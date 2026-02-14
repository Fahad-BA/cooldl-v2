# 🚀 CoolDL Bot - Ultimate Video Downloader Bot

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0-blue?style=for-the-badge&logo=github&logoColor=white" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11%2B-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge&logo=github&logoColor=white" alt="License">
  <img src="https://img.shields.io/badge/platform-linux-lightgrey?style=for-the-badge&logo=linux&logoColor=white" alt="Platform">
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
- **Rate Limiting** ⏱️ - Configurable per-user download limits (10/hour default)
- **Smart Error Handling** 🛠️ - Comprehensive logging and automatic recovery
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
python3 -c "from database import init_db; init_db()"
```

6. **Start the bot**
```bash
# Start the Telegram bot
python3 async_downloader.py &

# Start the web dashboard
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
```

### 🔧 **Configuration**

Create a `.env` file in the project root:

```env
# Bot Configuration
BOT_TOKEN=your_telegram_bot_token
CHANNEL_ID=your_channel_id
LOG_CHANNEL_ID=your_log_channel_id

# Database Configuration
DATABASE_URL=sqlite:///cooldl.db

# Rate Limiting (per hour)
MAX_DOWNLOADS_PER_HOUR=10

# File Management
MAX_FILE_SIZE=500  # MB
FILE_RETENTION_DAYS=7

# Admin Configuration
ADMIN_IDS=123456789,987654321
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
- **Help**: `/help` - Shows supported platforms
- **Admin Commands**:
  - `/block <user>` - Block a user
  - `/unblock <user>` - Unblock a user
  - `/blocked` - Show blocked users list
  - `/check <user>` - Check user status

### 🌐 **Web API**
```python
# Get dashboard stats
GET /dashboard

# Get recent downloads
GET /api/downloads

# Get error logs
GET /api/errors

# Get users data
GET /api/users
```

---

## 🏗️ **Architecture**

### 🔄 **System Components**
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Telegram Bot  │────│   Web Dashboard │────│   SQLite DB    │
│ (async_downloader) │    │   (FastAPI)     │    │   (cooldl.db)   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                │
                    ┌─────────────────┐
                    │ Blocking System │
                    │ (blocks.py)     │
                    └─────────────────┘
```

### 🎯 **Key Features**
- **Self-Hosted**: Complete control over your data and privacy
- **Scalable**: Handles multiple concurrent downloads efficiently
- **Secure**: User authentication and admin controls
- **Extensible**: Easy to add new platforms and features
- **Reliable**: Comprehensive error handling and logging

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

### 📚 **Testing**
```bash
# Run unit tests
python3 -m pytest

# Test blocking system
python3 test_blocking_system.py

# Test dashboard
python3 test_dashboard.py
```

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