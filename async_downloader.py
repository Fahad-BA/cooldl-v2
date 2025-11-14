import os, re, random, string, logging, datetime, pytz, sqlite3, asyncio
from pathlib import Path
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

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
COOKIES_FILE = os.getenv("COOKIES_FILE", "").strip()  # optional Netscape cookies.txt

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

# التقط جميع الروابط في النص
URL_RE = re.compile(r'https?://[^\s<>")]+', re.I)

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

        # TikTok: لا تغيّر الدومين/المسار؛ فقط نظّف التتبع
        if "tiktok.com" in netloc:
            q = {k:v for k,v in q.items() if k not in STRIP_KEYS}
            query = urlencode({k:v[0] for k,v in q.items()}) if q else ""
            return urlunparse((scheme, netloc, path, "", query, ""))

        # YouTube short → watch?v=
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

        # X/Instagram: نظّف التتبع فقط
        if netloc.endswith("x.com") or "twitter.com" in netloc or netloc.endswith("instagram.com"):
            q = {k:v for k,v in q.items() if k not in STRIP_KEYS}

        query = urlencode({k:v[0] for k,v in q.items()}) if q else ""
        norm = urlunparse((scheme, netloc, path, "", query, ""))
        return norm[:-1] if norm.endswith("?") else norm
    except Exception:
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
    return [u.rstrip(').,;!?””"\'') for u in urls]

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
      username TEXT
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
      filename TEXT
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
    """)
    c.commit(); c.close()

def log_to_db(table, values):
    c = conn(); cur = c.cursor()
    if table == "downloads":
        cur.execute("""INSERT INTO downloads
            (user_id, url, filename, source, timestamp, chat_id, name, username, file_id)
            VALUES (?,?,?,?,?,?,?,?,?)""", values)
    elif table == "users":
        cur.execute("INSERT OR IGNORE INTO users (chat_id, name, username) VALUES (?,?,?)", values)
    elif table == "errors":
        cur.execute("""INSERT INTO errors (error, file_id, timestamp, username, chat_id, name, url)
                       VALUES (?,?,?,?,?,?,?)""", values)
    elif table == "logs":
        cur.execute("""INSERT INTO logs (timestamp, action, username, chat_id, status)
                       VALUES (?,?,?,?,?)""", values)
    c.commit(); c.close()

def insert_download(user_id, url, filename, source, chat_id, name, username, file_id):
    log_to_db("downloads", (user_id, url, filename, source, now_utc_iso(), chat_id, name, username, file_id))

def find_cached_file(url: str) -> Path | None:
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

def human_size(path: Path) -> str:
    try: sz = path.stat().st_size
    except Exception: return "n/a"
    for unit in ["B","KB","MB","GB","TB"]:
        if sz < 1024 or unit == "TB":
            return f"{sz:.0f}{unit}" if unit=="B" else f"{sz/1024:.2f}{unit}" if unit!="B" else f"{sz}B"
        sz /= 1024

def build_meta_text(file_id, name, username, source, url, path: Path):
    return (f"✅ Downloaded\nID: {file_id}\nUser: {name} ({username})\nSource: {source}\n"
            f"File: {path.name} ({human_size(path)})\nTime: {now_local()}\nURL: {url}")

async def send_with_retry(factory, retries=3, backoff_base=2):
    for i in range(retries):
        try:
            return await factory()
        except TimedOut:
            if i == retries - 1: raise
            await asyncio.sleep(backoff_base * (i + 1))

# إرسال موحّد: للمستخدم أولًا كوثيقة (أسرع)، ثم نسخ للقناة بدون رفع ثاني
async def deliver_file(final_path: Path, source: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    sent_to_user = None

    async def _send_doc(to_chat):
        return await send_with_retry(lambda: context.bot.send_document(
            chat_id=to_chat, document=final_path.open("rb"),
            **doc_args(final_path.stem)
        ))

    async def _send_vid(to_chat):
        return await send_with_retry(lambda: context.bot.send_video(
            chat_id=to_chat, video=final_path.open("rb"),
            **video_args(final_path.stem)
        ))

    # 1) للمستخدم أولاً – document أسرع وأقل timeouts
    try:
        if source == "TikTok":
            sent_to_user = await _send_doc(chat_id)
        else:
            try:
                sent_to_user = await _send_doc(chat_id)
            except Exception:
                sent_to_user = await _send_vid(chat_id)
    except TimedOut:
        # محاولة ثانية أخيرة كوثيقة دائماً
        sent_to_user = await _send_doc(chat_id)

    # 2) للقناة بنسخ نفس الرسالة (بدون رفع)
    if CHANNEL_ID and sent_to_user:
        try:
            await context.bot.copy_message(
                chat_id=CHANNEL_ID,
                from_chat_id=chat_id,
                message_id=sent_to_user.message_id
            )
        except TimedOut:
            # محاولة ثانية
            await context.bot.copy_message(
                chat_id=CHANNEL_ID,
                from_chat_id=chat_id,
                message_id=sent_to_user.message_id
            )

    return sent_to_user is not None

# ================== HANDLERS ==================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a video link to download.")

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Supported: YouTube / TikTok / Instagram / X. Send a URL.")

async def process_single_url(raw_url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()

    norm_url = normalize_url(raw_url)
    cache_key = norm_url

    user = update.message.from_user
    chat_id = update.message.chat_id
    name = user.first_name or "User"
    username = f"@{user.username or 'unknown'}"
    file_id = rand_id()
    source = get_source(norm_url)
    is_tiktok = (source == "TikTok")

    log_to_db("users", (chat_id, name, username))

    # === Cache ===
    cached = find_cached_file(cache_key)
    if cached:
        # ميتاداتا للقناة (غير قاتل)
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

        insert_download(user.id, cache_key, cached.name, source, chat_id, name, username, file_id)
        if raw_url != cache_key:
            insert_download(user.id, raw_url, cached.name, source, chat_id, name, username, file_id)
        return

    # === Download (isolated) ===
    progress_msg = await update.message.reply_text("⏳ Downloading...")
    caplog = CaptureLogger()
    filename = f"File{rand_id()}"
    outtmpl = str(DOWNLOAD_DIR / f"{filename}.%(ext)s")

    ydl_opts = {
        'outtmpl': outtmpl,
        'format': 'bv*+ba/b',                 # غيّرها إذا تبغى MP4 فقط
        'recode-video': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'logger': caplog,
        'retries': 5,
        'concurrent_fragment_downloads': 4,
        'http_headers': {'User-Agent': 'Mozilla/5.0'}
    }
    if is_tiktok:
        ydl_opts['http_headers']['Referer'] = 'https://www.tiktok.com/'
    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        ydl_opts['cookiesfrombrowser'] = None
        ydl_opts['cookiefile'] = COOKIES_FILE

    async def do_download(url_to_use: str) -> Path:
        loop = asyncio.get_running_loop()
        def run():
            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url_to_use, download=True)
                fp = Path(ydl.prepare_filename(info))
                if not fp.exists():
                    matches = list(DOWNLOAD_DIR.glob(f"{filename}.*"))
                    if not matches: raise FileNotFoundError("Output file not found after download.")
                    return matches[0]
                return fp
        return await loop.run_in_executor(None, run)

    try:
        try:
            final_path: Path = await do_download(norm_url)
        except DownloadError as de:
            if "404" in str(de) or "Unable to download webpage" in str(de):
                final_path = await do_download(raw_url)
            else:
                raise
    except Exception as e:
        short_err = f"{type(e).__name__}: {e}"
        err_text = short_err + "\n\n--- yt-dlp log (tail) ---\n" + caplog.tail(40)
        logging.error(f"Download error: {short_err}")
        try: await context.bot.send_message(chat_id=chat_id, text="⚠️ Download failed.")
        except Exception: pass
        try:
            await context.bot.send_message(chat_id=LOG_CHANNEL_ID, text=f"❌ Error\n{name} ({username})\nID:{file_id}\nURL:{norm_url}\n\n{short_err}")
        except Exception: pass
        log_to_db("errors", (err_text, file_id, now_local(), username, chat_id, name, norm_url))
        log_to_db("logs", (now_local(), "DownloadFailed", username, chat_id, "Fail"))
        try: await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
        except Exception: pass
        return

    # === Post-download ===
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=progress_msg.message_id)
    except Exception as e:
        logging.warning(f"delete progress msg failed: {e}")

    # ميتاداتا للقناة (اختياري)
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

    # سجّل
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
        await update.message.reply_text("❌ Invalid URL.")
        return
    for raw_url in urls:
        try:
            await process_single_url(raw_url, update, context)
        except Exception as e:
            logging.exception(f"fatal error processing url {raw_url}: {e}")
            try:
                await update.message.reply_text("⚠️ Unexpected error.")
            except Exception:
                pass

# ================== BOOTSTRAP ==================
if __name__ == '__main__':
    ensure_tables()
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env var is required")
    # مهلة أعلى لتقليل Timeouts أثناء الإرسال
    req = HTTPXRequest(connect_timeout=20, read_timeout=180)
    app = ApplicationBuilder().token(BOT_TOKEN).request(req).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()
