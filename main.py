from models import get_all_downloads, get_errors, get_top_sources
from fastapi import FastAPI, Form, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from downloader import download_video
from starlette.middleware.sessions import SessionMiddleware
import os
import httpx
from pathlib import Path

# تأكد أن المجلدات موجودة
for d in ("downloads", "static", "templates"):
    Path(d).mkdir(parents=True, exist_ok=True)

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "secret-fahad-strong-key"))

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
    if username == "Fahad" and password == "213325@Fx9":
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

    downloads = get_all_downloads()
    errors = get_errors()
    top_sources = get_top_sources()

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
        "top_sources": top_sources
    })

@app.post("/restart-bot")
async def restart_bot():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:7070/restart")
            TELEGRAM_TOKEN = os.getenv("BOT_TOKEN")
            CHAT_ID = os.getenv("LOG_CHANNEL_ID") or os.getenv("CHANNEL_ID")
            message = "✅ CoolDL Bot has been restarted successfully."
            if TELEGRAM_TOKEN and CHAT_ID:
                await client.post(
                    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                    data={"chat_id": CHAT_ID, "text": message}
                )
        return JSONResponse({"success": True, "message": response.text})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
