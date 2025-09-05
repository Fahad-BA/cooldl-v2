import yt_dlp
import asyncio
from pathlib import Path
import sqlite3
import os
import datetime

DB_PATH = os.getenv("DATABASE", "cooldl.db")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def find_cached_file(url: str) -> Path | None:
    c = db(); cur = c.cursor()
    try:
        cur.execute("SELECT filename FROM downloads WHERE url=? ORDER BY ROWID DESC LIMIT 1", (url,))
        row = cur.fetchone()
    finally:
        c.close()
    if not row: return None
    fp = DOWNLOAD_DIR / (row["filename"] or "")
    return fp if fp.exists() else None

def insert_download(user_id, url, filename, source="web"):
    c = db(); cur = c.cursor()
    cur.execute("INSERT INTO downloads (user_id,url,filename,source,timestamp) VALUES (?,?,?,?,?)",
                (user_id, url, filename, source, now_utc_iso()))
    c.commit(); c.close()

async def download_video(url: str):
    cached = find_cached_file(url)
    if cached:
        return str(cached)

    def run():
        opts = {
            'outtmpl': str(DOWNLOAD_DIR / "File%(id)s.%(ext)s"),
            'format': 'bv*+ba/b',
            'quiet': True,
            'noplaylist': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0'}
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            fp = Path(ydl.prepare_filename(info))
            if not fp.exists():
                matches = list(DOWNLOAD_DIR.glob("File*.*"))
                if not matches:
                    raise FileNotFoundError("Output file not found after download.")
                fp = matches[-1]
            return str(fp)

    loop = asyncio.get_event_loop()
    file_path = await loop.run_in_executor(None, run)

    insert_download(0, url, Path(file_path).name, "web")
    return file_path
