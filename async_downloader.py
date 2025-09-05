import os, re, random, string, logging, datetime, pytz, sqlite3, asyncio
from pathlib import Path
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "0")) or CHANNEL_ID
CAPTION = os.getenv("CAPTION", "")
DB_PATH = os.getenv("DATABASE", "cooldl.db")

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)

URL_RE = re.compile(r'(https?://\S+)', re.I)

def extract_url(text: str):
    m = URL_RE.search(text or "")
    return m.group(1) if m else None

def get_source(url):
    u = url.lower()
    if "tiktok" in u: return "TikTok"
    if "instagram" in u: return "Instagram"
    if "x.com" in u or "twitter" in u: return "X"
    if "youtube" in u or "youtu.be" in u: return "YouTube"
    return "Unknown"

def rand_id(k=5):
    return ''.join(random.choices(string.digits, k=k))

def now_local():
    return datetime.datetime.now(pytz.timezone('Asia/Riyadh')).strftime('%Y-%m-%d %I:%M %p')

def now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def conn():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
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
      -- قد تكون عندك بدون id أصلاً؛ لا نعتمد عليه
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
    """)
    c.commit(); c.close()

def log_to_db(table, values):
    c = conn(); cur = c.cursor()
    if table == "downloads":
        cur.execute("INSERT INTO downloads (user_id, url, filename, source, timestamp, chat_id, name, username, file_id) VALUES (?,?,?,?,?,?,?,?,?)", values)
    elif table == "users":
        cur.execute("INSERT OR IGNORE INTO users (chat_id, name, username) VALUES (?,?,?)", values)
    elif table == "errors":
        cur.execute("INSERT INTO errors (error, file_id, timestamp, username, chat_id, name, url) VALUES (?,?,?,?,?,?,?)", values)
    elif table == "logs":
        cur.execute("INSERT INTO logs (timestamp, action, username, chat_id, status) VALUES (?,?,?,?,?)", values)
    c.commit(); c.close()

def insert_download(user_id, url, filename, source, chat_id, name, username, file_id):
    log_to_db("downloads", (user_id, url, filename, source, now_utc_iso(), chat_id, name, username, file_id))

def find_cached_file(url: str) -> Path | None:
    c = conn(); cur = c.cursor()
    try:
        # لا تعتمد على عمود id — استخدم ROWID
        cur.execute("SELECT filename FROM downloads WHERE url=? ORDER BY ROWID DESC LIMIT 1", (url,))
        row = cur.fetchone()
    finally:
        c.close()
    if not row: return None
    fp = DOWNLOAD_DIR / (row["filename"] or "")
    return fp if fp.exists() else None

class CaptureLogger:
    def __init__(self): self.buf = []
    def debug(self, msg): self.buf.append(str(msg))
    def warning(self, msg): self.buf.append(f"[W] {msg}")
    def error(self, msg): self.buf.append(f"[E] {msg}")
    def tail(self, n=120): return "\n".join(self.buf[-n:])

def make_send_args(fp: Path, title: str = ""):
    return dict(caption=(CAPTION or title[:950]), supports_streaming=True)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a video link to download.")

async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send a YouTube/TikTok/Instagram/X Link.")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ensure_tables()

    url = extract_url(update.message.text)
    if not url:
        return await update.message.reply_text("❌ Invalid Link.")

    user = update.message.from_user
    chat_id = update.message.chat_id
    name = user.first_name or "User"
    username = f"@{user.username or 'unknown'}"
    file_id = rand_id()
    source = get_source(url)

    log_to_db("users", (chat_id, name, username))

    cached = find_cached_file(url)
    if cached:
        try:
            args = make_send_args(cached, cached.stem)
            try:
                await context.bot.send_video(chat_id=chat_id, video=cached.open("rb"), **args)
            except Exception:
                await context.bot.send_document(chat_id=chat_id, document=cached.open("rb"), **args)

            if CHANNEL_ID:
                try:
                    await context.bot.send_document(
                        chat_id=CHANNEL_ID,
                        document=cached.open("rb"),
                        caption=f"ID:{file_id} | {name} ({username}) | {source}\n{url}"
                    )
                except Exception:
                    pass
            insert_download(user.id, url, cached.name, source, chat_id, name, username, file_id)
            log_to_db("logs", (now_local(), "SentFromCache", username, chat_id, "Success"))
            return
        except Exception as e:
            logging.warning(f"Cache send failed, fallback to download: {e}")

    msg = await update.message.reply_text("⏳ Downloading...")

    caplog = CaptureLogger()
    filename = f"File{rand_id()}"
    outtmpl = str(DOWNLOAD_DIR / f"{filename}.%(ext)s")
    opts = {
        'outtmpl': outtmpl,
        'format': 'bv*+ba/b',
        'noplaylist': True,
        'quiet': True,
        'logger': caplog,
        'retries': 5,
        'concurrent_fragment_downloads': 4,
        'http_headers': {'User-Agent': 'Mozilla/5.0'}
    }

    try:
        loop = asyncio.get_running_loop()
        def run_download():
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                final_path = Path(ydl.prepare_filename(info))
                if not final_path.exists():
                    matches = list(DOWNLOAD_DIR.glob(f"{filename}.*"))
                    if not matches:
                        raise FileNotFoundError("Output file not found after download.")
                    final_path = matches[0]
                return final_path

        final_path: Path = await loop.run_in_executor(None, run_download)

        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)

        args = make_send_args(final_path, final_path.stem)
        try:
            await context.bot.send_video(chat_id=chat_id, video=final_path.open("rb"), **args)
        except Exception:
            await context.bot.send_document(chat_id=chat_id, document=final_path.open("rb"), **args)

        if CHANNEL_ID:
            try:
                await context.bot.send_document(
                    chat_id=CHANNEL_ID,
                    document=final_path.open("rb"),
                    caption=f"ID:{file_id} | {name} ({username}) | {source}\n{url}"
                )
            except Exception:
                pass

        insert_download(user.id, url, final_path.name, source, chat_id, name, username, file_id)
        log_to_db("logs", (now_local(), "Downloaded", username, chat_id, "Success"))

    except Exception as e:
        err_text = f"{type(e).__name__}: {e}\n\n--- yt-dlp log (tail) ---\n{caplog.tail(120)}"
        logging.error(f"Download error: {err_text}")

        try:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Download Failed.")
        except Exception:
            pass

        try:
            await context.bot.send_message(
                chat_id=LOG_CHANNEL_ID,
                text=f"❌ Error\n{name} ({username})\nID:{file_id}\nURL:{url}\n\n{err_text}"
            )
        except Exception:
            pass

        log_to_db("errors", (err_text, file_id, now_local(), username, chat_id, name, url))
        log_to_db("logs", (now_local(), "DownloadFailed", username, chat_id, "Fail"))

if __name__ == '__main__':
    ensure_tables()
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN env var is required")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()
