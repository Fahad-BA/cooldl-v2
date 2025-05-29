import yt_dlp
import asyncio
import os
import random
import string

def random_filename(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

async def download_video(url):
    filename = random_filename()
    output_path = f"downloads/{filename}.%(ext)s"
    opts = {
        'outtmpl': output_path,
        'format': 'best',
        'quiet': True,
        'noplaylist': True
    }

    try:
        loop = asyncio.get_event_loop()
        def run_yt():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return ydl.prepare_filename(info)
        file_path = await loop.run_in_executor(None, run_yt)
        return file_path
    except Exception as e:
        print(f"[Download Error]: {e}")
        return None
