# 🚀 cooldl-v2 - Ultimate Video Downloader Bot

<p align="center">
  <img src="https://img.shields.io/badge/version-2.0-blue?style=for-the-badge&logo=github&logoColor=white" alt="Version">
  <img src="https://img.shields.io/badge/python-3.11%2B-yellow?style=for-the-badge&logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-green?style=for-the-badge&logo=github&logoColor=white" alt="License">
  <img src="https://img.shields.io/badge/platform-linux-lightgrey?style=for-the-badge&logo=linux&logoColor=white" alt="Platform">
</p>

<p align="center">
  <em>A powerful, feature-rich Telegram bot for downloading videos from multiple platforms with real-time dashboard monitoring</em>
</p>

---

## ✨ Features

### 🎥 **Multi-Platform Support**
- **TikTok** ⚡ - High-speed downloads with age-restriction bypass
- **YouTube** 🎬 - Video extraction with optimal quality selection
- **Twitter/X** 🐦 - Video and media downloads
- **Instagram** 📸 - Reels and media support
- **And more...** 🌐 - Extensible architecture for adding new platforms

### 🛡️ **Smart Features**
- **Rate Limiting** ⏱️ - Configurable per-user download limits
- **File Management** 🗂️ - Automatic cleanup with configurable retention
- **Caching System** 💾 - Smart duplicate detection to save bandwidth
- **Error Handling** 🛠️ - Comprehensive logging and error recovery
- **User Management** 👥 - 62+ active users with detailed analytics

### 📊 **Real-Time Dashboard**
- **Live Statistics** 📈 - Monitor downloads, errors, and top sources
- **Interactive Charts** 📊 - Beautiful data visualizations using Chart.js
- **User Analytics** 👤 - Track individual download patterns
- **Error Monitoring** 🔍 - Real-time error logs with timestamps
- **Performance Metrics** ⚡ - System health and performance indicators

---

## 🚀 Quick Start

### 📋 **Prerequisites**
```bash
# Python 3.11+
python --version

# Git (for cloning)
git --version

# SQLite3 (usually comes with Python)
sqlite3 --version
```

### 🛠️ **Installation**

1. **Clone the repository**
```bash
git clone https://github.com/Fahad-BA/cooldl-v2.git
cd cooldl-v2
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Environment Configuration**
```bash
# Copy the template
cp .env.example .env

# Edit with your configuration
nano .env
```

**Required Environment Variables:**
```env
# Telegram Bot Token
BOT_TOKEN=your_bot_token_here

# Channel ID for downloads
CHANNEL_ID=your_channel_id_here

# Database Path (optional, defaults to cooldl.db)
DATABASE=./cooldl.db

# (Optional) Log Channel ID
LOG_CHANNEL_ID=your_log_channel_id_here

# (Optional) Download Caption
CAPTION=Your custom caption here

# (Optional) Rate Limiting
MAX_CONCURRENT=3
MAX_DOWNLOADS_PER_HOUR=10
MAX_FILE_SIZE=500  # MB
DOWNLOAD_TIMEOUT=300  # seconds
FILE_RETENTION_DAYS=7
```

5. **Initialize Database**
```bash
python init_db.py
```

6. **Start the Services**
```bash
# Start the Telegram bot
python async_downloader.py

# In another terminal, start the web dashboard
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 📊 **Project Statistics**

<div align="center">

| Metric | Value | 📈 |
|--------|-------|----|
| **Total Users** | **62+** | 👥 |
| **Videos Downloaded** | **1,535+** | 🎥 |
| **Platforms Supported** | **4+** | 🌐 |
| **Database Records** | **1,535** | 💾 |
| **Error Rate** | **< 2%** | ✅ |

</div>

### 🔥 **Recent Achievements**
- ✅ **Database Schema Migration** - Added session tracking and fixed missing columns
- ✅ **Historical Data Import** - Migrated 703+ records from logs to downloads table
- ✅ **Performance Optimization** - Reduced error rates and improved download speeds
- ✅ **Dashboard Enhancement** - Real-time statistics and beautiful visualizations

---

## 🏗️ **Architecture Overview**

```
cooldl-v2/
├── 🤖 async_downloader.py    # Telegram bot main logic
├── 🌐 main.py               # FastAPI web dashboard
├── 💾 models.py             # Database models and queries
├── 📄 downloader.py         # Video download utilities
├── 🗃️ database.py          # Database connection helpers
├── 📋 requirements.txt     # Python dependencies
├── 🔧 .env                  # Environment variables (not in repo)
├── 🗄️ cooldl.db            # SQLite database (auto-created)
├── 📁 downloads/            # Downloaded files storage
├── 📁 static/               # Static web assets
├── 📁 templates/            # HTML templates
└── 🎨 static/styles.css     # Dashboard styling
```

### 💾 **Database Schema**

#### **Users Table**
```sql
CREATE TABLE users (
    chat_id INTEGER PRIMARY KEY,
    name TEXT,
    username TEXT,
    joined_at TEXT
);
```

#### **Downloads Table** 
```sql
CREATE TABLE downloads (
    file_id TEXT PRIMARY KEY,
    timestamp TEXT,
    username TEXT,
    chat_id INTEGER,
    name TEXT,
    url TEXT,
    source TEXT,
    user_id TEXT,
    filename TEXT,
    file_size INTEGER,
    session TEXT
);
```

#### **Logs Table**
```sql
CREATE TABLE logs (
    timestamp TEXT,
    action TEXT,
    username TEXT,
    chat_id INTEGER,
    status TEXT
);
```

---

## 🎮 **Usage Examples**

### **Telegram Bot Usage**
```
/send https://tiktok.com/@user/video/123456
⬇️ Downloads the TikTok video

/send https://youtube.com/watch?v=dQw4w9WgXcQ
⬇️ Downloads the YouTube video

/stats
📊 Shows download statistics
```

### **Web Dashboard Usage**
- **Access:** `http://localhost:8000`
- **Login:** `/login` (credentials configured in code)
- **Dashboard:** `/dashboard` (requires authentication)
- **Features:**
  - Real-time download monitoring
  - Interactive charts and statistics
  - Error log viewing
  - Bot restart functionality

---

## 🔧 **Configuration Options**

### **Rate Limiting**
```python
# In .env
MAX_CONCURRENT=3              # Simultaneous downloads
MAX_DOWNLOADS_PER_HOUR=10     # Per-user hourly limit
DOWNLOAD_TIMEOUT=300          # Seconds per download
FILE_RETENTION_DAYS=7         # Days to keep files
MAX_FILE_SIZE=500            # MB limit per file
```

### **Performance Tuning**
```python
# Database optimization
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=20000;

# Download optimization
concurrent_fragment_downloads: 4
retries: 5
socket_timeout: 30
```

---

## 🚨 **Troubleshooting**

### **Common Issues**

1. **"Database locked" errors**
   ```bash
   # Add WAL mode to SQLite
   sqlite3 cooldl.db "PRAGMA journal_mode=WAL;"
   ```

2. **Download timeouts**
   ```bash
   # Increase timeout in .env
   DOWNLOAD_TIMEOUT=600
   ```

3. **Permission errors**
   ```bash
   # Fix file permissions
   chmod -R 755 downloads/
   ```

### **Debug Mode**
```bash
# Enable verbose logging
export PYTHONPATH=.
python async_downloader.py --verbose
```

---

## 🤝 **Contributing**

We love contributions! Here's how you can help:

1. **🐛 Report Bugs** - Open an issue with detailed description
2. **✨ Request Features** - Suggest new functionality
3. **💻 Submit Pull Requests** - Code contributions welcome
4. **📚 Improve Documentation** - Help make docs better

### **Development Setup**
```bash
# Fork and clone
git clone https://github.com/your-username/cooldl-v2.git

# Create feature branch
git checkout -b feature/amazing-feature

# Make changes and commit
git commit -m "feat: add amazing feature"

# Push and open PR
git push origin feature/amazing-feature
```

---

## 📄 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

<div align="center">

**Made with ❤️ by [Fahad](https://github.com/Fahad-BA)**

**⭐ If this project helped you, please consider starring the repository!**

</div>

---

<div align="center">

**📞 Questions? Contact me:**
<br>
🐦 Twitter: [@Fahad_BA](https://twitter.com/Fahad_BA)
<br>
💼 LinkedIn: [Fahad Albalawi](https://linkedin.com/in/fahad-albalawi)
<br>
📧 Email: fahad@example.com

</div>

---

<p align="center">
  <img src="https://img.shields.io/badge/built%20with-❤️-red?style=for-the-badge" alt="Built with love">
  <img src="https://img.shields.io/badge/status-active-brightgreen?style=for-the-badge" alt="Status">
  <img src="https://img.shields.io/badge/maintained-yes-blue?style=for-the-badge" alt="Maintained">
</p>