import sqlite3

conn = sqlite3.connect("cooldl.db")
cursor = conn.cursor()

required_tables = {
    "downloads": {
        "file_id": "TEXT",
        "timestamp": "TEXT",
        "username": "TEXT",
        "chat_id": "INTEGER",
        "name": "TEXT",
        "url": "TEXT",
        "source": "TEXT",
        "user_id": "TEXT",
        "filename": "TEXT"
    },
    "errors": {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "error": "TEXT",
        "timestamp": "TEXT"
    },
    "users": {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "username": "TEXT",
        "joined_at": "TEXT"
    },
    "logs": {
        "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "action": "TEXT",
        "timestamp": "TEXT"
    }
}

def get_columns(table):
    cursor.execute(f"PRAGMA table_info({table});")
    return {col[1]: col[2] for col in cursor.fetchall()}

for table, columns in required_tables.items():
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}';")
    exists = cursor.fetchone()
    if not exists:
        columns_def = ", ".join([f"{col} {col_type}" for col, col_type in columns.items()])
        cursor.execute(f"CREATE TABLE {table} ({columns_def});")
    else:
        existing = get_columns(table)
        for col, col_type in columns.items():
            # نتجاهل الأعمدة اللي فيها PRIMARY KEY لأنها ما تقدر تنضاف بـ ALTER TABLE
            if col not in existing and "PRIMARY KEY" not in col_type.upper():
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type};")

conn.commit()
conn.close()
print("✅ Database schema patched successfully (without touching primary keys).")
