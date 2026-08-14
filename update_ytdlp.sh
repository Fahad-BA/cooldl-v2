#!/bin/bash
# Weekly yt-dlp update + restart cooldl-bot
# Created: 2026-08-05

LOG="/home/fahad/cooldl/ytdlp_update.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting yt-dlp update..." >> "$LOG"

/home/fahad/cooldl/venv/bin/pip install --upgrade yt-dlp >> "$LOG" 2>&1

# Restart regardless — picks up new version
sudo systemctl restart cooldl-bot.service >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done. Version: $(/home/fahad/cooldl/venv/bin/yt-dlp --version)" >> "$LOG"
echo "---" >> "$LOG"
