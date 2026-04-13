from models import get_all_downloads, get_errors, get_top_sources, get_connection
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from downloader import download_video
from starlette.middleware.sessions import SessionMiddleware
import os
import httpx
from pathlib import Path

# Import configuration
from config import settings

# تأكد أن المجلدات موجودة
for d in ("downloads", "static", "templates"):
    Path(d).mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=settings.web.session_secret)

templates = Jinja2Templates(directory="templates")
# لا تفحص وجود المجلدات عند التشغيل
app.mount("/static", StaticFiles(directory="static", check_dir=False), name="static")
app.mount("/downloads", StaticFiles(directory="downloads", check_dir=False), name="downloads")

@app.get("/healthz", response_class=PlainTextResponse)
async def healthz():
    return "ok"

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    tpl = Path("templates/index.html")
    if not tpl.exists():
        return HTMLResponse("<h1>CoolDL</h1><p>ضع قالبك في templates/index.html</p>", status_code=200)
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/download", response_class=HTMLResponse)
async def download(request: Request, video_url: str = Form(...)):
    try:
        file_path = await download_video(video_url)
        if file_path:
            filename = os.path.basename(file_path)
            file_url = f"/downloads/{filename}"
            return templates.TemplateResponse("index.html", {
                "request": request,
                "success": True,
                "filename": filename,
                "file_url": file_url
            })
        return templates.TemplateResponse("index.html", {"request": request, "error": True})
    except Exception as e:
        return templates.TemplateResponse("index.html", {"request": request, "error": True, "err": str(e)})

@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    tpl = Path("templates/login.html")
    if not tpl.exists():
        return HTMLResponse("<h2>Login template missing</h2>", status_code=200)
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == settings.web.admin_username and password == settings.web.admin_password:
        request.session["auth"] = True
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "البيانات غير صحيحة"})

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not request.session.get("auth"):
        return RedirectResponse("/login", status_code=302)

    # Pagination settings
    ITEMS_PER_PAGE = settings.web.items_per_page
    
    # Get page parameters for each table
    downloads_page = int(request.query_params.get('downloads_page', 1))
    errors_page = int(request.query_params.get('errors_page', 1))
    users_page = int(request.query_params.get('users_page', 1))
    
    # Calculate OFFSET for each table
    downloads_offset = (downloads_page - 1) * ITEMS_PER_PAGE
    errors_offset = (errors_page - 1) * ITEMS_PER_PAGE
    users_offset = (users_page - 1) * ITEMS_PER_PAGE

    # Get real database statistics
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Get total counts for pagination
        cur.execute("SELECT COUNT(*) FROM downloads")
        total_downloads_db = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM errors")
        total_errors_db = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM (SELECT source FROM downloads GROUP BY source)")
        total_sources_db = cur.fetchone()[0]
        
        # Get blocked users count
        cur.execute("SELECT COUNT(*) FROM blocked_users")
        blocked_users_count = cur.fetchone()[0]
        
        # Get users count
        cur.execute("SELECT COUNT(*) FROM users")
        users_count = cur.fetchone()[0]
        
        # Get paginated downloads data
        cur.execute("""
            SELECT filename, name, source, url, timestamp 
            FROM downloads 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, downloads_offset))
        downloads = cur.fetchall()
        # Convert to dict format for template compatibility
        downloads = [
            {'filename': row[0], 'name': row[1], 'source': row[2], 'url': row[3], 'timestamp': row[4]}
            for row in downloads
        ]
        
        # Get paginated errors data
        cur.execute("""
            SELECT file_id, timestamp, username, chat_id, name, url, error 
            FROM errors 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, errors_offset))
        errors = cur.fetchall()
        # Convert to dict format for template compatibility
        errors = [
            {'file_id': row[0], 'timestamp': row[1], 'username': row[2], 'chat_id': row[3], 'name': row[4], 'url': row[5], 'error': row[6]}
            for row in errors
        ]
        
        # Get top sources (not paginated)
        cur.execute("""
            SELECT source, COUNT(*) as count 
            FROM downloads 
            GROUP BY source 
            ORDER BY count DESC 
            LIMIT 10
        """)
        top_sources = cur.fetchall()
        top_sources = [
            {'source': row[0], 'count': row[1]}
            for row in top_sources
        ]
        
        # Get paginated users data with sorting support
        sort_by = request.query_params.get('sort_by', 'downloads_count')  # Default: downloads_count
        sort_order = request.query_params.get('sort_order', 'DESC')  # Default: DESC
        
        # Safe column mapping to prevent SQL injection
        safe_columns = {
            'downloads_count': 'COUNT(d.chat_id)',
            'last_used': 'MAX(d.timestamp)'
        }
        
        # Validate and sanitize sort_by parameter
        if sort_by not in safe_columns:
            sort_by = 'downloads_count'
        
        # Validate sort_order parameter
        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'
        
        # Build safe SQL query using parameterized approach
        order_by_clause = f"{safe_columns[sort_by]} {sort_order}"
        
        cur.execute(f"""
            SELECT u.chat_id, u.name, u.username, 
                   COUNT(d.chat_id) as downloads_count,
                   MAX(d.timestamp) as last_used
            FROM users u 
            LEFT JOIN downloads d ON u.chat_id = d.chat_id 
            GROUP BY u.chat_id, u.name, u.username
            ORDER BY {order_by_clause}
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, users_offset))
        users_data = cur.fetchall()
        
        # Calculate pagination metadata for each table
        def get_pagination_info(total_items, current_page, items_per_page):
            total_pages = (total_items + items_per_page - 1) // items_per_page
            return {
                'total_items': total_items,
                'current_page': current_page,
                'total_pages': total_pages,
                'items_per_page': items_per_page,
                'has_prev': current_page > 1,
                'has_next': current_page < total_pages,
                'start_item': (current_page - 1) * items_per_page + 1,
                'end_item': min(current_page * items_per_page, total_items)
            }
        
        downloads_pagination = get_pagination_info(total_downloads_db, downloads_page, ITEMS_PER_PAGE)
        errors_pagination = get_pagination_info(total_errors_db, errors_page, ITEMS_PER_PAGE)
        users_pagination = get_pagination_info(users_count, users_page, ITEMS_PER_PAGE)
        
        total_operations = total_downloads_db + total_errors_db
        if total_operations > 0:
            success_rate = (total_downloads_db / total_operations) * 100
        else:
            success_rate = 100.0
    finally:
        conn.close()

    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    tpl = Path("templates/dashboard.html")
    if not tpl.exists():
        return HTMLResponse(
            "<h2>Dashboard</h2>"
            f"<p>downloads: {len(downloads)}</p>"
            f"<p>errors: {len(errors)}</p>"
            f"<p>top_sources: {top_sources}</p>", status_code=200
        )

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "downloads": downloads,
        "errors": errors,
        "top_sources": top_sources,
        "now": now,
        "total_downloads": total_downloads_db,
        "total_errors": total_errors_db,
        "total_sources": total_sources_db,
        "success_rate": success_rate,
        "blocked_users_count": blocked_users_count,
        "users_count": users_count,
        "users_data": users_data,
        "downloads_pagination": downloads_pagination,
        "errors_pagination": errors_pagination,
        "users_pagination": users_pagination
    })

# API Endpoints for AJAX Pagination
@app.get("/api/downloads")
async def api_downloads(request: Request, page: int = 1):
    """API endpoint for downloads table with pagination"""
    if not request.session.get("auth"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    ITEMS_PER_PAGE = settings.web.items_per_page
    offset = (page - 1) * ITEMS_PER_PAGE
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Get total count
        cur.execute("SELECT COUNT(*) FROM downloads")
        total_items = cur.fetchone()[0]
        
        # Get paginated data
        cur.execute("""
            SELECT filename, name, source, url, timestamp 
            FROM downloads 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, offset))
        downloads = cur.fetchall()
        
        # Convert to dict format
        data = [
            {'filename': row[0], 'name': row[1], 'source': row[2], 'url': row[3], 'timestamp': row[4]}
            for row in downloads
        ]
        
        # Calculate pagination metadata
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        pagination = {
            'total_items': total_items,
            'current_page': page,
            'total_pages': total_pages,
            'items_per_page': ITEMS_PER_PAGE,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_item': (page - 1) * ITEMS_PER_PAGE + 1,
            'end_item': min(page * ITEMS_PER_PAGE, total_items)
        }
        
        return JSONResponse({
            'success': True,
            'data': data,
            'pagination': pagination
        })
    finally:
        conn.close()

@app.get("/api/users")
async def api_users(request: Request, page: int = 1, sort_by: str = "downloads_count", sort_order: str = "DESC"):
    """API endpoint for users table with pagination and sorting"""
    if not request.session.get("auth"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    ITEMS_PER_PAGE = settings.web.items_per_page
    offset = (page - 1) * ITEMS_PER_PAGE
    
    # Validate parameters
    safe_columns = {
        'downloads_count': 'COUNT(d.chat_id)',
        'last_used': 'MAX(d.timestamp)'
    }
    
    if sort_by not in safe_columns:
        sort_by = 'downloads_count'
    
    if sort_order not in ['ASC', 'DESC']:
        sort_order = 'DESC'
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Get total count
        cur.execute("SELECT COUNT(*) FROM users")
        total_items = cur.fetchone()[0]
        
        # Get paginated and sorted data
        order_by_clause = f"{safe_columns[sort_by]} {sort_order}"
        
        cur.execute(f"""
            SELECT u.chat_id, u.name, u.username, 
                   COUNT(d.chat_id) as downloads_count,
                   MAX(d.timestamp) as last_used
            FROM users u 
            LEFT JOIN downloads d ON u.chat_id = d.chat_id 
            GROUP BY u.chat_id, u.name, u.username
            ORDER BY {order_by_clause}
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, offset))
        users_data = cur.fetchall()
        
        # Calculate pagination metadata
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        pagination = {
            'total_items': total_items,
            'current_page': page,
            'total_pages': total_pages,
            'items_per_page': ITEMS_PER_PAGE,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_item': (page - 1) * ITEMS_PER_PAGE + 1,
            'end_item': min(page * ITEMS_PER_PAGE, total_items)
        }
        
        return JSONResponse({
            'success': True,
            'data': users_data,
            'pagination': pagination
        })
    finally:
        conn.close()

@app.get("/api/errors")
async def api_errors(request: Request, page: int = 1):
    """API endpoint for errors table with pagination"""
    if not request.session.get("auth"):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    ITEMS_PER_PAGE = settings.web.items_per_page
    offset = (page - 1) * ITEMS_PER_PAGE
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Get total count
        cur.execute("SELECT COUNT(*) FROM errors")
        total_items = cur.fetchone()[0]
        
        # Get paginated data with all error details
        cur.execute("""
            SELECT file_id, timestamp, username, chat_id, name, url, error 
            FROM errors 
            ORDER BY timestamp DESC 
            LIMIT ? OFFSET ?
        """, (ITEMS_PER_PAGE, offset))
        errors = cur.fetchall()
        
        # Convert to dict format
        data = [
            {'file_id': row[0], 'timestamp': row[1], 'username': row[2], 'chat_id': row[3], 'name': row[4], 'url': row[5], 'error': row[6]}
            for row in errors
        ]
        
        # Calculate pagination metadata
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        pagination = {
            'total_items': total_items,
            'current_page': page,
            'total_pages': total_pages,
            'items_per_page': ITEMS_PER_PAGE,
            'has_prev': page > 1,
            'has_next': page < total_pages,
            'start_item': (page - 1) * ITEMS_PER_PAGE + 1,
            'end_item': min(page * ITEMS_PER_PAGE, total_items)
        }
        
        return JSONResponse({
            'success': True,
            'data': data,
            'pagination': pagination
        })
    finally:
        conn.close()

@app.post("/restart-bot")
async def restart_bot():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(settings.web.restart_endpoint)
            message = "✅ CoolDL Bot has been restarted successfully."
            if settings.bot.token and settings.bot.log_channel_id:
                await client.post(
                    f"https://api.telegram.org/bot{settings.bot.token}/sendMessage",
                    data={"chat_id": settings.bot.log_channel_id, "text": message}
                )
        return JSONResponse({"success": True, "message": response.text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))