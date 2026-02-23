from fastapi import APIRouter, HTTPException, Query, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from typing import Optional, List, Dict, Any
import sqlite3
from datetime import datetime
from pathlib import Path

router = APIRouter(prefix="/blocks", tags=["blocks"])

# Make sure templates directory exists
Path("templates").mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory="templates")

# Block message in both English and Arabic
BLOCK_MESSAGE = "You've been blocked from using this bot — أنت محظور من استخدام البوت"

def get_connection():
    conn = sqlite3.connect("cooldl.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_blocked_users():
    """Get all blocked users from database."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM blocked_users ORDER BY blocked_at DESC")
        users = cursor.fetchall()
        
        conn.close()
        
        # Convert to dict format
        result = []
        for user in users:
            result.append(dict(user))
        
        return result
    except Exception as e:
        print(f"Error getting blocked users: {e}")
        return []

def is_user_blocked(chat_id):
    """Check if a user is blocked by chat_id."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT 1 FROM blocked_users WHERE chat_id = ?", (chat_id,))
        result = cursor.fetchone()
        
        conn.close()
        return result is not None
    except Exception as e:
        print(f"Error checking block status: {e}")
        return False

@router.get("/", response_class=HTMLResponse)
async def blocks_dashboard(request: Request):
    """Main blocks management page."""
    try:
        blocked_users = get_blocked_users()
        return templates.TemplateResponse("blocks.html", {
            "request": request,
            "blocked_users": blocked_users
        })
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)

@router.post("/block", response_class=HTMLResponse)
async def block_user_web(
    request: Request,
    chat_id: Optional[str] = Form(None),
    username: Optional[str] = Form(None),
    filename: Optional[str] = Form(None),
    reason: str = Form(""),
    blocked_by: str = Form("web_admin")
):
    """Block a user via web interface."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Convert chat_id to int if provided
        chat_id_int = None
        if chat_id:
            try:
                chat_id_int = int(chat_id)
            except ValueError:
                return templates.TemplateResponse("blocks.html", {
                    "request": request,
                    "blocked_users": get_blocked_users(),
                    "error": "Invalid chat_id format"
                })
        
        # Check if already blocked
        if chat_id_int:
            cursor.execute("SELECT id FROM blocked_users WHERE chat_id = ?", (chat_id_int,))
        elif username:
            cursor.execute("SELECT id FROM blocked_users WHERE username = ?", (username,))
        elif filename:
            cursor.execute("SELECT id FROM blocked_users WHERE filename = ?", (filename,))
        else:
            return templates.TemplateResponse("blocks.html", {
                "request": request,
                "blocked_users": get_blocked_users(),
                "error": "No identifier provided"
            })
        
        if cursor.fetchone():
            return templates.TemplateResponse("blocks.html", {
                "request": request,
                "blocked_users": get_blocked_users(),
                "error": "User already blocked"
            })
        
        # Block the user
        blocked_at = datetime.now().isoformat()
        
        if chat_id_int:
            cursor.execute(
                "INSERT INTO blocked_users (chat_id, reason, blocked_at, blocked_by) VALUES (?, ?, ?, ?)",
                (chat_id_int, reason, blocked_at, blocked_by)
            )
        elif username:
            cursor.execute(
                "INSERT INTO blocked_users (username, reason, blocked_at, blocked_by) VALUES (?, ?, ?, ?)",
                (username, reason, blocked_at, blocked_by)
            )
        elif filename:
            cursor.execute(
                "INSERT INTO blocked_users (filename, reason, blocked_at, blocked_by) VALUES (?, ?, ?, ?)",
                (filename, reason, blocked_at, blocked_by)
            )
        
        conn.commit()
        conn.close()
        
        return templates.TemplateResponse("blocks.html", {
            "request": request,
            "blocked_users": get_blocked_users(),
            "success": "User blocked successfully"
        })
        
    except Exception as e:
        return templates.TemplateResponse("blocks.html", {
            "request": request,
            "blocked_users": get_blocked_users(),
            "error": f"Error blocking user: {str(e)}"
        })

@router.post("/api/block")
async def block_user_api(request: Request):
    """API endpoint to block a user."""
    try:
        data = await request.json()
        
        chat_id = data.get('chat_id')
        username = data.get('username')
        filename = data.get('filename')
        reason = data.get('reason', '')
        blocked_by = data.get('blocked_by', 'api')
        
        if not chat_id and not username and not filename:
            return {"success": False, "message": "No identifier provided"}
        
        conn = get_connection()
        cursor = conn.cursor()
        
        # Check if already blocked
        if chat_id:
            cursor.execute("SELECT id FROM blocked_users WHERE chat_id = ?", (chat_id,))
        elif username:
            cursor.execute("SELECT id FROM blocked_users WHERE username = ?", (username,))
        elif filename:
            cursor.execute("SELECT id FROM blocked_users WHERE filename = ?", (filename,))
        
        if cursor.fetchone():
            conn.close()
            return {"success": False, "message": "User already blocked"}
        
        # Block the user
        blocked_at = datetime.now().isoformat()
        
        if chat_id:
            cursor.execute(
                "INSERT INTO blocked_users (chat_id, reason, blocked_at, blocked_by) VALUES (?, ?, ?, ?)",
                (chat_id, reason, blocked_at, blocked_by)
            )
        elif username:
            cursor.execute(
                "INSERT INTO blocked_users (username, reason, blocked_at, blocked_by) VALUES (?, ?, ?, ?)",
                (username, reason, blocked_at, blocked_by)
            )
        elif filename:
            cursor.execute(
                "INSERT INTO blocked_users (filename, reason, blocked_at, blocked_by) VALUES (?, ?, ?, ?)",
                (filename, reason, blocked_at, blocked_by)
            )
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "User blocked successfully", "chat_id": chat_id}
        
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.post("/api/unblock")
async def unblock_user_api(request: Request):
    """API endpoint to unblock a user."""
    try:
        data = await request.json()
        
        chat_id = data.get('chat_id')
        username = data.get('username')
        filename = data.get('filename')
        
        if not chat_id and not username and not filename:
            return {"success": False, "message": "No identifier provided"}
        
        conn = get_connection()
        cursor = conn.cursor()
        
        if chat_id:
            cursor.execute("DELETE FROM blocked_users WHERE chat_id = ?", (chat_id,))
        elif username:
            cursor.execute("DELETE FROM blocked_users WHERE username = ?", (username,))
        elif filename:
            cursor.execute("DELETE FROM blocked_users WHERE filename = ?", (filename,))
        
        conn.commit()
        conn.close()
        
        return {"success": True, "message": "User unblocked successfully", "chat_id": chat_id}
        
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/api/blocked")
async def get_blocked_users_api():
    """API endpoint to get all blocked users."""
    try:
        blocked_users = get_blocked_users()
        return {"success": True, "blocked_users": blocked_users}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/api/check/{chat_id}")
async def check_user_block_api(chat_id: int):
    """API endpoint to check if a user is blocked."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM blocked_users WHERE chat_id = ?", (chat_id,))
        user = cursor.fetchone()
        
        conn.close()
        
        if user:
            return {
                "success": True,
                "blocked": True,
                "details": dict(user)
            }
        else:
            return {
                "success": True,
                "blocked": False,
                "message": f"User {chat_id} is not blocked"
            }
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/api/is-blocked/{chat_id}")
async def is_user_blocked_api(chat_id: int):
    """Simple check if user is blocked (returns boolean)."""
    try:
        blocked = is_user_blocked(chat_id)
        return {"success": True, "blocked": blocked}
    except Exception as e:
        return {"success": False, "message": str(e)}

@router.get("/search")
async def search_blocked_users(request: Request, q: str = ""):
    """Search blocked users."""
    try:
        blocked_users = get_blocked_users()
        
        if q:
            results = []
            for user in blocked_users:
                if (q.isdigit() and str(user.get("chat_id", "")) == q) or \
                   (user.get("username") and q.lower() in user.get("username", "").lower()) or \
                   (user.get("filename") and q.lower() in user.get("filename", "").lower()):
                    results.append(user)
            blocked_users = results
        
        return templates.TemplateResponse("blocks_search.html", {
            "request": request,
            "blocked_users": blocked_users,
            "query": q
        })
    except Exception as e:
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)