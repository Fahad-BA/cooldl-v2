#!/bin/bash
# Change to script directory to ensure relative paths work
cd "$(dirname "$0")"
echo "🔄 Restarting CoolDL services..."

# Function to get current PIDs
get_pids() {
    WEB_PID=$(pgrep -f "uvicorn main:app" | head -1)
    BOT_PID=$(pgrep -f "async_downloader.py" | head -1)
    echo "Current PIDs - Web: $WEB_PID, Bot: $BOT_PID"
}

# Get current PIDs before restart
echo "📊 Current running processes:"
get_pids

# Stop services using systemctl (clean way)
echo "🛑 Stopping services via systemctl..."
echo "213325" | sudo -S systemctl stop cooldl-bot.service 2>/dev/null || true
echo "213325" | sudo -S systemctl stop cooldl-web.service 2>/dev/null || true

# Wait for services to stop
sleep 3

# Kill any remaining processes
echo "🔪 Killing any remaining processes..."
pkill -f "uvicorn main:app" || true
pkill -f "async_downloader.py" || true

# Wait for processes to die
sleep 2

# Kill any process still running on port 8000 (force kill)
echo "💥 Force killing port 8000..."
echo "213325" | sudo -S lsof -ti:8000 | xargs kill -9 2>/dev/null || true
sleep 1

# Start services via systemctl (recommended way)
echo "🚀 Starting services via systemctl..."
echo "213325" | sudo -S systemctl start cooldl-web.service 2>/dev/null || true
echo "213325" | sudo -S systemctl start cooldl-bot.service 2>/dev/null || true

# Wait for services to start
sleep 3

# Check if services are running
echo "✅ Checking service status..."
WEB_STATUS=$(echo "213325" | sudo -S systemctl is-active cooldl-web.service 2>/dev/null || echo "unknown")
BOT_STATUS=$(echo "213325" | sudo -S systemctl is-active cooldl-bot.service 2>/dev/null || echo "unknown")

echo "📊 Service Status:"
echo "   Web Service: $WEB_STATUS"
echo "   Bot Service: $BOT_STATUS"

# If systemctl failed, start manually
if [ "$WEB_STATUS" != "active" ]; then
    echo "⚠️  Web service not active, starting manually..."
    source venv/bin/activate
    nohup uvicorn main:app --host 0.0.0.0 --port 8000 > web.log 2>&1 &
    WEB_PID=$!
    echo "✅ Web service started manually (PID: $WEB_PID)"
fi

if [ "$BOT_STATUS" != "active" ]; then
    echo "⚠️  Bot service not active, starting manually..."
    if [ -f "async_downloader.py" ]; then
        source venv/bin/activate
        nohup python async_downloader.py > bot.log 2>&1 &
        BOT_PID=$!
        echo "✅ Bot service started manually (PID: $BOT_PID)"
    fi
fi

# Final status check
echo ""
echo "🔥 Services restarted!"
echo "📊 Final process status:"
get_pids
echo ""
echo "📝 Logs:"
echo "   Web logs: tail -f web.log"
echo "   Bot logs: tail -f bot.log"
echo "   System logs: journalctl -u cooldl-web -u cooldl-bot -f"
