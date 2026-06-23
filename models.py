import sys, traceback

# Import unified database layer
import db

# Convenience function for backward compatibility
def get_connection():
    """Alias for db.get_connection() for backward compatibility."""
    return db.get_connection()

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
    conn = db.get_connection()
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
    conn = db.get_connection()
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
    conn = db.get_connection()
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

# Ask-Project Functions
def get_questions(category: str = None, difficulty: str = None, limit: int = 50, active_only: bool = True):
    """
    Get questions with optional filtering by category and difficulty
    """
    conn = db.get_connection()
    cur = conn.cursor()
    
    # Build the query dynamically based on parameters
    query = "SELECT * FROM questions"
    params = []
    conditions = []
    
    if active_only:
        conditions.append("is_active = 1")
    
    if category:
        conditions.append("category = ?")
        params.append(category)
    
    if difficulty:
        conditions.append("difficulty = ?")
        params.append(difficulty)
    
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    rows = _fetch(cur, query, tuple(params))
    conn.close()
    
    return [
        {
            "id": r["id"],
            "question_text": r["question_text"],
            "category": r["category"],
            "difficulty": r["difficulty"],
            "created_at": r["created_at"],
            "created_by": r["created_by"],
            "is_active": r["is_active"]
        }
        for r in rows
    ]

def get_answers_for_question(question_id: int):
    """
    Get all answers for a specific question
    """
    conn = db.get_connection()
    cur = conn.cursor()
    
    rows = _fetch(cur, """
        SELECT * FROM answers 
        WHERE question_id = ? 
        ORDER BY created_at ASC
    """, (question_id,))
    
    conn.close()
    
    return [
        {
            "id": r["id"],
            "question_id": r["question_id"],
            "answer_text": r["answer_text"],
            "is_correct": r["is_correct"],
            "created_at": r["created_at"],
            "created_by": r["created_by"]
        }
        for r in rows
    ]

def get_questions_with_answers(category: str = None, difficulty: str = None, limit: int = 50, active_only: bool = True):
    """
    Get questions along with their answers
    """
    questions = get_questions(category, difficulty, limit, active_only)
    
    for question in questions:
        question["answers"] = get_answers_for_question(question["id"])
    
    return questions

def create_question(question_text: str, category: str = "general", difficulty: str = "medium", created_by: int = None):
    """
    Create a new question
    """
    conn = db.get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO questions (question_text, category, difficulty, created_by)
            VALUES (?, ?, ?, ?)
        """, (question_text, category, difficulty, created_by))
        
        question_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return {"success": True, "question_id": question_id}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "error": str(e)}

def create_answer(question_id: int, answer_text: str, is_correct: bool = False, created_by: int = None):
    """
    Create a new answer for a question
    """
    conn = db.get_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("""
            INSERT INTO answers (question_id, answer_text, is_correct, created_by)
            VALUES (?, ?, ?, ?)
        """, (question_id, answer_text, is_correct, created_by))
        
        answer_id = cur.lastrowid
        conn.commit()
        conn.close()
        
        return {"success": True, "answer_id": answer_id}
    except Exception as e:
        conn.rollback()
        conn.close()
        return {"success": False, "error": str(e)}
