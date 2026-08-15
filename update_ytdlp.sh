#!/bin/bash
# Weekly yt-dlp update for cooldl + discordbot, then restart both services
# Created: 2026-08-05 | Updated: 2026-08-15 (added Discord bot + moved to 3:30 AM)

LOG="/home/fahad/cooldl/ytdlp_update.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting weekly yt-dlp update..." >> "$LOG"

# --- cooldl venv ---
/home/fahad/cooldl/venv/bin/pip install --upgrade yt-dlp >> "$LOG" 2>&1
echo "[cooldl] now at: $(/home/fahad/cooldl/venv/bin/yt-dlp --version)" >> "$LOG"

# --- Discord bot venv ---
/home/fahad/Discord/venv/bin/pip install --upgrade yt-dlp >> "$LOG" 2>&1
echo "[discordbot] now at: $(/home/fahad/Discord/venv/bin/yt-dlp --version)" >> "$LOG"

# Restart regardless — picks up new version
sudo systemctl restart cooldl-bot.service >> "$LOG" 2>&1
sudo systemctl restart discordbot.service >> "$LOG" 2>&1

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Done." >> "$LOG"
echo "---" >> "$LOG"
