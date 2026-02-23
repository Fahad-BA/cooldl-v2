#!/bin/bash

# CoolDL Bot Startup Script
# Starts both web interface and Telegram bot

cd /home/fahad/cooldl

echo "Starting CoolDL Bot..."

# Kill any existing processes
pkill -f "uvicorn main:app" 2>/dev/null || true
pkill -f "async_downloader.py" 2>/dev/null || true

# Start web interface
echo "Starting web interface on port 8001..."
nohup /home/fahad/cooldl/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8001 > /dev/null 2>&1 &
WEB_PID=$!

# Start Telegram bot
echo "Starting Telegram bot..."
nohup /home/fahad/cooldl/venv/bin/python3 async_downloader.py > /dev/null 2>&1 &
BOT_PID=$!

# Write PIDs to file
echo $WEB_PID > /home/fahad/cooldl/web_pid.txt
echo $BOT_PID > /home/fahad/cooldl/bot_pid.txt

echo "Web interface PID: $WEB_PID"
echo "Telegram bot PID: $BOT_PID"
echo "CoolDL Bot started successfully!"