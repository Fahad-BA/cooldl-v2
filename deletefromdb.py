import sqlite3
import os
import logging
from pathlib import Path

# تحديد مسار قاعدة البيانات واسم الملف
DB_FILENAME = "cooldl.db"
DB_PATH = Path(os.getcwd()) / DB_FILENAME
FILE_TO_DELETE = "File38079.mp4"

def conn():
    """ينشئ ويُرجع اتصال بقاعدة بيانات SQLite."""
    # يفترض أن قاعدة البيانات cooldl.db في نفس مسار تشغيل هذا الملف
    c = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=20)
    c.row_factory = sqlite3.Row
    try:
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("PRAGMA busy_timeout=20000;")
    except Exception:
        pass
    return c

def delete_download_by_filename(filename_to_delete: str) -> int:
    """يحذف سجلاً من جدول 'downloads' بناءً على اسم الملف."""
    c = conn()
    cur = c.cursor()
    try:
        cur.execute(
            """DELETE FROM downloads WHERE filename = ?""",
            (filename_to_delete,)
        )
        c.commit()
        return cur.rowcount
    except Exception as e:
        print(f"فشل حذف السجل: {e}") 
        return 0
    finally:
        c.close()

# ================== التنفيذ ==================

if __name__ == '__main__':
    if not DB_PATH.exists():
        print(f"❌ خطأ: لم يتم العثور على قاعدة البيانات في المسار المحدد: {DB_PATH}")
    else:
        rows_deleted = delete_download_by_filename(FILE_TO_DELETE)

        if rows_deleted > 0:
            print(f"✅ تم حذف {rows_deleted} سجل يخص الملف: **{FILE_TO_DELETE}** من قاعدة البيانات.")
        else:
            print(f"⚠️ لم يتم العثور على سجل للملف: **{FILE_TO_DELETE}** أو فشلت عملية الحذف.")