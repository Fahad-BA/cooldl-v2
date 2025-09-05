import os, re, random, string, logging, datetime, pytz, sqlite3, asyncio
from telegram import Update, Bot
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from yt_dlp import YoutubeDL
from dotenv import load_dotenv

# تحميل المتغيرات من .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
CAPTION = os.getenv("CAPTION")
DB_PATH = os.getenv("DATABASE")

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)


def extract_url(text):
    match = re.search(r'(https?://\S+)', text)
    return match.group(1) if match else None

def get_source(url):
    if "tiktok" in url: return "TikTok"
    if "instagram" in url: return "Instagram"
    if "x.com" in url or "twitter" in url: return "X"
    if "youtube" in url or "youtu.be" in url: return "YouTube"
    return "Unknown"

def rand_id():
    return ''.join(random.choices(string.digits, k=5))

def now():
    return datetime.datetime.now(pytz.timezone('Asia/Riyadh')).strftime('%Y-%m-%d %I:%M %p')

def download_video(url, opts):
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return info.get("ext", "mp4")

def log_to_db(table, values):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    if table == "downloads":
        c.execute("INSERT INTO downloads (file_id, timestamp, username, chat_id, name, url, source) VALUES (?, ?, ?, ?, ?, ?, ?)", values)
    elif table == "users":
        c.execute("INSERT OR IGNORE INTO users (chat_id, name, username) VALUES (?, ?, ?)", values)
    elif table == "errors":
        c.execute("INSERT INTO errors (file_id, timestamp, username, chat_id, name, url) VALUES (?, ?, ?, ?, ?, ?)", values)
    elif table == "logs":
        c.execute("INSERT INTO logs (timestamp, action, username, chat_id, status) VALUES (?, ?, ?, ?, ?)", values)
    conn.commit()
    conn.close()

def insert_download(user_id, url, filename, source="telegram"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO downloads (user_id, url, filename, source, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, url, filename, source, datetime.datetime.now(datetime.timezone.utc).isoformat()))
    conn.commit()
    conn.close()

async def start(update, ctx):
    await update.message.reply_text(f"Hey {update.message.chat.first_name}! Send a video link.")

async def help_command(update, ctx):
    await update.message.reply_text("Send a YouTube Shorts or Instagram Reels link.")

async def handle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"📨 from: {update.message.from_user.username} | {update.message.text}")
    url = extract_url(update.message.text or "")
    if not url:
        return await update.message.reply_text("❌ Invalid link. Try again.")

    user = update.message.from_user
    chat_id = update.message.chat_id
    name = user.first_name or "User"
    username = f"@{user.username or 'unknown'}"
    file_id = rand_id()
    filename = f'File{rand_id()}'
    sent = False
    source = get_source(url)

    msg = await update.message.reply_text("⏳Downloading...")
    opts = {'outtmpl': f'downloads/{filename}.%(ext)s', 'format': 'best'}

    try:
        loop = asyncio.get_running_loop()
        ext = await loop.run_in_executor(None, download_video, url, opts)
        filepath = f"downloads/{filename}.{ext}"
        insert_download(user.id, url, f"{filename}.{ext}", source)

        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)

        with open(filepath, 'rb') as f:
            await context.bot.send_video(chat_id=chat_id, video=f, caption=CAPTION, supports_streaming=True)
            sent = True

        with open(filepath, 'rb') as f:
            await context.bot.send_video(chat_id=CHANNEL_ID, video=f, caption=f"ID: {file_id} | [{name}]({username}) | Source: [{source}]({url})", parse_mode='Markdown', supports_streaming=True)

        log_to_db("downloads", (file_id, now(), username, chat_id, name, url, source))
        log_to_db("users", (chat_id, name, username))
        log_to_db("logs", (now(), "Downloaded", username, chat_id, "Success"))

    except Exception as e:
        logging.error(f"Download error: {e}")
        if not sent:
            await context.bot.send_message(chat_id=chat_id, text="⚠️ Couldn't download.")
            await context.bot.send_message(chat_id=CHANNEL_ID, text=f"❌ Error\n[{name}]({username})\nID: {file_id}", parse_mode='Markdown')
        log_to_db("errors", (file_id, now(), username, chat_id, name, url))
        log_to_db("logs", (now(), "Download Failed", username, chat_id, "Fail"))

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle))
    app.run_polling()
