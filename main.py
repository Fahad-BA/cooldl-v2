from models import get_all_downloads, get_errors, get_top_sources, get_connection, get_questions, get_questions_with_answers, get_answers_for_question, create_question, create_answer
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
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "SECRET_REMOVED"))

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
    if username == "Fahad" and password == "PASSWORD_REMOVED":
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

    # Get real database statistics
    downloads = get_all_downloads()
    errors = get_errors()
    top_sources = get_top_sources()
    
    # Get actual counts from database
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM downloads")
        total_downloads_db = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM errors")
        total_errors_db = cur.fetchone()[0]
        
        cur.execute("SELECT COUNT(*) FROM (SELECT source FROM downloads GROUP BY source)")
        total_sources_db = cur.fetchone()[0]
        
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
        "success_rate": success_rate
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

# Ask-Project API Endpoints
@app.get("/api/questions")
async def api_questions(request: Request, category: str = None, difficulty: str = None, limit: int = 50):
    """API endpoint to get questions"""
    questions = get_questions(category=category, difficulty=difficulty, limit=limit)
    return JSONResponse({"success": True, "questions": questions})

@app.get("/api/questions-with-answers")
async def api_questions_with_answers(request: Request, category: str = None, difficulty: str = None, limit: int = 50):
    """API endpoint to get questions with their answers"""
    questions = get_questions_with_answers(category=category, difficulty=difficulty, limit=limit)
    return JSONResponse({"success": True, "questions": questions})

@app.get("/api/answers/{question_id}")
async def api_answers_for_question(request: Request, question_id: int):
    """API endpoint to get answers for a specific question"""
    answers = get_answers_for_question(question_id)
    return JSONResponse({"success": True, "question_id": question_id, "answers": answers})

@app.post("/api/create-question")
async def api_create_question(request: Request, question_text: str = Form(...), category: str = Form("general"), difficulty: str = Form("medium")):
    """API endpoint to create a new question"""
    result = create_question(question_text, category, difficulty)
    if result["success"]:
        return JSONResponse({"success": True, "question_id": result["question_id"]})
    else:
        raise HTTPException(status_code=400, detail=result["error"])

@app.post("/api/create-answer")
async def api_create_answer(request: Request, question_id: int = Form(...), answer_text: str = Form(...), is_correct: bool = Form(False)):
    """API endpoint to create a new answer"""
    result = create_answer(question_id, answer_text, is_correct)
    if result["success"]:
        return JSONResponse({"success": True, "answer_id": result["answer_id"]})
    else:
        raise HTTPException(status_code=400, detail=result["error"])

@app.get("/ask-project", response_class=HTMLResponse)
async def ask_project_page(request: Request):
    """Basic HTML page for testing ask-project functionality"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Ask-Project - CoolDL</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
            .question { margin: 20px 0; padding: 15px; background: #f9f9f9; border-left: 4px solid #007bff; }
            .answers { margin: 10px 0 0 20px; }
            .answer { margin: 5px 0; padding: 8px; background: #fff; border: 1px solid #ddd; }
            .correct { background: #d4edda; border-color: #28a745; }
            .category { display: inline-block; background: #007bff; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; }
            .difficulty { display: inline-block; background: #6c757d; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 5px; }
            h1 { color: #333; }
            .form-group { margin: 15px 0; }
            label { display: block; margin-bottom: 5px; font-weight: bold; }
            input, textarea, select { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; }
            button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            button:hover { background: #0056b3; }
            .error { color: red; margin: 10px 0; }
            .success { color: green; margin: 10px 0; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Ask-Project - Questions & Answers</h1>
            
            <div id="questions-container">
                <h2>Questions with Answers</h2>
                <div id="questions-list">Loading...</div>
            </div>
            
            <hr>
            
            <div class="form-section">
                <h2>Add New Question</h2>
                <form id="add-question-form">
                    <div class="form-group">
                        <label for="question-text">Question Text:</label>
                        <textarea id="question-text" name="question_text" rows="3" required></textarea>
                    </div>
                    <div class="form-group">
                        <label for="category">Category:</label>
                        <select id="category" name="category">
                            <option value="general">General</option>
                            <option value="science">Science</option>
                            <option value="math">Math</option>
                            <option value="geography">Geography</option>
                            <option value="history">History</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="difficulty">Difficulty:</label>
                        <select id="difficulty" name="difficulty">
                            <option value="easy">Easy</option>
                            <option value="medium">Medium</option>
                            <option value="hard">Hard</option>
                        </select>
                    </div>
                    <button type="submit">Add Question</button>
                </form>
            </div>
            
            <div class="form-section">
                <h2>Add Answer to Question</h2>
                <form id="add-answer-form">
                    <div class="form-group">
                        <label for="question-id">Question ID:</label>
                        <input type="number" id="question-id" name="question_id" required>
                    </div>
                    <div class="form-group">
                        <label for="answer-text">Answer Text:</label>
                        <input type="text" id="answer-text" name="answer_text" required>
                    </div>
                    <div class="form-group">
                        <label>
                            <input type="checkbox" id="is-correct" name="is_correct">
                            Is Correct Answer
                        </label>
                    </div>
                    <button type="submit">Add Answer</button>
                </form>
            </div>
            
            <div id="message"></div>
        </div>
        
        <script>
            // Load questions on page load
            document.addEventListener('DOMContentLoaded', function() {
                loadQuestions();
            });
            
            async function loadQuestions() {
                try {
                    const response = await fetch('/api/questions-with-answers');
                    const data = await response.json();
                    
                    if (data.success) {
                        displayQuestions(data.questions);
                    } else {
                        document.getElementById('questions-list').innerHTML = '<p class="error">Error loading questions</p>';
                    }
                } catch (error) {
                    document.getElementById('questions-list').innerHTML = '<p class="error">Error: ' + error.message + '</p>';
                }
            }
            
            function displayQuestions(questions) {
                const container = document.getElementById('questions-list');
                
                if (questions.length === 0) {
                    container.innerHTML = '<p>No questions found.</p>';
                    return;
                }
                
                let html = '';
                questions.forEach(question => {
                    html += '<div class="question">';
                    html += '<h3>' + question.question_text + '</h3>';
                    html += '<span class="category">' + question.category + '</span>';
                    html += '<span class="difficulty">' + question.difficulty + '</span>';
                    html += '<small> (ID: ' + question.id + ')</small>';
                    
                    if (question.answers && question.answers.length > 0) {
                        html += '<div class="answers"><h4>Answers:</h4>';
                        question.answers.forEach(answer => {
                            html += '<div class="answer ' + (answer.is_correct ? 'correct' : '') + '">';
                            html += answer.answer_text;
                            if (answer.is_correct) {
                                html += ' ✓ (Correct)';
                            }
                            html += '</div>';
                        });
                        html += '</div>';
                    } else {
                        html += '<p><em>No answers yet.</em></p>';
                    }
                    
                    html += '</div>';
                });
                
                container.innerHTML = html;
            }
            
            // Handle add question form
            document.getElementById('add-question-form').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData(e.target);
                
                try {
                    const response = await fetch('/api/create-question', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        showMessage('Question added successfully!', 'success');
                        e.target.reset();
                        loadQuestions(); // Reload questions
                    } else {
                        showMessage('Error adding question: ' + result.error, 'error');
                    }
                } catch (error) {
                    showMessage('Error: ' + error.message, 'error');
                }
            });
            
            // Handle add answer form
            document.getElementById('add-answer-form').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData(e.target);
                
                try {
                    const response = await fetch('/api/create-answer', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const result = await response.json();
                    
                    if (result.success) {
                        showMessage('Answer added successfully!', 'success');
                        e.target.reset();
                        loadQuestions(); // Reload questions
                    } else {
                        showMessage('Error adding answer: ' + result.error, 'error');
                    }
                } catch (error) {
                    showMessage('Error: ' + error.message, 'error');
                }
            });
            
            function showMessage(message, type) {
                const messageDiv = document.getElementById('message');
                messageDiv.innerHTML = '<div class="' + type + '">' + message + '</div>';
                setTimeout(() => {
                    messageDiv.innerHTML = '';
                }, 5000);
            }
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(html_content)
