"""
Unified database layer for CoolDL project.
Provides single source for database connections and schema management.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection with proper configuration and row factory."""
    conn = sqlite3.connect(
        settings.database.absolute_path, 
        check_same_thread=False, 
        timeout=settings.database.connection_timeout
    )
    conn.row_factory = sqlite3.Row
    
    # Set PRAGMAs
    try:
        conn.execute(f"PRAGMA journal_mode={settings.database.journal_mode};")
        conn.execute(f"PRAGMA busy_timeout={settings.database.busy_timeout};")
    except Exception as e:
        logger.debug(f"Could not set PRAGMAs: {e}")
    
    return conn


def setup_database():
    """Create database connection and ensure tables exist."""
    conn = get_connection()
    
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
      chat_id INTEGER PRIMARY KEY,
      name TEXT,
      username TEXT,
      created_at TEXT
    );
    CREATE TABLE IF NOT EXISTS downloads (
      file_id TEXT,
      timestamp TEXT,
      username TEXT,
      chat_id INTEGER,
      name TEXT,
      url TEXT,
      source TEXT,
      user_id TEXT,
      filename TEXT,
      file_size INTEGER
    );
    CREATE TABLE IF NOT EXISTS errors (
      error TEXT,
      file_id TEXT,
      timestamp TEXT,
      username TEXT,
      chat_id INTEGER,
      name TEXT,
      url TEXT
    );
    CREATE TABLE IF NOT EXISTS logs (
      timestamp TEXT,
      action TEXT,
      username TEXT,
      chat_id INTEGER,
      status TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_downloads_url ON downloads(url);
    CREATE INDEX IF NOT EXISTS ix_downloads_chat ON downloads(chat_id);
    CREATE INDEX IF NOT EXISTS ix_downloads_timestamp ON downloads(timestamp);
    """)
    conn.commit()
    return conn


def log_to_db(conn, table, values):
    """Log entry to database table."""
    cur = conn.cursor()
    try:
        if table == "downloads":
            cur.execute("""INSERT INTO downloads
                (user_id, url, filename, source, timestamp, chat_id, name, username, file_id, file_size, session)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""", values)
        elif table == "users":
            cur.execute("INSERT OR IGNORE INTO users (chat_id, name, username, created_at) VALUES (?,?,?,?)", values)
        elif table == "errors":
            cur.execute("""INSERT INTO errors (error, file_id, timestamp, username, chat_id, name, url)
                             VALUES (?,?,?,?,?,?,?)""", values)
        elif table == "logs":
            cur.execute("""INSERT INTO logs (timestamp, action, username, chat_id, status)
                             VALUES (?,?,?,?,?)""", values)
        conn.commit()
    except Exception as e:
        logger.error(f"DB logging error: {e}")


# Convenience function for backward compatibility
def get_db_connection():
    """Alias for get_connection() for backward compatibility."""
    return get_connection()


# Initialize database when module is imported
try:
    setup_database()
except Exception as e:
    logger.error(f"Failed to initialize database: {e}")