import sqlite3
import random
from datetime import datetime, timedelta

DB_PATH = "cooldl.db"
SOURCES = ["YouTube", "TikTok", "Instagram", "X", "Unknown"]
USER_IDS = [111, 222, 333, 444, 555]

def random_timestamp():
    now = datetime.now()
    delta = timedelta(days=random.randint(0, 5), hours=random.randint(0, 23), minutes=random.randint(0, 59))
    return (now - delta).isoformat()

def seed_downloads(n=50):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    for _ in range(n):
        user_id = random.choice(USER_IDS)
        url = f"https://example.com/video{random.randint(1000, 9999)}"
        filename = f"file_{random.randint(1000,9999)}.mp4"
        source = random.choice(SOURCES)
        timestamp = random_timestamp()

        cur.execute("""
            INSERT INTO downloads (user_id, url, filename, source, timestamp)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, url, filename, source, timestamp))

    conn.commit()
    conn.close()
    print(f"✅ تمت إضافة {n} تحميل وهمي إلى قاعدة البيانات.")

if __name__ == "__main__":
    seed_downloads()
