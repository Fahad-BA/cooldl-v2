#!/bin/bash
echo "🔄 Restarting CoolDL services..."
sudo systemctl restart cooldl-bot.service
sudo systemctl restart cooldl-web.service
echo "✅ Done!"
