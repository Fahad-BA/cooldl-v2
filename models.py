import sqlite3
import os

DB_PATH = os.getenv("DATABASE", "cooldl.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def get_all_downloads():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT url, source, user_id, timestamp FROM downloads ORDER BY ROWID DESC LIMIT 50")
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [
        {"url": r[0], "source": r[1], "channel": "bot" if r[2] else "webapp", "timestamp": r[3]}
        for r in rows
    ]

def get_errors():
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COALESCE(error,'Unknown error') as error, timestamp FROM errors ORDER BY ROWID DESC LIMIT 20")
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [{"error": r[0], "timestamp": r[1]} for r in rows]

def get_top_sources(limit=5):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT source, COUNT(*) as count
            FROM downloads
            GROUP BY source
            ORDER BY count DESC
            LIMIT ?
        """, (limit,))
        rows = cur.fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()
    return [{"source": r[0], "count": r[1]} for r in rows]
