"""
CoolDL Telegram Bot Package

This package contains the decomposed modules from the original async_downloader.py monolith.
Each module focuses on a specific responsibility:

- handlers.py: Telegram message and command handlers
- url_utils.py: URL normalization, extraction, and source detection
- downloader.py: yt-dlp download logic
- delivery.py: File delivery to users and channels
- rate_limit.py: Rate limiting logic
- run.py: Bot bootstrap and main entry point
"""