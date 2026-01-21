import os, re, random, string, logging, datetime, pytz, sqlite3, asyncio
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from collections import defaultdict
from typing import Optional

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from telegram.error import TimedOut

from yt_dlp import YoutubeDL, DownloadError
from dotenv import load_dotenv

# ================== ENV / SETUP ==================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0")) or CHANNEL_ID
CAPTION = os.getenv("CAPTION", "")
DB_PATH = os.path.abspath(os.getenv("DATABASE", "cooldl.db"))
COOKIES_FILE = os.getenv("COOKIES_FILE", "").strip()

# NEW: Rate limiting & resource management
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 500)) * 1024 * 1024  # Default 500MB
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", 300))  # 5 min default
MAX_CONCURRENT = int(os.getenv("MAX_CONCURRENT", 3))
MAX_DOWNLOADS_PER_HOUR = int(os.getenv("MAX_DOWNLOADS_PER_HOUR", 10))
FILE_RETENTION_DAYS = int(os.getenv("FILE_RETENTION_DAYS", 7))

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)
URL_RE = re.compile(r'https?://[^\s<>")]+', re.I)

# NEW: Rate limiting tracker
download_semaphore = asyncio.Semaphore(MAX_CONCURRENT)
user_download_tracker = defaultdict(list)  # chat_id -> [timestamps]

# ================== URL NORMALIZATION ==================
STRIP_KEYS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
              "_t","_r","s","si","igsh","igshid","feature","fbclid"}

def normalize_url(raw: str) -> str:
    """Normalize without breaking short TikTok links. Canonicalize YouTube. Strip tracking elsewhere."""
    try:
        raw = raw.strip()
        u = urlparse(raw)
        scheme = "https"
        netloc = (u.netloc or "").lower()
        if netloc.startswith("www."): netloc = netloc[4:]
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
            if len(parts) >= 2 and parts[0] == "shorts":
                vid = parts[1]; path = "/watch"; q = {"v":[vid]}
            keep = {}
            if "v" in q and q["v"]: keep["v"] = [q["v"][0]]
            q = keep

        if netloc.endswith("x.com") or "twitter.com" in netloc or netloc.endswith("instagram.com"):
            q = {k:v for k,v in q.items() if k not in STRIP_KEYS}

        query = urlencode({k:v[0] for k,v in q.items()}) if q else ""
        norm = urlunparse((scheme, netloc, path, "", query, ""))
        return norm[:-1] if norm.endswith("?") else norm
    except Exception as e:
        logger.warning(f"URL normalization error: {e}")
        return raw.strip()

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

def rand_id(k=5): return ''.join(random.choices(string.digits, k=k))
def now_local(): return datetime.datetime.now(pytz.timezone('Asia/Riyadh')).strftime('%Y/%m/%d, %I:%M %p')
def now_utc_iso(): return datetime.datetime.now(datetime.timezone.utc).isoformat()

# NEW: Check rate limit
def check_rate_limit(chat_id: int) -> tuple[bool, str]:
    """Check if user exceeded download limit. Returns (allowed, message)."""
    now = datetime.datetime.now()
    hour_ago = now - datetime.timedelta(hours=1)
    
    # Clean old entries
    user_download_tracker[chat_id] = [ts for ts in user_download_tracker[chat_id] if ts > hour_ago]
    
    if len(user_download_tracker[chat_id]) >= MAX_DOWNLOADS_PER_HOUR:
        return False, f"⏱️ Rate limit: max {MAX_DOWNLOADS_PER_HOUR} downloads/hour. Try again later."
    
    return True, ""

def record_download(chat_id: int):
    """Record download timestamp for rate limiting."""
    user_download_tracker[chat_id].append(datetime.datetime.now())

# NEW: Cleanup old files
def cleanup_old_files():
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
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA busy_timeout=20000;")
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
                (user_id, url, filename, source, timestamp, chat_id, name, username, file_id, file_size)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", values)
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

def insert_download(user_id, url, filename, source, chat_id, name, username, file_id):
    try:
        file_size = (DOWNLOAD_DIR / filename).stat().st_size if (DOWNLOAD_DIR / filename).exists() else 0
    except:
        file_size = 0
    log_to_db("downloads", (user_id, url, filename, source, now_utc_iso(), chat_id, name, username, file_id, file_size))

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

def build_meta_text(file_id, name, username, source, url, path: Path):
    try:
        sz = human_size(path.stat().st_size)
    except:
        sz = "n/a"
    return (f"✅ Downloaded\nID: {file_id}\nUser: {name} ({username})\nSource: {source}\n"
            f"File: {path.name} ({sz})\nTime: {now_local()}\nURL: {url}")

async def send_with_retry(factory, retries=3, backoff_base=2):
    for i in range(retries):
        try:
            return await factory()
        except TimedOut:
            if i == retries - 1: raise
            await asyncio.sleep(backoff_base * (i + 1))

async def deliver_file(final_path: Path, source: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    sent_to_user = None
    file_extension = final_path.suffix.lower()
    file_size = final_path.stat().st_size

    # NEW: Validate file size before sending
    if file_size > MAX_FILE_SIZE:
        logger.error(f"File too large: {human_size(file_size)} > {human_size(MAX_FILE_SIZE)}")
        return False

    async def _send_video(to_chat):
        return await send_with_retry(lambda: context.bot.send_video(
            chat_id=to_chat, video=final_path.open("rb"),
            **video_args(final_path.stem)
        ))

    async def _send_document(to_chat):
        return await send_with_retry(lambda: context.bot.send_document(
            chat_id=to_chat, document=final_path.open("rb"),
            **doc_args(final_path.stem)
        ))
    
    if file_extension in ['.mp4', '.mov', '.webm']:
        try:
            sent_to_user = await _send_video(chat_id)
        except Exception:
            sent_to_user = await _send_document(chat_id)
    else:
        try:
            sent_to_user = await _send_video(chat_id)
        except Exception:
            sent_to_user = await _send_document(chat_id)
            
    if CHANNEL_ID and sent_to_user:
        try:
            await context.bot.copy_message(
                chat_id=CHANNEL_ID,
                from_chat_id=chat_id,
                message_id=sent_to_user.message_id
            )
        except Exception as e:
            logging.warning(f"copy to channel failed: {e}")

    return sent_to_user is not None

# ================== HANDLERS ==================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📥 Send me a video link to download. Supported: YouTube, TikTok, Instagram, X")

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = f"""
📋 Supported platforms:
• YouTube
• TikTok
• Instagram
• X (Twitter)

⚙️ Limits:
• Max {MAX_DOWNLOADS_PER_HOUR} downloads/hour
• Max file size: {human_size(MAX_FILE_SIZE)}


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

    log_to_db("users", (chat_id, name, username, now_utc_iso()))

    # === Cache ===
    cached = find_cached_file(cache_key)
    if cached:
        if CHANNEL_ID:
            try:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=build_meta_text(file_id, name, username, source, norm_url, cached),
                    disable_web_page_preview=True
                )
            except Exception as e:
                logging.warning(f"send meta to channel failed (cache): {e}")

        ok = await deliver_file(cached, source, chat_id, context)
        if not ok:
            try: await context.bot.send_message(chat_id=chat_id, text="⚠️ Sending failed.")
            except Exception: pass

        record_download(chat_id)
        insert_download(user.id, cache_key, cached.name, source, chat_id, name, username, file_id)
        if raw_url != cache_key:
            insert_download(user.id, raw_url, cached.name, source, chat_id, name, username, file_id)
        return

    # === Download (with semaphore) ===
    async with download_semaphore:
        progress_msg = await update.message.reply_text("⏳ Downloading...")
        caplog = CaptureLogger()
        filename = f"File{rand_id()}"
        outtmpl = str(DOWNLOAD_DIR / f"{filename}.%(ext)s")

        ydl_opts = {
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
            'retries': 5,
            'concurrent_fragment_downloads': 4,
            'socket_timeout': 30,
            'http_headers': {'User-Agent': 'Mozilla/5.0'}
        }
        if is_tiktok:
            ydl_opts['http_headers']['Referer'] = 'https://www.tiktok.com/'
        if COOKIES_FILE and os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE

        async def do_download(url_to_use: str, timeout: int = DOWNLOAD_TIMEOUT) -> Path:
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
                await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=f"❌ Error\n{name} ({username})\nID:{file_id}\nURL:{norm_url}\n\n{short_err}")
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

        if CHANNEL_ID:
            try:
                await context.bot.send_message(
                    chat_id=CHANNEL_ID,
                    text=build_meta_text(file_id, name, username, source, norm_url, final_path),
                    disable_web_page_preview=True
                )
            except Exception as e:
                logging.warning(f"send meta to channel failed: {e}")

        ok = await deliver_file(final_path, source, chat_id, context)
        if not ok:
            try: await context.bot.send_message(chat_id=chat_id, text="⚠️ Sending failed.")
            except Exception: pass
            return

        record_download(chat_id)
        try:
            insert_download(user.id, cache_key, final_path.name, source, chat_id, name, username, file_id)
            if raw_url != cache_key:
                insert_download(user.id, raw_url, final_path.name, source, chat_id, name, username, file_id)
            log_to_db("logs", (now_local(), "Downloaded", username, chat_id, "Success"))
        except Exception as e:
            logging.warning(f"recording download failed: {e}")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    cleanup_old_files()
    
    if not BOT_TOKEN:
        raise SystemExit("❌ BOT_TOKEN env var required")
    
    logger.info(f"Config: MAX_CONCURRENT={MAX_CONCURRENT}, TIMEOUT={DOWNLOAD_TIMEOUT}s, MAX_FILE_SIZE={human_size(MAX_FILE_SIZE)}")
    
    req = HTTPXRequest(connect_timeout=20, read_timeout=180)
    app = ApplicationBuilder().token(BOT_TOKEN).request(req).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()