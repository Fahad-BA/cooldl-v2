import sqlite3
from datetime import datetime

def get_connection():
    return sqlite3.connect("cooldl.db")

def get_all_downloads():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT url, source, user_id, timestamp FROM downloads ORDER BY timestamp DESC LIMIT 50")
    rows = cur.fetchall()
    conn.close()
    return [
        {"url": r[0], "source": r[1], "channel": "bot" if r[2] else "webapp", "timestamp": r[3]}
        for r in rows
    ]

def get_errors():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT error, timestamp FROM errors ORDER BY timestamp DESC LIMIT 20")
    rows = cur.fetchall()
    conn.close()
    return [{"error": r[0] if r[0] else "Unknown error", "timestamp": r[1]} for r in rows]

def get_top_sources(limit=5):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT source, COUNT(*) as count 
        FROM downloads 
        GROUP BY source 
        ORDER BY count DESC 
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"source": r[0], "count": r[1]} for r in rows]
