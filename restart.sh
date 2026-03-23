#!/bin/bash
# Change to script directory to ensure relative paths work
cd "$(dirname "$0")"
echo "🔄 Restarting CoolDL services..."
echo "🔐 Sudo password: 213325"

# Use sudo with password for systemctl (if services exist)
echo "213325" | sudo -S systemctl restart cooldl-bot.service 2>/dev/null || true
echo "213325" | sudo -S systemctl restart cooldl-web.service 2>/dev/null || true

# Also kill any remaining processes
pkill -f "uvicorn main:app" || true
sleep 2

# Kill any process still running on port 8000
echo "213325" | sudo -S lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1

# Start the web service in background
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > web.log 2>&1 &
WEB_PID=$!

echo "✅ Web service started (PID: $WEB_PID)"

# Check if async_downloader.py exists and restart it
if [ -f "async_downloader.py" ]; then
    pkill -f "async_downloader.py" || true
    sleep 1
    nohup python async_downloader.py > bot.log 2>&1 &
    BOT_PID=$!
    echo "✅ Bot service started (PID: $BOT_PID)"
fi

echo "🔥 All services restarted successfully!"
echo "📝 Web logs: tail -f web.log"
echo "📝 Bot logs: tail -f bot.log"
