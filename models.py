import sqlite3, os, sys, traceback

# اجعل المسار مطلقًا
DB_PATH = os.path.abspath(os.getenv("DATABASE", "cooldl.db"))

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=20000;")
    except Exception:
        pass
    return conn

def _fetch(cur, sql, params=()):
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception as e:
        # اطبع الخطأ في stdout عشان يبين في لوق الويب
        print("[models.get_all_downloads] SQL error:", e, file=sys.stderr)
        traceback.print_exc()
        return []

def get_all_downloads(limit: int = 50):
    """
    يرجّع أحدث التحميلات مع:
      - url, source, timestamp
      - filename (اسم الملف في الستوريج)
      - name (اسم اللي حمّل: users.name وإلا downloads.name)
    """
    conn = get_connection()
    cur = conn.cursor()
    rows = _fetch(cur, """
        SELECT
            d.url,
            d.source,
            d.timestamp,
            d.filename,
            COALESCE(u.name, d.name) AS name
        FROM downloads AS d
        LEFT JOIN users AS u ON u.chat_id = d.chat_id
        -- رتب حسب الوقت الأحدث، ولو ما فيه وقت استخدم rowid كرجوع
        ORDER BY
            CASE WHEN d.timestamp IS NULL OR d.timestamp = '' THEN 1 ELSE 0 END,
            d.timestamp DESC,
            d.rowid DESC
        LIMIT ?
    """, (limit,))
    conn.close()

    return [
        {
            "url": r["url"],
            "source": r["source"],
            "timestamp": r["timestamp"],
            "filename": r["filename"],
            "name": r["name"] or "web",
        }
        for r in rows
    ]

def get_errors(limit: int = 50):
    conn = get_connection()
    cur = conn.cursor()
    rows = _fetch(cur, """
        SELECT COALESCE(error,'Unknown error') AS error, timestamp, file_id
        FROM errors
        ORDER BY rowid DESC
        LIMIT ?
    """, (limit,))
    conn.close()
    return [{"error": r["error"], "timestamp": r["timestamp"], "file_id": r["file_id"]} for r in rows]

def get_top_sources(limit: int = 5):
    conn = get_connection()
    cur = conn.cursor()
    rows = _fetch(cur, """
        SELECT source, COUNT(*) AS count
        FROM downloads
        GROUP BY source
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    conn.close()
    return [{"source": r["source"], "count": r["count"]} for r in rows]
