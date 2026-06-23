import os, re, random, string, logging, datetime, pytz, sqlite3, asyncio, time, uuid
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from collections import defaultdict
from typing import Optional, Tuple

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from telegram.request import HTTPXRequest
from telegram.error import TimedOut, Conflict

from yt_dlp import YoutubeDL, DownloadError
from dotenv import load_dotenv

# Import configuration
from config import settings

# Import unified database layer
import db

# Import blocking system
from blocks import is_user_blocked, log_blocked_attempt

# Block message in English
BLOCK_MESSAGE = "You've been banned from using this bot."
from admin_commands import get_admin_handlers

# Import enhanced systems (Phase 1)
from error_recovery import download_with_retry, error_recovery
from file_manager import file_manager
from security_manager import security_manager, security_check_before_download, record_download_start, record_download_complete

# Import Phase 2 systems
from url_validator import url_validator, validate_and_analyze, pre_download_check
from queue_manager import queue_manager, initialize_queue_manager, get_rate_limit_info, format_user_stats
from user_commands import get_user_command_handlers, get_callback_handlers, help_callback_handler, enhanced_help_command


def get_ydl_opts(base_opts, is_shorts=False, is_tiktok=False):
    """Get optimized yt-dlp options for different platforms."""
    opts = base_opts.copy()
    
    if is_shorts:
        opts.update({
            'format': 'best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio[acodec=opus]/bestvideo[height<=720]+bestaudio/best',
            'recode-video': 'mp4' if opts.get('recode-video') else None,
            'postprocessors': [
                {
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                    'when': 'post_process'
                },
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                    'when': 'post_process'
                }
            ],
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

def normalize_and_detect_url(raw_url: str) -> Tuple[str, bool]:
    """Normalize URL and detect if it's a YouTube short.
    
    Returns:
        Tuple of (normalized_url, is_shorts)
    """
    try:
        raw_url = raw_url.strip()
        u = urlparse(raw_url)
        scheme = "https"
        netloc = (u.netloc or "").lower()
        
        # Normalize mobile and www subdomains
        if netloc.startswith("www.") or netloc.startswith("m.") or netloc.startswith("mobile."):
            netloc = netloc.split(".", 1)[1]
        
        path = u.path or "/"
        q = parse_qs(u.query, keep_blank_values=False)
        is_shorts = False

        if "tiktok.com" in netloc:
            q = {k:v for k,v in q.items() if k not in STRIP_KEYS}
            query = urlencode({k:v[0] for k,v in q.items()}) if q else ""
            return urlunparse((scheme, netloc, path, "", query, "")), is_shorts

        if netloc == "youtu.be":
            vid = path.strip("/").split("/")[0]
            netloc = "youtube.com"; path = "/watch"; q = {"v":[vid]}
        elif netloc.endswith("youtube.com"):
            parts = [p for p in path.split("/") if p]
            
            # Handle shorts URLs
            if len(parts) >= 2 and parts[0] == "shorts":
                vid = parts[1]; path = "/watch"; q = {"v":[vid]}; is_shorts = True
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
        norm = norm[:-1] if norm.endswith("?") else norm
        return norm, is_shorts
    except Exception as e:
        logger.warning(f"URL normalization error: {e}")
        return raw_url.strip(), False

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

# ================== DATABASE ==================
# Database functions moved to db.py



# ================== LOG AGGREGATION ==================
class CaptureLogger:
    def __init__(self): self.buf = []
    def debug(self, msg): self.buf.append(str(msg))
    def warning(self, msg): self.buf.append(f"[W] {msg}")
    def error(self, msg): self.buf.append(f"[E] {msg}")
    def tail(self, n=40): return "\n".join(self.buf[-n:])

# ================== DELIVERY ==================
async def deliver_file(conn, final_path: Path, source: str, chat_id: int, 
                      user_id: int, name: str, username: str, url: str,
                      context: ContextTypes.DEFAULT_TYPE, is_from_cache: bool) -> bool:
    """Deliver file to user and log channels.
    
    Args:
        conn: Database connection
        final_path: Path to the file
        source: Platform source (TikTok, YouTube, etc.)
        chat_id: User's chat ID
        user_id: User's Telegram ID
        name: User's first name
        username: User's username
        url: Original URL
        context: Telegram context
        is_cache: Whether file is from cache
    """
    sent_to_user = None
    file_extension = final_path.suffix.lower()
    file_size = final_path.stat().st_size

    # Validate file size
    if file_size > settings.rate_limit.max_file_size_bytes:
        logger.error(f"File too large: {human_size(file_size)} > {human_size(settings.rate_limit.max_file_size_bytes)}")
        return False

    # Build inline keyboard
    keyboard = [[InlineKeyboardButton("Downloaded with @CoolDLBot", url="https://t.me/CoolDLBot")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send with retry logic
    async def send_with_retry(factory, retries=3):
        for i in range(retries):
            try:
                return await factory()
            except TimedOut:
                if i == retries - 1:
                    raise
                await asyncio.sleep(2 * (i + 1))

    # Create send functions
    async def send_file(to_chat, as_video=True):
        caption = settings.bot.caption if settings.bot.caption else ""
        if as_video:
            return await send_with_retry(lambda: context.bot.send_video(
                chat_id=to_chat, video=final_path.open("rb"),
                caption=caption, reply_markup=reply_markup, supports_streaming=True
            ))
        else:
            return await send_with_retry(lambda: context.bot.send_document(
                chat_id=to_chat, document=final_path.open("rb"),
                caption=caption, reply_markup=reply_markup
            ))

    # Send to user
    try:
        if file_extension in ['.mp4', '.mov', '.webm']:
            sent_to_user = await send_file(chat_id, as_video=True)
        else:
            sent_to_user = await send_file(chat_id, as_video=False)
    except Exception:
        try:
            sent_to_user = await send_file(chat_id, as_video=False)
        except Exception:
            pass

    # Build and send metadata to log channel
    if settings.bot.log_channel_id:
        try:
            sz = human_size(file_size)
            now_local = datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p')
            meta_text = (f"ID: {user_id}\nUser: {name} ({username})\nSource: {source}\n"
                        f"File: {final_path.name} ({sz})\nTime: {now_local}\nURL: {url}\n(FRESH DOWNLOAD)")
            await context.bot.send_message(
                chat_id=settings.bot.log_channel_id,
                text=meta_text,
                disable_web_page_preview=True
            )
        except Exception as e:
            logging.warning(f"send meta to log channel failed: {e}")

    # Send file to log channel
    if settings.bot.log_channel_id:
        try:
            await send_file(settings.bot.log_channel_id, as_video=(file_extension in ['.mp4', '.mov', '.webm']))
        except Exception as e:
            logging.warning(f"send file to log channel failed: {e}")

    # Copy to regular channel if set
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

# ================== DOWNLOAD HANDLING ==================
async def download_fresh(conn, norm_url: str, raw_url: str, source: str, chat_id: int,
                        user_id: int, name: str, username: str, file_id: str,
                        is_tiktok: bool, is_shorts: bool, context: ContextTypes.DEFAULT_TYPE,
                        update: Update):
    """Handle fresh download."""
    progress_msg = await update.message.reply_text("⏳ Downloading...")
    caplog = CaptureLogger()
    filename = f"File{''.join(random.choices(string.digits, k=settings.random_id_length))}"
    outtmpl = str(DOWNLOAD_DIR / f"{filename}.%(ext)s")

    # Set up ydl_opts
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
    
    ydl_opts = get_ydl_opts(base_opts, is_shorts=is_shorts, is_tiktok=is_tiktok)
    
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
                    if not matches:
                        raise FileNotFoundError("Output file not found.")
                    return matches[0]
                return fp
        return await asyncio.wait_for(loop.run_in_executor(None, run), timeout=timeout)

    try:
        try:
            final_path = await do_download(norm_url)
        except (DownloadError, asyncio.TimeoutError) as de:
            if isinstance(de, DownloadError) and ("404" in str(de) or "Unable to download" in str(de)):
                final_path = await do_download(raw_url)
            else:
                raise
    except asyncio.TimeoutError:
        logger.error(f"Download timeout: {norm_url}")
        try:
            await context.bot.send_message(chat_id=chat_id, text="⏱️ Download timeout. Try again later.")
        except Exception:
            pass
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
        except Exception:
            pass
        db.log_to_db(conn, "logs", (datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p'), 
                                  "DownloadTimeout", username, chat_id, "Timeout"))
        return
    except Exception as e:
        short_err = f"{type(e).__name__}: {str(e)[:100]}"
        logger.error(f"Download error: {short_err}")
        try:
            await context.bot.send_message(chat_id=chat_id, text="❌ Download failed. Try another URL.")
        except Exception:
            pass
        try:
            await context.bot.send_message(chat_id=settings.bot.log_channel_id, 
                                          text=f"❌ Error\n{name} ({username})\nID:{file_id}\nURL:{norm_url}\n\n{short_err}")
        except Exception:
            pass
        db.log_to_db(conn, "errors", (short_err, file_id, datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p'), 
                                    username, chat_id, name, norm_url))
        db.log_to_db(conn, "logs", (datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p'), 
                                "DownloadFailed", username, chat_id, "Fail"))
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
        except Exception:
            pass
        return

    # Delete progress message
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
    except Exception as e:
        logging.warning(f"delete progress msg failed: {e}")

    # Deliver file
    ok = await deliver_file(conn, final_path, source, chat_id, user_id, name, username, norm_url, context, is_cache=False)
    if not ok:
        try:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Sending failed.")
        except Exception:
            pass
        return

    record_download(chat_id)
    try:
        # Record download to database
        try:
            file_size = (DOWNLOAD_DIR / final_path.name).stat().st_size if (DOWNLOAD_DIR / final_path.name).exists() else 0
        except:
            file_size = 0
        db.log_to_db(conn, "downloads", (user_id, norm_url, final_path.name, source, datetime.datetime.now(datetime.timezone.utc).isoformat(), 
                                         chat_id, name, username, file_size, file_size, None))
        if raw_url != norm_url:
            try:
                file_size = (DOWNLOAD_DIR / final_path.name).stat().st_size if (DOWNLOAD_DIR / final_path.name).exists() else 0
            except:
                file_size = 0
            db.log_to_db(conn, "downloads", (user_id, raw_url, final_path.name, source, datetime.datetime.now(datetime.timezone.utc).isoformat(), 
                                             chat_id, name, username, file_size, file_size, None))
        db.log_to_db(conn, "logs", (datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p'), 
                                "Downloaded", username, chat_id, "Success"))
    except Exception as e:
        logging.warning(f"recording download failed: {e}")


async def download_fresh_enhanced(conn, norm_url: str, raw_url: str, source: str, chat_id: int,
                               user_id: int, name: str, username: str, file_id: str,
                               is_tiktok: bool, is_shorts: bool, context: ContextTypes.DEFAULT_TYPE,
                               update: Update):
    """Enhanced fresh download with error recovery and security features."""
    progress_msg = await update.message.reply_text("⏳ Downloading...")
    caplog = CaptureLogger()
    filename = f"File{''.join(random.choices(string.digits, k=settings.random_id_length))}"
    outtmpl = str(DOWNLOAD_DIR / f"{filename}.%(ext)s")

    # Set up ydl_opts
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
    
    ydl_opts = get_ydl_opts(base_opts, is_shorts=is_shorts, is_tiktok=is_tiktok)
    
    if is_tiktok:
        ydl_opts['extractor_args'] = {'tiktok': ['impersonate=webkit']}
        ydl_opts['http_headers']['Referer'] = settings.telegram.tiktok_referer
    
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        ydl_opts['cookiefile'] = COOKIES_FILE

    async def enhanced_do_download(url: str, timeout: int = settings.download.timeout_seconds) -> Path:
        loop = asyncio.get_running_loop()
        def run():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                fp = Path(ydl.prepare_filename(info))
                if not fp.exists():
                    matches = list(DOWNLOAD_DIR.glob(f"{filename}.*"))
                    if not matches:
                        raise FileNotFoundError("Output file not found.")
                    return matches[0]
                return fp
        return await asyncio.wait_for(loop.run_in_executor(None, run), timeout=timeout)

    # Use enhanced error recovery
    async def download_with_enhanced_recovery(url: str) -> Optional[Path]:
        return await download_with_retry(url, chat_id, context, enhanced_do_download, conn)

    try:
        # Try normalized URL first
        final_path = await download_with_enhanced_recovery(norm_url)
        if not final_path:
            # If normalized URL fails, try raw URL
            logger.info(f"Normalized URL failed, trying raw URL: {raw_url}")
            final_path = await download_with_enhanced_recovery(raw_url)
            
        if not final_path:
            # All attempts failed
            logger.error(f"All download attempts failed for: {norm_url}")
            return False
            
    except Exception as e:
        logger.error(f"Unexpected error in download: {e}")
        return False

    # Delete progress message
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
    except Exception as e:
        logging.warning(f"delete progress msg failed: {e}")

    # Deliver file
    ok = await deliver_file(conn, final_path, source, chat_id, user_id, name, username, norm_url, context, is_cache=False)
    if not ok:
        try:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Sending failed.")
        except Exception:
            pass
        return False

    # Record file access for smart file management
    file_manager.record_file_access(final_path.name)
    
    record_download(chat_id)
    try:
        # Record download to database
        try:
            file_size = (DOWNLOAD_DIR / final_path.name).stat().st_size if (DOWNLOAD_DIR / final_path.name).exists() else 0
        except:
            file_size = 0
        db.log_to_db(conn, "downloads", (user_id, norm_url, final_path.name, source, datetime.datetime.now(datetime.timezone.utc).isoformat(), 
                                         chat_id, name, username, file_size, file_size, None))
        if raw_url != norm_url:
            try:
                file_size = (DOWNLOAD_DIR / final_path.name).stat().st_size if (DOWNLOAD_DIR / final_path.name).exists() else 0
            except:
                file_size = 0
            db.log_to_db(conn, "downloads", (user_id, raw_url, final_path.name, source, datetime.datetime.now(datetime.timezone.utc).isoformat(), 
                                             chat_id, name, username, file_size, file_size, None))
        db.log_to_db(conn, "logs", (datetime.datetime.now(pytz.timezone(settings.timezone)).strftime('%Y/%m/%d, %I:%M %p'), 
                                "Downloaded", username, chat_id, "Success"))
    except Exception as e:
        logging.warning(f"recording download failed: {e}")
    
    return True

# ================== URL PROCESSING ==================
async def process_single_url(raw_url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = db.get_connection()

    user = update.message.from_user
    chat_id = update.message.chat_id
    name = user.first_name or "User"
    username = f"@{user.username or 'unknown'}"

    # === Phase 2: Intelligent URL Validation ===
    should_proceed, validation_msg, url_analysis = await pre_download_check(raw_url)
    if not should_proceed:
        await update.message.reply_text(f"❌ {validation_msg}")
        conn.close()
        return
    
    # Show URL analysis if there are warnings (non-blocking)
    if url_analysis and url_analysis.warnings:
        warning_text = url_validator.format_analysis_for_user(url_analysis)
        if warning_text:
            try:
                await update.message.reply_text(warning_text, parse_mode='Markdown')
            except Exception:
                pass

    # Security check
    is_allowed, security_reason = await security_check_before_download(chat_id, raw_url)
    if not is_allowed:
        await update.message.reply_text(f"🚫 {security_reason}")
        conn.close()
        return

    # === Phase 2: Smart Rate Limiting ===
    rate_allowed, rate_msg, rate_details = get_rate_limit_info(chat_id)
    if not rate_allowed:
        await update.message.reply_text(rate_msg)
        conn.close()
        return
    
    # Check fair usage alerts (non-blocking, informational)
    fair_usage_alert = queue_manager.get_fair_usage_alert(chat_id)
    if fair_usage_alert:
        try:
            await update.message.reply_text(fair_usage_alert, parse_mode='Markdown')
        except Exception:
            pass

    norm_url, is_shorts = normalize_and_detect_url(raw_url)
    source = get_source(norm_url)
    is_tiktok = (source == "TikTok")
    file_id = ''.join(random.choices(string.digits, k=settings.random_id_length))

    db.log_to_db(conn, "users", (chat_id, name, username, datetime.datetime.now(datetime.timezone.utc).isoformat()))

    # Removed caching methodology - always download fresh files
    # This prevents database/filesystem mismatches and ensures latest content

    # Fresh download
    async with download_semaphore:
        # Record download start for security monitoring and queue manager
        await record_download_start(chat_id, norm_url)
        queue_manager.record_download_start(chat_id)
        download_start_time = time.time()
        
        # Use enhanced download with retry logic
        success = await download_fresh_enhanced(conn, norm_url, raw_url, source, chat_id, user.id, name, username, file_id, 
                                                is_tiktok, is_shorts, context, update)
        
        # Calculate download duration
        download_duration = time.time() - download_start_time
        
        # Get file size for stats
        file_size_mb = 0
        try:
            # Find the downloaded file
            for f in Path(DOWNLOAD_DIR).glob(f"*{file_id}*"):
                file_size_mb = f.stat().st_size / (1024 * 1024)
                break
        except Exception:
            pass
        
        # Record download completion (both Phase 1 security and Phase 2 queue)
        await record_download_complete(chat_id, norm_url, success)
        queue_manager.record_download_complete(
            chat_id, success=success, 
            duration_s=download_duration, 
            size_mb=file_size_mb
        )
    
    conn.close()

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

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check if user is blocked
    if update.message and update.message.from_user:
        chat_id = update.message.from_user.id
        
        if is_user_blocked(chat_id):
            username = update.message.from_user.username or "Unknown"
            url = update.message.text if hasattr(update.message, 'text') else "Unknown"
            log_blocked_attempt(chat_id, url, username)
            await update.message.reply_text(BLOCK_MESSAGE)
            return
    
    # Extract URLs
    urls = extract_urls(update.message.text)
    if not urls:
        await update.message.reply_text("❌ No valid URLs found.")
        return
    
    # Process each URL
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
    conn = db.get_connection()
    conn.close()
    
    if not settings.bot.token:
        raise SystemExit("❌ BOT_TOKEN env var required")
    
    logger.info(f"Config: MAX_CONCURRENT={settings.rate_limit.max_concurrent}, TIMEOUT={settings.download.timeout_seconds}s, MAX_FILE_SIZE={human_size(settings.rate_limit.max_file_size_bytes)}")
    
    req = HTTPXRequest(connect_timeout=settings.telegram.request_connect_timeout, read_timeout=settings.telegram.request_read_timeout)
    
    app = ApplicationBuilder().token(settings.bot.token).request(req).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # Add user commands
    from user_commands import get_user_command_handlers
    user_handlers = get_user_command_handlers()
    for command, handler in user_handlers:
        app.add_handler(CommandHandler(command, handler))
    
    # Add admin commands
    admin_handlers = get_admin_handlers()
    for command, handler in admin_handlers:
        app.add_handler(CommandHandler(command, handler))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))

def start_bot():
    """Start the bot with enhanced features."""
    # Create app instance
    req = HTTPXRequest(connect_timeout=settings.telegram.request_connect_timeout, read_timeout=settings.telegram.request_read_timeout)
    
    app = ApplicationBuilder().token(settings.bot.token).request(req).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", enhanced_help_command))
    app.add_handler(CommandHandler("status", status_command))
    
    # Add admin commands (Phase 1)
    admin_handlers = get_admin_handlers()
    for command, handler in admin_handlers:
        app.add_handler(CommandHandler(command, handler))
    
    # Add Phase 2 user commands
    user_handlers = get_user_command_handlers()
    for command, handler in user_handlers:
        # Skip 'help' as it's already registered above
        if command != 'help':
            app.add_handler(CommandHandler(command, handler))
    
    # Add callback query handlers for interactive help
    from telegram.ext import CallbackQueryHandler
    callback_handlers = get_callback_handlers()
    for pattern, handler in callback_handlers:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    
    # Enhanced polling with conflict handling
    max_retries = settings.telegram.polling_max_retries
    for attempt in range(max_retries):
        try:
            logger.info(f"Starting polling (attempt {attempt + 1}/{max_retries})...")
            app.run_polling(drop_pending_updates=True)
            break
        except Conflict as e:
            logger.warning(f"Conflict detected: {e}")
            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * settings.telegram.polling_conflict_wait_base
                logger.info(f"Waiting {wait_time}s before retry...")
                time.sleep(wait_time)
            else:
                logger.error("Max retries reached. Bot cannot start due to conflict.")
                raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise


# Enhanced startup
if __name__ == '__main__':
    start_bot()