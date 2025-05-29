import sqlite3

DB_PATH = "cooldl.db"

def drop_all_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    tables = ['downloads', 'users', 'errors', 'logs']
    for table in tables:
        try:
            cur.execute(f"DROP TABLE IF EXISTS {table}")
            print(f"✅ Dropped table: {table}")
        except Exception as e:
            print(f"❌ Failed to drop {table}: {e}")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    drop_all_tables()
