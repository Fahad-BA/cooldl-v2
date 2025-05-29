import sqlite3

DB_PATH = "cooldl.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # جدول التحميلات
    cur.execute("""
    CREATE TABLE IF NOT EXISTS downloads (
        file_id TEXT PRIMARY KEY,
        timestamp TEXT,
        username TEXT,
        chat_id INTEGER,
        name TEXT,
        url TEXT,
        source TEXT
    )
    """)

    # جدول المستخدمين
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT
    )
    """)

    # جدول الأخطاء
    cur.execute("""
    CREATE TABLE IF NOT EXISTS errors (
        file_id TEXT,
        timestamp TEXT,
        username TEXT,
        chat_id INTEGER,
        name TEXT,
        url TEXT
    )
    """)

    # جدول اللوقز
    cur.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        timestamp TEXT,
        action TEXT,
        username TEXT,
        chat_id INTEGER,
        status TEXT
    )
    """)

    conn.commit()
    conn.close()
    print("✅ All tables created.")

if __name__ == "__main__":
    init_db()
