# 🚀 CoolDL Bot - Ultimate Video Downloader Bot

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0-blue?style=for-the-badge&logo=github&logoColor=white" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11%2B-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge&logo=github&logoColor=white" alt="License">
  <img src="https://img.shields.io/badge/platform-linux-lightgrey?style=for-the-badge&logo=linux&logoColor=white" alt="Platform">
  <img src="https://img.shields.io/badge/python--telegram--bot-20.7-blue?style=for-the-badge&logo=telegram&logoColor=white" alt="python-telegram-bot">
  <img src="https://img.shields.io/badge/yt--dlp-2023.12.30-red?style=for-the-badge&logo=youtube&logoColor=white" alt="yt-dlp">
  <img src="https://img.shields.io/badge/vibe_coded-purple?style=for-the-badge&logo=sparkles&logoColor=white" alt="Vibe Coded">
</p>

<p align="center">
  <em>A powerful, self-hosted Telegram bot for downloading videos from multiple platforms with real-time dashboard monitoring - Now vibe-coded!</em>
</p>

<p align="center">
  <a href="https://t.me/CoolDLBot"><strong>🤖 Try the Bot</strong></a> •
  <a href="#-installation"><strong>📖 Installation</strong></a> •
  <a href="#-features"><strong>✨ Features</strong></a> •
  <a href="#-use-cases"><strong>🎯 Use Cases</strong></a>
</p>

---

## 🎯 **About This Project**

**CoolDL Bot** is a sophisticated, self-hosted video downloader bot that seamlessly integrates with Telegram to provide lightning-fast video downloads from multiple social media platforms. What started as a simple downloader has evolved into a comprehensive system with advanced user management, real-time monitoring, and intelligent blocking capabilities.

**🌟 Now Vibe-Coded:** This project has been meticulously crafted with attention to detail, intuitive design, and a focus on user experience - that's the essence of vibe-coding!

---

## ✨ Features

### 🎥 **Multi-Platform Support**
- **TikTok** ⚡ - High-speed downloads with age-restriction bypass
- **Instagram** 📸 - Reels, Stories, and media support
- **Twitter/X** 🐦 - Video and media downloads
- **Snapchat** 👻 - Media extraction support
- **Tumblr** 🎭 - Video and media downloads

### 🛡️ **Advanced Security & Management**
- **User Blocking System** 🚫 - Comprehensive admin controls with real-time monitoring
- **Smart Rate Limiting** ⏱️ - Tier-based limits (10-20/hour) with trust scoring and predictive behavior analysis
- **Error Recovery System** 🛠️ - Smart retry logic with exponential backoff and error classification
- **Security Manager** 🛡️ - Suspicious pattern detection, URL safety validation, and user risk scoring
- **File Management** 📁 - Automated cleanup with disk space monitoring and file protection
- **Queue Manager** 📋 - Priority-based download queue with user tiers (NEW, REGULAR, TRUSTED, VIP)
- **URL Validator** 🔗 - Pre-download URL analysis with platform detection and content type prediction
- **Session Management** 🔐 - Secure user sessions with IP tracking

### 📊 **Real-Time Dashboard**
- **Live Statistics** 📈 - Monitor downloads, users, errors, and top sources
- **Interactive Charts** 📊 - Beautiful data visualizations using Chart.js
- **User Analytics** 👥 - Track individual download patterns with 270+ active users
- **Error Monitoring** 🔍 - Real-time error logs with detailed timestamps
- **User Management Table** 📋 - Complete user directory with search functionality
- **Performance Metrics** ⚡ - System health and performance indicators

### 🎨 **Modern UI/UX**
- **Responsive Design** 📱 - Works seamlessly on all devices
- **Dark Theme** 🌙 - Easy on the eyes for extended use
- **Real-time Updates** ⚡ - Live data refresh without page reloads
- **Interactive Tables** 📊 - Sortable, searchable data tables
- **Search Filters** 🔍 - Advanced filtering for users and downloads

---

## 🎯 **Use Cases**

### 📱 **Social Media Archiving**
- Save TikTok videos before they're deleted
- Archive Instagram Stories and Reels
- Download Twitter/X threads and media
- Preserve Snapchat memories

### 🎓 **Educational Content**
- Download tutorial videos for offline viewing
- Save educational TikToks and Instagram content
- Archive webinars and online courses
- Create offline learning libraries

### 💼 **Content Creation**
- Download source videos for editing
- Save inspirational content for mood boards
- Archive competitor content for analysis
- Build video reference libraries

### 🏢 **Business Applications**
- Monitor competitor content strategies
- Save client-approved videos for portfolios
- Archive brand-related social media content
- Create content databases for marketing teams

---

## 🚀 Quick Start

### 📋 **Prerequisites**
```bash
# Python 3.11+
python --version

# Git (for cloning)
git --version

# System packages (Ubuntu/Debian)
sudo apt update
sudo apt install python3-pip ffmpeg
```

### 🛠️ **Installation**

1. **Clone the repository**
```bash
git clone https://github.com/Fahad-BA/cooldl-v2.git
cd cooldl-v2
```

2. **Create virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Set up environment variables**
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. **Initialize database**
```bash
python3 -c "from db import setup_database; setup_database()"
```

6. **Start the bot**
```bash
# Option A: Enhanced startup (recommended - includes Phase 1 & 2 systems)
python3 enhanced_startup.py

# Option B: Manual start
python3 async_downloader.py &  # Telegram bot
python3 -m uvicorn main:app --host 0.0.0.0 --port 8001  # Web dashboard
```

### 🔧 **Configuration**

Create a `.env` file in the project root (see `.env.example` for all options):

```env
# Bot Settings
BOT_TOKEN=your_telegram_bot_token
CHANNEL_ID=0
LOG_CHANNEL_ID=0
CAPTION=

# Database Settings
DATABASE=cooldl.db
DB_CONNECTION_TIMEOUT=20
DB_JOURNAL_MODE=WAL

# Rate Limiting & Concurrency
MAX_DOWNLOADS_PER_HOUR=10
MAX_CONCURRENT=3
MAX_FILE_SIZE=500  # MB
FILE_RETENTION_DAYS=7

# Download Settings
DOWNLOAD_TIMEOUT=300
DOWNLOAD_RETRIES=5
CONCURRENT_FRAGMENTS=4

# Web Dashboard
SESSION_SECRET=your_secret_key_here
ADMIN_USERNAME=admin
ADMIN_PASSWORD=your_password_here

# Admin Telegram IDs (comma-separated, for bot admin commands)
ADMIN_IDS=123456789,987654321

# General
LOG_LEVEL=INFO
TIMEZONE=Asia/Riyadh
CLEANUP_ENABLED=false
CLEANUP_INTERVAL_HOURS=24
```

---

## 📊 **Dashboard Features**

### 🔍 **Users Management**
- **Complete User Directory** with 270+ active users
- **Advanced Search** by display name or username
- **Real-time Statistics** showing downloads per user
- **Direct Telegram Links** to user profiles
- **Export capabilities** for user analytics

### 🛡️ **Admin Panel**
- **Block/Unblock Users** with detailed logging
- **Real-time Monitoring** of user activities
- **Error Log Management** with search and filtering
- **System Statistics** and performance metrics
- **User Activity Tracking** with timestamps

### 📈 **Analytics**
- **Download Statistics** by platform and user
- **Error Rate Analysis** with trend detection
- **User Growth Tracking** over time
- **Performance Metrics** for system optimization
- **Custom Reports** generation

---

## 🛠️ **API & Integration**

### 🔌 **Bot Commands**
- **Basic Usage**: Send a video URL to download
- **Help**: `/help` - Interactive help menu with platform guides, commands, examples, and FAQ
- **User Commands**:
  - `/stats` - Personal download statistics (total, by platform, success rate)
  - `/queue` - Download queue status and estimated wait time
  - `/commands` - List available commands based on your access level
- **Admin Commands**:
  - `/health` - System health dashboard (CPU, memory, disk, database, security)
  - `/cleanup` - File management (dry-run, execute, scan, statistics modes)
  - `/security` - Security dashboard (overview, user lookup, events, cleanup)
  - `/block <user>` - Block a user
  - `/unblock <user>` - Unblock a user
  - `/blocked` - Show blocked users list
  - `/check <user>` - Check user status

### 🌐 **Web API**
```python
# Dashboard (HTML)
GET /dashboard

# Health check
GET /healthz

# Authentication
GET /login
POST /login
GET /logout

# API endpoints (JSON)
GET /api/downloads    # Recent downloads
GET /api/errors       # Error logs
GET /api/users        # Users data

# Admin actions
POST /download        # Trigger download from dashboard
POST /restart-bot     # Restart the bot process
```

---

## 🏗️ **Architecture**

### 🔄 **System Components**
```
┌─────────────────────┐    ┌─────────────────────┐    ┌─────────────────────┐
│    Telegram Bot     │────│    Web Dashboard    │────│    SQLite Database  │
│ (async_downloader)  │    │     (FastAPI)       │    │    (cooldl.db)      │
└─────────────────────┘    └─────────────────────┘    └─────────────────────┘
         │                          │                          │
         └──────────────────────────┼──────────────────────────┘
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  Error Recovery  │   │  File Manager    │   │ Security Manager │
│(error_recovery)  │   │ (file_manager)   │   │(security_manager)│
└──────────────────┘   └──────────────────┘   └──────────────────┘
          │                         │                         │
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│  URL Validator   │   │  Queue Manager   │   │   DB Layer       │
│ (url_validator)  │   │ (queue_manager)  │   │     (db.py)      │
└──────────────────┘   └──────────────────┘   └──────────────────┘
          │
┌──────────────────┐   ┌──────────────────┐
│  User Commands   │   │ Blocking System  │
│ (user_commands)  │   │   (blocks.py)    │
└──────────────────┘   └──────────────────┘
```

### 🎯 **Key Features**
- **Self-Hosted**: Complete control over your data and privacy
- **Scalable**: Handles multiple concurrent downloads efficiently
- **Secure**: Multi-layered security with user authentication, trust scoring, and admin controls
- **Extensible**: Easy to add new platforms and features
- **Reliable**: Smart error recovery with automatic retry logic
- **Smart Queue**: Priority-based download queue with user tier system
- **Intelligent URL Validation**: Pre-download analysis and platform detection

---

## 🔧 **Development**

### 🤝 **Contributing**
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### 🐛 **Debugging**
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# View bot logs
tail -f async_downloader.log

# View dashboard logs
tail -f server.log
```

> **Note:** For details on Phase 1 & 2 enhancements, see [ENHANCEMENT_LOG.md](ENHANCEMENT_LOG.md)

---

## 📜 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 **Acknowledgments**

- **Telegram Bot API** for the amazing bot platform
- **yt-dlp** for the robust video downloading capabilities
- **FastAPI** for the lightning-fast web framework
- **Chart.js** for beautiful data visualizations
- **All Contributors** who helped improve this project

---

## 📧 **Contact**

**Developer**: Fahad Alhuqaili

- 🐦 **Twitter/X**: [@falhuqaili](https://twitter.com/falhuqaili)
- 💼 **LinkedIn**: [/in/fahad-alhuqaili](https://linkedin.com/in/fahad-alhuqaili)
- 📧 **Email**: [Fahad@Alhuqaili.com](mailto:Fahad@Alhuqaili.com)
- 🤖 **Bot**: [t.me/CoolDLBot](https://t.me/CoolDLBot)

---

## ⭐ **Star History**

[![Star History Chart](https://api.star-history.com/svg?repos=Fahad-BA/cooldl-v2&type=Date)](https://star-history.com/#Fahad-BA/cooldl-v2&Date)

---

<p align="center">
  <em>Made with ❤️ by Fahad Alhuqaili | Now Vibe-Coded ✨</em>
</p>