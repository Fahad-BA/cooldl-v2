"""
URL utilities for CoolDL Telegram bot.

Provides URL normalization, extraction, source detection, and related utilities.
"""

import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from typing import Tuple
import datetime
import logging

logger = logging.getLogger(__name__)

# Constants
URL_RE = re.compile(r'https?://[^\s<>")]+', re.I)
STRIP_KEYS = {"utm_source","utm_medium","utm_campaign","utm_term","utm_content","utm_id",
              "_t","_r","s","si","igsh","igshid","feature","fbclid","app", "m",
              "cshid", "pp", "sns", "share"}


def normalize_and_detect_url(raw_url: str) -> Tuple[str, bool]:
    """Normalize URL and detect if it's a YouTube short.
    
    Args:
        raw_url: The raw URL string to normalize
        
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


def extract_urls(text: str) -> list[str]:
    """Extract URLs from text.
    
    Args:
        text: Text to extract URLs from
        
    Returns:
        List of URLs found in text
    """
    if not text: 
        return []
    urls = URL_RE.findall(text)
    return [u.rstrip(').,;!?"""\'') for u in urls]


def get_source(url: str) -> str:
    """Detect the source platform from URL.
    
    Args:
        url: URL to analyze
        
    Returns:
        Source platform name (TikTok, Instagram, X, YouTube, Unknown)
    """
    u = url.lower()
    if "tiktok.com" in u: 
        return "TikTok"
    if "instagram" in u: 
        return "Instagram"
    if "x.com" in u or "twitter.com" in u: 
        return "X"
    if "youtube" in u or "youtu.be" in u: 
        return "YouTube"
    return "Unknown"


def human_size(sz: int) -> str:
    """Convert bytes to human-readable format.
    
    Args:
        sz: Size in bytes
        
    Returns:
        Human-readable size string (e.g., "1.23MB")
    """
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