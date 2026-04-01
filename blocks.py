import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any

from models import get_connection

def is_user_blocked(chat_id: int) -> bool:
    """Check if a user is blocked by chat_id."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT 1 FROM blocked_users WHERE chat_id = ?",
            (chat_id,)
        )
        
        result = cursor.fetchone()
        conn.close()
        return result is not None
        
    except Exception as e:
        logging.error(f"Error checking block status for chat_id {chat_id}: {e}")
        return False

def block_user(chat_id: Optional[int] = None, 
               username: Optional[str] = None, 
               filename: Optional[str] = None, 
               reason: str = "", 
               blocked_by: str = "admin") -> Dict[str, Any]:
    """
    Block a user by chat_id, username, or filename.
    Returns a dict with success status and message.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # If filename is provided, get the chat_id from downloads table
        if filename:
            cursor.execute(
                "SELECT chat_id FROM downloads WHERE filename = ? LIMIT 1",
                (filename,)
            )
            result = cursor.fetchone()
            if result:
                chat_id = result[0]
            else:
                return {"success": False, "message": f"Filename '{filename}' not found in downloads"}
        
        # If username is provided, get the chat_id from users table
        elif username:
            cursor.execute(
                "SELECT chat_id FROM users WHERE username = ? LIMIT 1",
                (username,)
            )
            result = cursor.fetchone()
            if result:
                chat_id = result[0]
            else:
                return {"success": False, "message": f"Username '{username}' not found"}
        
        # If no chat_id found, return error
        if not chat_id:
            return {"success": False, "message": "No valid chat_id found for blocking"}
        
        # Check if user is already blocked
        if is_user_blocked(chat_id):
            return {"success": False, "message": f"User {chat_id} is already blocked"}
        
        # Get username if not provided
        if not username:
            cursor.execute(
                "SELECT username FROM users WHERE chat_id = ? LIMIT 1",
                (chat_id,)
            )
            result = cursor.fetchone()
            username = result[0] if result else None
        
        # Insert into blocked_users table
        cursor.execute(
            """INSERT INTO blocked_users 
               (chat_id, username, filename, reason, blocked_at, blocked_by)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chat_id, username, filename, reason, datetime.now().isoformat(), blocked_by)
        )
        
        conn.commit()
        conn.close()
        
        return {
            "success": True, 
            "message": f"User {chat_id} ({username}) has been blocked",
            "chat_id": chat_id,
            "username": username
        }
        
    except sqlite3.IntegrityError:
        return {"success": False, "message": f"User {chat_id} is already blocked"}
    except Exception as e:
        logging.error(f"Error blocking user {chat_id}: {e}")
        return {"success": False, "message": f"Database error: {str(e)}"}

def unblock_user(chat_id: Optional[int] = None, 
                 username: Optional[str] = None, 
                 filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Unblock a user by chat_id, username, or filename.
    Returns a dict with success status and message.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # If filename is provided, get the chat_id from downloads table
        if filename:
            cursor.execute(
                "SELECT chat_id FROM downloads WHERE filename = ? LIMIT 1",
                (filename,)
            )
            result = cursor.fetchone()
            if result:
                chat_id = result[0]
            else:
                return {"success": False, "message": f"Filename '{filename}' not found in downloads"}
        
        # If username is provided, get the chat_id from users table
        elif username:
            cursor.execute(
                "SELECT chat_id FROM users WHERE username = ? LIMIT 1",
                (username,)
            )
            result = cursor.fetchone()
            if result:
                chat_id = result[0]
            else:
                return {"success": False, "message": f"Username '{username}' not found"}
        
        # If no chat_id found, return error
        if not chat_id:
            return {"success": False, "message": "No valid chat_id found for unblocking"}
        
        # Check if user is actually blocked
        if not is_user_blocked(chat_id):
            return {"success": False, "message": f"User {chat_id} is not blocked"}
        
        # Delete from blocked_users table
        cursor.execute(
            "DELETE FROM blocked_users WHERE chat_id = ?",
            (chat_id,)
        )
        
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        if rows_affected > 0:
            return {
                "success": True, 
                "message": f"User {chat_id} has been unblocked",
                "chat_id": chat_id
            }
        else:
            return {"success": False, "message": f"User {chat_id} was not found in blocked users"}
            
    except Exception as e:
        logging.error(f"Error unblocking user {chat_id}: {e}")
        return {"success": False, "message": f"Database error: {str(e)}"}

def get_blocked_users() -> List[Dict[str, Any]]:
    """Get all blocked users with their details."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, chat_id, username, filename, reason, blocked_at, blocked_by
               FROM blocked_users 
               ORDER BY blocked_at DESC"""
        )
        
        blocked_users = []
        for row in cursor.fetchall():
            blocked_users.append({
                "id": row[0],
                "chat_id": row[1],
                "username": row[2],
                "filename": row[3],
                "reason": row[4],
                "blocked_at": row[5],
                "blocked_by": row[6]
            })
        
        conn.close()
        return blocked_users
        
    except Exception as e:
        logging.error(f"Error getting blocked users: {e}")
        return []

def check_user_block_status(chat_id: int) -> Optional[Dict[str, Any]]:
    """Check if a user is blocked and return block details."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """SELECT id, chat_id, username, filename, reason, blocked_at, blocked_by
               FROM blocked_users 
               WHERE chat_id = ?""",
            (chat_id,)
        )
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "id": row[0],
                "chat_id": row[1],
                "username": row[2],
                "filename": row[3],
                "reason": row[4],
                "blocked_at": row[5],
                "blocked_by": row[6]
            }
        return None
        
    except Exception as e:
        logging.error(f"Error checking block status for chat_id {chat_id}: {e}")
        return None

def log_blocked_attempt(chat_id: int, url: str, username: str = "Unknown"):
    """Log a blocked download attempt."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            """INSERT INTO logs (timestamp, action, username, chat_id, status)
               VALUES (?, ?, ?, ?, ?)""",
            (datetime.now().isoformat(), "download_attempt_blocked", username, chat_id, "blocked")
        )
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        logging.error(f"Error logging blocked attempt for chat_id {chat_id}: {e}")