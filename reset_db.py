import sqlite3

DB_PATH = "cooldl.db"

def clear_all():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # حذف البيانات من الجداول
    c.execute("DELETE FROM downloads")
    c.execute("DELETE FROM users")
    c.execute("DELETE FROM errors")
    c.execute("DELETE FROM logs")

    conn.commit()
    conn.close()
    print("✅ تمت تهيئة قاعدة البيانات بنجاح (تم حذف كل البيانات).")

if __name__ == "__main__":
    clear_all()
