from models import get_all_downloads, get_errors, get_top_sources
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from downloader import download_video
from starlette.middleware.sessions import SessionMiddleware
import os
import humanize
import datetime
from pathlib import Path

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key="secret-fahad-strong-key")

# مسارات القوالب والملفات
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/downloads", StaticFiles(directory="downloads"), name="downloads")

# الصفحة الرئيسية
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# عملية التحميل
@app.post("/download", response_class=HTMLResponse)
async def download(request: Request, video_url: str = Form(...)):
    file_path = await download_video(video_url)
    if file_path:
        filename = os.path.basename(file_path)
        source_path = f"downloads/source_{filename}.txt"
        with open(source_path, "w") as f:
            f.write("web")
        file_url = f"/downloads/{filename}"
        return templates.TemplateResponse("index.html", {
            "request": request,
            "success": True,
            "filename": filename,
            "file_url": file_url
        })
    return templates.TemplateResponse("index.html", {
        "request": request,
        "error": True
    })

# صفحة تسجيل الدخول
@app.get("/login", response_class=HTMLResponse)
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == "Fahad" and password == "213325@Fx9":
        request.session["auth"] = True
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse("login.html", {
        "request": request,
        "error": "البيانات غير صحيحة"
    })

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)

# لوحة التحكم
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not request.session.get("auth"):
        return RedirectResponse("/login", status_code=302)

    downloads = get_all_downloads()
    errors = get_errors()
    top_sources = get_top_sources()

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "downloads": downloads,
        "errors": errors,
        "top_sources": top_sources
    })
