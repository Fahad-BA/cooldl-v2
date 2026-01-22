import yt_dlp
import asyncio
import logging
from pathlib import Path
import sqlite3
import os
import datetime
from typing import Optional

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DATABASE", "cooldl.db")
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True, parents=True)

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
DOWNLOAD_TIMEOUT = 300  # 5 minutes
MAX_CONCURRENT_DOWNLOADS = 3

download_semaphore = asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)

def db():
    c = sqlite3.connect(DB_PATH, check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c

def now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def find_cached_file(url: str) -> Optional[Path]:
    c = db()
    cur = c.cursor()
    try:
        cur.execute("SELECT filename FROM downloads WHERE url=? AND status='completed' ORDER BY ROWID DESC LIMIT 1", (url,))
        row = cur.fetchone()
    finally:
        c.close()
    
    if not row:
        return None
    
    fp = DOWNLOAD_DIR / (row["filename"] or "")
    # Verify file still exists and has reasonable size
    if fp.exists() and fp.stat().st_size > 0 and fp.stat().st_size <= MAX_FILE_SIZE:
        return fp
    
    logger.warning(f"Cached file missing or invalid: {fp}")
    return None

def insert_download(user_id: int, url: str, filename: str, status: str = "pending", source: str = "web"):
    c = db()
    cur = c.cursor()
    try:
        cur.execute("""INSERT INTO downloads (user_id, url, filename, status, source, timestamp) 
                      VALUES (?, ?, ?, ?, ?, ?)""",
                    (user_id, url, filename, status, source, now_utc_iso()))
        c.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
    finally:
        c.close()

def update_download_status(url: str, status: str):
    c = db()
    cur = c.cursor()
    try:
        cur.execute("UPDATE downloads SET status=? WHERE url=?", (status, url))
        c.commit()
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
    finally:
        c.close()

async def download_video(url: str, user_id: int = 0, timeout: int = DOWNLOAD_TIMEOUT) -> Optional[str]:
    """Download video with improved error handling and caching."""
    
    # Check cache first
    cached = find_cached_file(url)
    if cached:
        logger.info(f"Using cached file: {cached}")
        return str(cached)
    
    async with download_semaphore:
        insert_download(user_id, url, "", "pending")
        
        try:
            loop = asyncio.get_event_loop()
            file_path = await asyncio.wait_for(
                loop.run_in_executor(None, _download_with_ydl, url),
                timeout=timeout
            )
            
            update_download_status(url, "completed")
            insert_download(user_id, url, Path(file_path).name, "completed", "web")
            logger.info(f"Download successful: {file_path}")
            return file_path
            
        except asyncio.TimeoutError:
            logger.error(f"Download timeout for {url}")
            update_download_status(url, "timeout")
            return None
        except Exception as e:
            logger.error(f"Download failed for {url}: {str(e)}")
            update_download_status(url, "failed")
            return None

def _download_with_ydl(url: str) -> str:
    """Helper function to run yt-dlp download."""
    opts = {
        'outtmpl': str(DOWNLOAD_DIR / "File%(id)s.%(ext)s"),
        'format': 'bv*+ba/b',
        'quiet': False,
        'noplaylist': True,
        'max_filesize': MAX_FILE_SIZE,
        'socket_timeout': 30,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
    }
    
    # Add TikTok impersonation for age-restricted content
    if 'tiktok.com' in url or 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
        opts['extractor_args'] = {'tiktok': ['impersonate=webkit']}
        opts['http_headers']['Referer'] = 'https://www.tiktok.com/'
    
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        fp = Path(ydl.prepare_filename(info))
        
        if not fp.exists():
            matches = list(DOWNLOAD_DIR.glob("File*.*"))
            if not matches:
                raise FileNotFoundError("Output file not found after download.")
            fp = matches[-1]
        
        return str(fp)