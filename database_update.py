import os
import sqlite3
import datetime
from pathlib import Path

# مسار القاعدة من المتغير البيئي أو الافتراضي
DB_PATH = os.getenv("DATABASE", "cooldl.db")

def get_connection():
    """
    يفتح اتصال SQLite مع row_factory=Row.
    """
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

# =========================
# أدوات وقت مفيدة
# =========================
def now_utc_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def now_local_str(tz="Asia/Riyadh"):
    # بدون الاعتماد على pytz لتقليل المتطلبات
    # نستخدم التوقيت المحلي للنظام إذا ما توفّر tz
    return datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")

# =========================
# مهاجرات خفيفة + إنشاء جداول
# =========================
def _table_columns(conn, table_name: str) -> dict:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = {row["name"]: row for row in cur.fetchall()}
    return cols

def _ensure_column(conn, table: str, col_def: str):
    """
    يضيف عمودًا إن لم يكن موجودًا.
    col_def مثال: "id INTEGER PRIMARY KEY AUTOINCREMENT"
    ملاحظة: لا يمكن تغيير الـ PRIMARY KEY ب ALTER TABLE إذا كان الجدول موجودًا.
    """
    parts = col_def.strip().split()
    col_name = parts[0]
    cols = _table_columns(conn, table)
    if col_name not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_def}")

def ensure_tables():
    """
    ينشئ الجداول إن لم تكن موجودة، ويضمن الأعمدة الأساسية إن فقدت.
    يحافظ على جداولك الحالية بدون كسر المفاتيح الأساسية القديمة.
    """
    conn = get_connection()
    cur = conn.cursor()

    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        chat_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        joined_at TEXT
    )
    """)

    # downloads
    # ملاحظة: بعض نسخك السابقة تستخدم file_id TEXT كمفتاح.
    # هنا ننشئ الجدول لو غير موجود. لو موجود، نضيف الأعمدة الناقصة فقط.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS downloads(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id TEXT,
        timestamp TEXT,
        username TEXT,
        chat_id INTEGER,
        name TEXT,
        url TEXT,
        source TEXT,
        user_id TEXT,
        filename TEXT
    )
    """)

    # errors
    cur.execute("""
    CREATE TABLE IF NOT EXISTS errors(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        error TEXT,
        file_id TEXT,
        timestamp TEXT,
        username TEXT,
        chat_id INTEGER,
        name TEXT,
        url TEXT
    )
    """)

    # logs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        action TEXT,
        username TEXT,
        chat_id INTEGER,
        status TEXT
    )
    """)

    # ضمان الأعمدة الأساسية لو كانت ناقصة (مهاجرات خفيفة)
    # downloads
    for col_def in [
        "file_id TEXT",
        "timestamp TEXT",
        "username TEXT",
        "chat_id INTEGER",
        "name TEXT",
        "url TEXT",
        "source TEXT",
        "user_id TEXT",
        "filename TEXT",
    ]:
        _ensure_column(conn, "downloads", col_def)

    # errors
    for col_def in [
        "error TEXT",
        "file_id TEXT",
        "timestamp TEXT",
        "username TEXT",
        "chat_id INTEGER",
        "name TEXT",
        "url TEXT",
    ]:
        _ensure_column(conn, "errors", col_def)

    # users
    for col_def in [
        "name TEXT",
        "username TEXT",
        "joined_at TEXT",
    ]:
        _ensure_column(conn, "users", col_def)

    # logs
    for col_def in [
        "timestamp TEXT",
        "action TEXT",
        "username TEXT",
        "chat_id INTEGER",
        "status TEXT",
    ]:
        _ensure_column(conn, "logs", col_def)

    conn.commit()
    conn.close()

# =========================
# عمليات إدخال سريعة
# =========================
def insert_user(chat_id: int, name: str, username: str):
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "INSERT OR IGNORE INTO users(chat_id, name, username, joined_at) VALUES(?,?,?,?)",
        (chat_id, name, username, now_utc_iso())
    )
    conn.commit(); conn.close()

def insert_download(user_id, url, filename, source="telegram", chat_id=None, name=None, username=None, file_id=None):
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO downloads(user_id, url, filename, source, timestamp, chat_id, name, username, file_id)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (user_id, url, filename, source, now_utc_iso(), chat_id, name, username, file_id)
    )
    conn.commit(); conn.close()

def insert_error(error_text, file_id, username, chat_id, name, url):
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        """INSERT INTO errors(error, file_id, timestamp, username, chat_id, name, url)
           VALUES (?,?,?,?,?,?,?)""",
        (error_text, file_id, now_utc_iso(), username, chat_id, name, url)
    )
    conn.commit(); conn.close()

def insert_log(action, username, chat_id, status):
    conn = get_connection(); cur = conn.cursor()
    cur.execute(
        "INSERT INTO logs(timestamp, action, username, chat_id, status) VALUES (?,?,?,?,?)",
        (now_utc_iso(), action, username, chat_id, status)
    )
    conn.commit(); conn.close()

# =========================
# استعلامات مساعدة للكاش
# =========================
def find_cached_file(url: str) -> Path | None:
    """
    يرجع مسار الملف من آخر تحميل لنفس الرابط، إن وجد الملف على القرص.
    يعتمد على أحدث ROWID لضمان آخر إدخال حتى لو ما كان فيه عمود id تسلسلي.
    """
    conn = get_connection(); cur = conn.cursor()
    cur.execute("SELECT filename FROM downloads WHERE url=? ORDER BY ROWID DESC LIMIT 1", (url,))
    row = cur.fetchone()
    conn.close()
    if not row: 
        return None
    filename = row["filename"]
    if not filename:
        return None
    fp = Path("downloads") / filename
    return fp if fp.exists() else None

# دوال قراءة للداشبورد (اختيارية)
def get_recent_downloads(limit=50):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT url, source, user_id, timestamp 
        FROM downloads 
        ORDER BY ROWID DESC 
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall(); conn.close()
    return [
        {"url": r[0], "source": r[1], "channel": "bot" if r[2] else "webapp", "timestamp": r[3]}
        for r in rows
    ]

def get_recent_errors(limit=20):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(error,'Unknown error') as error, timestamp 
        FROM errors 
        ORDER BY ROWID DESC 
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall(); conn.close()
    return [{"error": r[0], "timestamp": r[1]} for r in rows]

def get_top_sources(limit=5):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("""
        SELECT source, COUNT(*) as count
        FROM downloads
        GROUP BY source
        ORDER BY count DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall(); conn.close()
    return [{"source": r[0], "count": r[1]} for r in rows]

# تهيئة سريعة لو احتجتها من سكربت خارجي
def init_db():
    ensure_tables()
