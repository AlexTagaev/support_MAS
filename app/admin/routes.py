import os
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.admin.auth import verify_admin
from app.config import settings
from app.core.rag_engine import RAGEngine
from app.database.questions_db import QuestionsDB
from app.core.ai_client import AIClient
from loguru import logger

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/admin/templates")

rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
db = QuestionsDB()
ai = AIClient()

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(verify_admin)):
    questions = await db.get_all_questions()
    return templates.TemplateResponse("analytics.html", {
        "request": request, 
        "questions": questions,
        "active_page": "analytics"
    })

@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(request: Request, username: str = Depends(verify_admin)):
    content = ""
    if os.path.exists(settings.KNOWLEDGE_BASE_PATH):
        with open(settings.KNOWLEDGE_BASE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
    return templates.TemplateResponse("knowledge.html", {
        "request": request, 
        "content": content,
        "active_page": "knowledge"
    })

@router.post("/api/knowledge")
async def save_knowledge(content: str = Form(...), username: str = Depends(verify_admin)):
    with open(settings.KNOWLEDGE_BASE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return {"status": "success"}

@router.post("/api/rebuild")
async def rebuild_index(username: str = Depends(verify_admin)):
    rag.rebuild_index()
    return {"status": "success"}

@router.get("/test", response_class=HTMLResponse)
async def testing_page(request: Request, username: str = Depends(verify_admin)):
    return templates.TemplateResponse("testing.html", {
        "request": request,
        "active_page": "testing"
    })

@router.post("/api/test")
async def test_query(question: str = Form(...), username: str = Depends(verify_admin)):
    rag_context = await rag.get_context_for_query(question)
    response = await ai.generate_response(
        user_question=question,
        rag_context=rag_context,
        conversation_history=[],
        system_prompt=settings.SYSTEM_PROMPT
    )
    return {
        "answer": response,
        "context": rag_context
    }
