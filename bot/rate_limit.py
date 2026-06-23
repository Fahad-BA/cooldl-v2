"""
Rate limiting and resource management for CoolDL Telegram bot.
"""

import datetime
import asyncio
from collections import defaultdict
from typing import Tuple

import logging
from config import settings

logger = logging.getLogger(__name__)

# Global rate limiting state
user_download_tracker = defaultdict(list)  # chat_id -> [timestamps]
download_semaphore = asyncio.Semaphore(settings.rate_limit.max_concurrent)


def check_rate_limit(chat_id: int) -> Tuple[bool, str]:
    """Check if user exceeded download limit.
    
    Args:
        chat_id: Telegram chat ID to check
        
    Returns:
        Tuple of (allowed, message). If allowed=True, message is empty.
    """
    now = datetime.datetime.now()
    hour_ago = now - datetime.timedelta(hours=1)
    
    # Clean old entries
    user_download_tracker[chat_id] = [ts for ts in user_download_tracker[chat_id] if ts > hour_ago]
    
    if len(user_download_tracker[chat_id]) >= settings.rate_limit.max_downloads_per_hour:
        return False, f"⏱️ Rate limit: max {settings.rate_limit.max_downloads_per_hour} downloads/hour. Try again later."
    
    return True, ""


def record_download(chat_id: int) -> None:
    """Record download timestamp for rate limiting.
    
    Args:
        chat_id: Telegram chat ID that downloaded something
    """
    user_download_tracker[chat_id].append(datetime.datetime.now())


async def get_download_semaphore():
    """Get the download semaphore for concurrent download limiting.
    
    Returns:
        Asyncio Semaphore for managing concurrent downloads
    """
    return download_semaphore