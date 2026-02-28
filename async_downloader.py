import os, re, random, string, logging, datetime, pytz, sqlite3, asyncio, time, uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from collections import defaultdict
from typing import Optional

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, Conflict

from yt_dlp import YoutubeDL, DownloadError
from dotenv import load_dotenv

# Import configuration
from config import settings

# Import blocking system
from blocks import is_user_blocked, BLOCK_MESSAGE, log_blocked_attempt
from admin_commands import get_admin_handlers


def get_ydl_opts(base_opts, is_shorts=False, is_tiktok=False):
    """Get optimized yt-dlp options for different platforms."""
    
    opts = base_opts.copy()
    
    if is_shorts:
        # 🎯 OPTIMIZED FOR YOUTUBE SHORTS - Telegram compatible
        opts.update({
            # Prefer mp4 format with max 720p for better Telegram compatibility
            'format': 'best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio[acodec=opus]/bestvideo[height<=720]+bestaudio/best',
            # Force mp4 container for Telegram compatibility
            'recode-video': 'mp4' if opts.get('recode-video') else None,
            # Ensure audio is in compatible format
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                    'when': 'post_process'
                },
                # Add audio codec conversion if needed
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                    'when': 'post_process'
                }
            ],
            # Shorts-specific optimizations
            'writethumbnail': False,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'embedthumbnail': False,
            'addmetadata': False,
            'no_warnings': True,
            'ignoreerrors': False,
            'extract_flat': 'discard_in_playlist',
            'fragment_retries': 15,
            'hls_prefer_native': True,
            'compat_opts': ['embed-thumbnail-ffmpeg'],
            # Additional headers for shorts
            'http_headers': {
                **opts.get('http_headers', {}),
                'Referer': settings.telegram.youtube_referer,
                'Accept': settings.telegram.accept_header,
            }
        })
    
    return opts

# ================== CONFIG / SETUP ==================
load_dotenv()

# Use configuration system
DB_PATH = settings.database.absolute_path
COOKIES_FILE = settings.download.cookies_file.strip()
DOWNLOAD_DIR = settings.download.download_dir_path

# Configure logging
logging.basicConfig(level=getattr(logging, settings.log_level))
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
URL_RE = re.compile(r'https?://[^\s<>")]+', re.I)

# Rate limiting tracker
download_semaphore = asyncio.Semaphore(settings.rate_limit.max_concurrent)
user_download_tracker = defaultdict(list)  # chat_id -> [timestamps]

# ================== URL NORMALIZATION ==================
STRIP_KEYS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
              "_t","_r","s","si","igsh","igshid","feature","fbclid","app", "m",
              "cshid", "pp", "sns", "share"}

def normalize_url(raw: str) -> str:
    """Enhanced URL normalization with better YouTube shorts and mobile domain handling."""
    try:
        raw = raw.strip()
        u = urlparse(raw)
        scheme = "https"
        netloc = (u.netloc or "").lower()
        
        # Normalize mobile and www subdomains
        if netloc.startswith("www.") or netloc.startswith("m.") or netloc.startswith("mobile."):
            netloc = netloc.split(".", 1)[1]
        
        path = u.path or "/"
        q = parse_qs(u.query, keep_blank_values=False)

        if "tiktok.com" in netloc:
            q = {k:v for k,v in q.items() if k not in STRIP_KEYS}
            query = urlencode({k:v[0] for k,v in q.items()}) if q else ""
            return urlunparse((scheme, netloc, path, "", query, ""))

        if netloc == "youtu.be":
            vid = path.strip("/").split("/")[0]
            netloc = "youtube.com"; path = "/watch"; q = {"v":[vid]}
        elif netloc.endswith("youtube.com"):
            parts = [p for p in path.split("/") if p]
            
            # Handle shorts URLs
            if len(parts) >= 2 and parts[0] == "shorts":
                vid = parts[1]; path = "/watch"; q = {"v":[vid]}
            # Handle live URLs
            elif len(parts) >= 2 and parts[0] == "live":
                vid = parts[1]; path = "/watch"; q = {"v":[vid], "feature": ["live"]}
            
            # Keep only essential YouTube parameters
            keep = {}
            if "v" in q and q["v"]: keep["v"] = [q["v"][0]]
            if "list" in q and q["list"]: keep["list"] = [q["list"][0]]
            if "t" in q and q["t"]: keep["t"] = [q["t"][0]]
            if "index" in q and q["index"]: keep["index"] = [q["index"][0]]
            q = keep

        if netloc.endswith("x.com") or "twitter.com" in netloc or netloc.endswith("instagram.com"):
            q = {k:v for k,v in q.items() if k not in STRIP_KEYS}

        query = urlencode({k:v[0] for k,v in q.items()}) if q else ""
        norm = urlunparse((scheme, netloc, path, "", query, ""))
        return norm[:-1] if norm.endswith("?") else norm
    except Exception as e:
        logger.warning(f"URL normalization error: {e}")
        return raw.strip()

def is_youtube_shorts(url: str) -> bool:
    """Check if URL is a YouTube shorts video."""
    return "shorts" in url.lower() or ("youtu.be" in url and len(url) > 30)

def strip_query(u: str) -> str:
    try:
        p = urlparse(u)
        return urlunparse((p.scheme or "https", (p.netloc or "").lower().lstrip("www."), p.path or "/", "", "", ""))
    except Exception:
        return u

# ================== HELPERS ==================
def extract_urls(text: str) -> list[str]:
    if not text: return []
    urls = URL_RE.findall(text)
    return [u.rstrip(').,;!?"""\'') for u in urls]

def get_source(url):
    u = url.lower()
    if "tiktok.com" in u: return "TikTok"
    if "instagram" in u: return "Instagram"
    if "x.com" in u or "twitter.com" in u: return "X"
    if "youtube" in u or "youtu.be" in u: return "YouTube"
    return "Unknown"

def rand_id(): return ''.join(random.choices(string.digits, k=settings.random_id_length))
def now_local(): return datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p')
def now_utc_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

# NEW: Check rate limit
def check_rate_limit(chat_id: int) -> tuple[bool, str]:
    """Check if user exceeded download limit. Returns (allowed, message)."""
    now = datetime.datetime.now()
    hour_ago = now - datetime.timedelta(hours=1)
    
    # Clean old entries
    user_download_tracker[chat_id] = [ts for ts in user_download_tracker[chat_id] if ts > hour_ago]
    
    if len(user_download_tracker[chat_id]) >= settings.rate_limit.max_downloads_per_hour:
        return False, f"⏱️ Rate limit: max {settings.rate_limit.max_downloads_per_hour} downloads/hour. Try again later."
    
    return True, ""

def record_download(chat_id: int):
    """Record download timestamp for rate limiting."""
    user_download_tracker[chat_id].append(datetime.datetime.now())

# NEW: Cleanup old files
# cleanup_old_files() # Disabled - keeping files longer
    """Remove files older than FILE_RETENTION_DAYS."""
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=FILE_RETENTION_DAYS)
        for fp in DOWNLOAD_DIR.glob("*"):
            if fp.is_file() and datetime.datetime.fromtimestamp(fp.stat().st_mtime) < cutoff:
                fp.unlink()
                logger.info(f"Cleaned up old file: {fp.name}")
    except Exception as e:
        logger.warning(f"Cleanup error: {e}")

# ================== DB ==================
def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=settings.database.connection_timeout)
    c.row_factory = sqlite3.Row
    try:
        c.execute(f"PRAGMA journal_mode={settings.database.journal_mode};")
        c.execute(f"PRAGMA busy_timeout={settings.database.busy_timeout};")
    except Exception:
        pass
    return c

def ensure_tables():
    c = conn(); cur = c.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      chat_id INTEGER PRIMARY KEY,
      name TEXT,
      username TEXT,
      created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS downloads (
      file_id TEXT,
      timestamp TEXT,
      username TEXT,
      chat_id INTEGER,
      name TEXT,
      url TEXT,
      source TEXT,
      user_id TEXT,
      filename TEXT,
      file_size INTEGER
    );
    CREATE TABLE IF NOT EXISTS errors (
      error TEXT,
      file_id TEXT,
      timestamp TEXT,
      username TEXT,
      chat_id INTEGER,
      name TEXT,
      url TEXT
    );
    CREATE TABLE IF NOT EXISTS logs (
      timestamp TEXT,
      action TEXT,
      username TEXT,
      chat_id INTEGER,
      status TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_downloads_url ON downloads(url);
    CREATE INDEX IF NOT EXISTS ix_downloads_chat ON downloads(chat_id);
    CREATE INDEX IF NOT EXISTS ix_downloads_timestamp ON downloads(timestamp);
    """)
    c.commit(); c.close()

def log_to_db(table, values):
    c = conn(); cur = c.cursor()
    try:
        if table == "downloads":
            cur.execute("""INSERT INTO downloads
                (user_id, url, filename, source, timestamp, chat_id, name, username, file_id, file_size, session)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", values)
        elif table == "users":
            cur.execute("INSERT OR IGNORE INTO users (chat_id, name, username, created_at) VALUES (?,?,?,?)", values)
        elif table == "errors":
            cur.execute("""INSERT INTO errors (error, file_id, timestamp, username, chat_id, name, url)
                             VALUES (?,?,?,?,?,?,?)""", values)
        elif table == "logs":
            cur.execute("""INSERT INTO logs (timestamp, action, username, chat_id, status)
                             VALUES (?,?,?,?,?)""", values)
        c.commit()
    except Exception as e:
        logger.error(f"DB logging error: {e}")
    finally:
        c.close()

def insert_download(user_id, url, filename, source, chat_id, name, username, file_id, session=None):
    try:
        file_size = (DOWNLOAD_DIR / filename).stat().st_size if (DOWNLOAD_DIR / filename).exists() else 0
    except:
        file_size = 0
    log_to_db("downloads", (user_id, url, filename, source, now_utc_iso(), chat_id, name, username, file_id, file_size, session))

def find_cached_file(url: str) -> Optional[Path]:
    c = conn(); cur = c.cursor()
    try:
        cur.execute("SELECT filename FROM downloads WHERE url=? ORDER BY rowid DESC LIMIT 1", (url,))
        row = cur.fetchone()
        if not row:
            alt = strip_query(url)
            cur.execute("SELECT filename FROM downloads WHERE url=? ORDER BY rowid DESC LIMIT 1", (alt,))
            row = cur.fetchone()
    finally:
        c.close()
    if not row or not row["filename"]:
        return None
    fp = DOWNLOAD_DIR / row["filename"]
    return fp if fp.exists() else None

# ================== LOG AGGREGATION ==================
class CaptureLogger:
    def __init__(self): self.buf = []
    def debug(self, msg): self.buf.append(str(msg))
    def warning(self, msg): self.buf.append(f"[W] {msg}")
    def error(self, msg): self.buf.append(f"[E] {msg}")
    def tail(self, n=40): return "\n".join(self.buf[-n:])

def video_args(caption: str = ""): return dict(caption=(CAPTION or caption[:950]), supports_streaming=True)
def doc_args(caption: str = ""):   return dict(caption=(CAPTION or caption[:950]))

def human_size(sz: int) -> str:
    """Convert bytes to human-readable format."""
    if sz == 0:
        return "0B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(sz)
    
    for unit in units:
        if size < 1024:
            if unit == "B":
                return f"{int(size)}{unit}"
            return f"{size:.2f}{unit}"
        size /= 1024
    
    return f"{size:.2f}TB"

def build_meta_text(user_id, name, username, source, url, path: Path):
    try:
        sz = human_size(path.stat().st_size)
    except:
        sz = "n/a"
    return (f"ID: {user_id}\n"
            f"User: {name} ({username})\n"
            f"Source: {source}\n"
            f"File: {path.name} ({sz})\n"
            f"Time: {now_local()}\n"
            f"URL: {url}")

async def send_with_retry(factory, retries=3, backoff_base=2):
    for i in range(retries):
        try:
            return await factory()
        except TimedOut:
            if i == retries - 1: raise
            await asyncio.sleep(backoff_base * (i + 1))

async def deliver_file(final_path: Path, source: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    sent_to_user = None
    sent_to_log = None
    file_extension = final_path.suffix.lower()
    file_size = final_path.stat().st_size

    # Validate file size before sending
    if file_size > settings.rate_limit.max_file_size_bytes:
        logger.error(f"File too large: {human_size(file_size)} > {human_size(settings.rate_limit.max_file_size_bytes)}")
        return False

    # Create inline keyboard button
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    keyboard = [[InlineKeyboardButton("Downloaded with @CoolDLBot", url="https://t.me/CoolDLBot")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    async def _send_video(to_chat, include_caption=True):
        caption = settings.bot.caption if include_caption and settings.bot.caption else ""
        return await send_with_retry(lambda: context.bot.send_video(
            chat_id=to_chat, video=final_path.open("rb"),
            caption=caption,
            reply_markup=reply_markup,
            supports_streaming=True
        ))

    async def _send_document(to_chat, include_caption=True):
        caption = settings.bot.caption if include_caption and settings.bot.caption else ""
        return await send_with_retry(lambda: context.bot.send_document(
            chat_id=to_chat, document=final_path.open("rb"),
            caption=caption,
            reply_markup=reply_markup
        ))
    
    # Send to user (without filename caption)
    if file_extension in ['.mp4', '.mov', '.webm']:
        try:
            sent_to_user = await _send_video(chat_id, include_caption=False)
        except Exception:
            sent_to_user = await _send_document(chat_id, include_caption=False)
    else:
        try:
            sent_to_user = await _send_video(chat_id, include_caption=False)
        except Exception:
            sent_to_user = await _send_document(chat_id, include_caption=False)
    
    # Send to log channel (with metadata caption if caption is set)
    if settings.bot.log_channel_id:
        try:
            if file_extension in ['.mp4', '.mov', '.webm']:
                sent_to_log = await _send_video(settings.bot.log_channel_id, include_caption=True)
            else:
                sent_to_log = await _send_document(settings.bot.log_channel_id, include_caption=True)
        except Exception as e:
            logging.warning(f"send to log channel failed: {e}")
    
    # Also copy to regular channel if set (for backward compatibility)
    if settings.bot.channel_id and settings.bot.channel_id != settings.bot.log_channel_id and sent_to_user:
        try:
            await context.bot.copy_message(
                chat_id=settings.bot.channel_id,
                from_chat_id=chat_id,
                message_id=sent_to_user.message_id
            )
        except Exception as e:
            logging.warning(f"copy to channel failed: {e}")

    return sent_to_user is not None

# ================== HANDLERS ==================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 Send me a video link to download. Supported: TikTok, Instagram, X")

async def status_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = f"🟢: Bot is up and running"
    await update.message.reply_text(msg)

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = f"""
📋 Supported platforms:
• TikTok  
• Instagram
• X (Twitter)
• Snapchat
• Tumblr

⚙️ Limits:
• Max {settings.rate_limit.max_downloads_per_hour} downloads/hour
• Max file size: {human_size(settings.rate_limit.max_file_size_bytes)}


🔗 Send a URL to download!
"""
    await update.message.reply_text(msg)

async def process_single_url(raw_url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()

    user = update.message.from_user
    chat_id = update.message.chat_id
    name = user.first_name or "User"
    username = f"@{user.username or 'unknown'}"

    # NEW: Rate limit check
    allowed, msg = check_rate_limit(chat_id)
    if not allowed:
        await update.message.reply_text(msg)
        return

    norm_url = normalize_url(raw_url)
    cache_key = norm_url
    file_id = rand_id()
    source = get_source(norm_url)
    is_tiktok = (source == "TikTok")
    is_shorts = (source == "YouTube" and is_youtube_shorts(norm_url))

    log_to_db("users", (chat_id, name, username, now_utc_iso()))

    # === Cache ===
    cached = find_cached_file(cache_key)
    if cached:
        if settings.bot.log_channel_id:
            try:
                await context.bot.send_message(
                    chat_id=settings.bot.log_channel_id,
                    text=build_meta_text(user.id, name, username, source, norm_url, cached),
                    disable_web_page_preview=True
                )
            except Exception as e:
                logging.warning(f"send meta to log channel failed (cache): {e}")

        ok = await deliver_file(cached, source, chat_id, context)
        if not ok:
            try: await context.bot.send_message(chat_id=chat_id, text="⚠️ Sending failed.")
            except Exception: pass

        record_download(chat_id)
        insert_download(user.id, cache_key, cached.name, source, chat_id, name, username, file_id, None)
        if raw_url != cache_key:
            insert_download(user.id, raw_url, cached.name, source, chat_id, name, username, file_id, None)
        return

    # === Download (with semaphore) ===
    async with download_semaphore:
        progress_msg = await update.message.reply_text("⏳ Downloading...")
        caplog = CaptureLogger()
        filename = f"File{rand_id()}"
        outtmpl = str(DOWNLOAD_DIR / f"{filename}.%(ext)s")

        # Set up ydl_opts with platform-specific handling
        base_opts = {
            'outtmpl': outtmpl,
            'format': 'bv*+ba/b',
            'recode-video': 'mp4',
            'postprocessors': [{
                'key': 'FFmpegVideoRemuxer',
                'preferedformat': 'mp4',
            }],
            'noplaylist': True,
            'quiet': True,
            'logger': caplog,
            'retries': settings.download.retries,
            'concurrent_fragment_downloads': settings.download.concurrent_fragments,
            'socket_timeout': settings.download.socket_timeout,
            'http_headers': {'User-Agent': settings.telegram.user_agent}
        }
        
        # Apply platform-specific optimizations
        ydl_opts = get_ydl_opts(base_opts, is_shorts=is_shorts, is_tiktok=is_tiktok)
        
        # Add TikTok impersonation for age-restricted content
        if is_tiktok:
            ydl_opts['extractor_args'] = {'tiktok': ['impersonate=webkit']}
            ydl_opts['http_headers']['Referer'] = settings.telegram.tiktok_referer
        
        if COOKIES_FILE and os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE

        async def do_download(url_to_use: str, timeout: int = settings.download.timeout_seconds) -> Path:
            loop = asyncio.get_running_loop()
            def run():
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url_to_use, download=True)
                    fp = Path(ydl.prepare_filename(info))
                    if not fp.exists():
                        matches = list(DOWNLOAD_DIR.glob(f"{filename}.*"))
                        if not matches: raise FileNotFoundError("Output file not found.")
                        return matches[0]
                    return fp
            return await asyncio.wait_for(loop.run_in_executor(None, run), timeout=timeout)

        try:
            try:
                final_path: Path = await do_download(norm_url)
            except (DownloadError, asyncio.TimeoutError) as de:
                if isinstance(de, DownloadError) and ("404" in str(de) or "Unable to download" in str(de)):
                    final_path = await do_download(raw_url)
                else:
                    raise
        except asyncio.TimeoutError:
            logger.error(f"Download timeout: {norm_url}")
            try: await context.bot.send_message(chat_id=chat_id, text="⏱️ Download timeout. Try again later.")
            except Exception: pass
            try: await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
            except Exception: pass
            log_to_db("logs", (now_local(), "DownloadTimeout", username, chat_id, "Timeout"))
            return
        except Exception as e:
            short_err = f"{type(e).__name__}: {str(e)[:100]}"
            logger.error(f"Download error: {short_err}")
            try: await context.bot.send_message(chat_id=chat_id, text="❌ Download failed. Try another URL.")
            except Exception: pass
            try:
                await context.bot.send_message(chat_id=settings.bot.log_channel_id, text=f"❌ Error\n{name} ({username})\nID:{file_id}\nURL:{norm_url}\n\n{short_err}")
            except Exception: pass
            log_to_db("errors", (short_err, file_id, now_local(), username, chat_id, name, norm_url))
            log_to_db("logs", (now_local(), "DownloadFailed", username, chat_id, "Fail"))
            try: await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
            except Exception: pass
            return

        # === Post-download ===
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
        except Exception as e:
            logging.warning(f"delete progress msg failed: {e}")

        if settings.bot.log_channel_id:
            try:
                await context.bot.send_message(
                    chat_id=settings.bot.log_channel_id,
                    text=build_meta_text(user.id, name, username, source, norm_url, final_path),
                    disable_web_page_preview=True
                )
            except Exception as e:
                logging.warning(f"send meta to log channel failed: {e}")

        ok = await deliver_file(final_path, source, chat_id, context)
        if not ok:
            try: await context.bot.send_message(chat_id=chat_id, text="⚠️ Sending failed.")
            except Exception: pass
            return

        record_download(chat_id)
        try:
            insert_download(user.id, cache_key, final_path.name, source, chat_id, name, username, file_id, None)
            if raw_url != cache_key:
                insert_download(user.id, raw_url, final_path.name, source, chat_id, name, username, file_id, None)
            log_to_db("logs", (now_local(), "Downloaded", username, chat_id, "Success"))
        except Exception as e:
            logging.warning(f"recording download failed: {e}")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is blocked first
    if update.message and update.message.from_user:
        chat_id = update.message.from_user.id
        
        if is_user_blocked(chat_id):
            # User is blocked, send block message and log the attempt
            username = update.message.from_user.username or "Unknown"
            url = update.message.text if hasattr(update.message, 'text') else "Unknown"
            
            # Log the blocked attempt
            log_blocked_attempt(chat_id, url, username)
            
            # Send block message
            await update.message.reply_text(BLOCK_MESSAGE)
            return
    
    urls = extract_urls(update.message.text)
    if not urls:
        await update.message.reply_text("❌ No valid URLs found.")
        return
    for raw_url in urls:
        try:
            await process_single_url(raw_url, update, context)
        except Exception as e:
            logger.exception(f"fatal error processing url {raw_url}: {e}")
            try:
                await update.message.reply_text("⚠️ Unexpected error.")
            except Exception:
                pass

# ================== BOOTSTRAP ==================
if __name__ == '__main__':
    ensure_tables()
    # cleanup_old_files() # Disabled - keeping files longer
    
    if not settings.bot.token:
        raise SystemExit("❌ BOT_TOKEN env var required")
    
    logger.info(f"Config: MAX_CONCURRENT={settings.rate_limit.max_concurrent}, TIMEOUT={settings.download.timeout_seconds}s, MAX_FILE_SIZE={human_size(settings.rate_limit.max_file_size_bytes)}")
    
    req = HTTPXRequest(connect_timeout=settings.telegram.request_connect_timeout, read_timeout=settings.telegram.request_read_timeout)
    
    # Use unique bot instance to avoid conflicts
    app = ApplicationBuilder().token(settings.bot.token).request(req).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # Add admin commands
    admin_handlers = get_admin_handlers()
    for command, handler in admin_handlers:
        app.add_handler(CommandHandler(command, handler))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    # Enhanced polling with conflict handling
    import time
    from telegram.error import Conflict
    
    max_retries = settings.telegram.polling_max_retries
    for attempt in range(max_retries):
        try:
            logger.info(f"Starting polling (attempt {attempt + 1}/{max_retries})...")
            app.run_polling(drop_pending_updates=True)
            break
        except Conflict as e:
            logger.warning(f"Conflict detected: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * settings.telegram.polling_conflict_wait_base  # 30s, 60s, 90s, etc.
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                logger.error("Max retries reached. Bot cannot start due to conflict.")
                raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise