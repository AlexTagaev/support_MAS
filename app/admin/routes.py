"""Роуты админ-панели.

Админка предназначена для внутреннего использования:
- просмотр аналитики уникальных вопросов;
- редактирование Markdown базы знаний;
- пересборка FAISS индекса;
- настройка параметров LLM провайдера в `.env` и runtime.
"""

import os
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.admin.auth import verify_admin
from app.config import settings
from app.core.ai_client import AIClient
from app.core.rag_engine import RAGEngine
from app.database.questions_db import QuestionsDB

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/admin/templates")

# В текущей архитектуре используем глобальные singletons на модуль.
# Это упрощает запуск. При росте нагрузки лучше перейти на DI.
rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
db = QuestionsDB()
ai = AIClient()


def _update_env_file(updates: dict[str, str]) -> None:
    """Обновляет .env и добавляет отсутствующие ключи."""
    env_path = Path(".env")
    lines = []
    if env_path.exists():
        with env_path.open("r", encoding="utf-8") as env_file:
            lines = env_file.readlines()

    updated_lines = []
    seen_keys = set()

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            updated_lines.append(line)
            continue

        key, _ = line.split("=", 1)
        env_key = key.strip()
        if env_key in updates:
            updated_lines.append(f"{env_key}={updates[env_key]}\n")
            seen_keys.add(env_key)
        else:
            updated_lines.append(line)

    for env_key, env_value in updates.items():
        if env_key not in seen_keys:
            updated_lines.append(f"{env_key}={env_value}\n")

    with env_path.open("w", encoding="utf-8") as env_file:
        env_file.writelines(updated_lines)


def _apply_runtime_ai_settings(updates: dict[str, str]) -> None:
    """Применяет AI-настройки в runtime без перезапуска."""
    for key, value in updates.items():
        if hasattr(settings, key):
            setattr(settings, key, value)


def _is_valid_url(url: str) -> bool:
    """Проверяет, что строка похожа на корректный HTTP(S) URL."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, username: str = Depends(verify_admin)):
    """Главная страница админки: аналитика уникальных вопросов."""
    questions = await db.get_all_questions()
    return templates.TemplateResponse("analytics.html", {
        "request": request, 
        "questions": questions,
        "active_page": "analytics"
    })

@router.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(request: Request, username: str = Depends(verify_admin)):
    """Страница просмотра/редактирования базы знаний (Markdown)."""
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
    """Сохраняет обновлённый Markdown базы знаний на диск."""
    with open(settings.KNOWLEDGE_BASE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return {"status": "success"}

@router.post("/api/rebuild")
async def rebuild_index(username: str = Depends(verify_admin)):
    """Пересобирает FAISS индекс по актуальной базе знаний."""
    rag.rebuild_index()
    return {"status": "success"}

@router.get("/test", response_class=HTMLResponse)
async def testing_page(request: Request, username: str = Depends(verify_admin)):
    """UI-страница для ручного тестирования вопросов к ассистенту."""
    return templates.TemplateResponse("testing.html", {
        "request": request,
        "active_page": "testing"
    })


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request, username: str = Depends(verify_admin)):
    """UI-страница настроек LLM провайдера и модели."""
    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "active_page": "settings",
            "llm_provider": settings.LLM_PROVIDER,
            "openai_api_key": settings.OPENAI_API_KEY,
            "openai_api_base": settings.OPENAI_API_BASE or "",
            "proxiapi_api_key": settings.PROXIAPI_API_KEY or "",
            "proxiapi_api_base": settings.PROXIAPI_API_BASE,
            "ai_model": settings.AI_MODEL
        }
    )


@router.post("/api/settings/ai")
async def save_ai_settings(
    llm_provider: str = Form(...),
    openai_api_key: str = Form(...),
    openai_api_base: str = Form(""),
    proxiapi_api_key: str = Form(""),
    proxiapi_api_base: str = Form(...),
    ai_model: str = Form(...),
    username: str = Depends(verify_admin)
):
    """Сохраняет AI-настройки в `.env` и применяет их в runtime."""
    provider = llm_provider.strip().lower()
    openai_key = openai_api_key.strip()
    openai_base = openai_api_base.strip()
    proxiapi_key = proxiapi_api_key.strip()
    proxiapi_base = proxiapi_api_base.strip()
    model = ai_model.strip()

    if provider not in {"openai", "proxiapi"}:
        return {
            "status": "error",
            "message": "Провайдер должен быть openai или proxiapi."
        }

    if not model:
        return {
            "status": "error",
            "message": "Поле AI_MODEL не должно быть пустым."
        }

    if provider == "openai" and not openai_key:
        return {
            "status": "error",
            "message": "Для OpenAI укажите OPENAI_API_KEY."
        }

    if provider == "proxiapi":
        if not proxiapi_key:
            return {
                "status": "error",
                "message": "Для ProxiAPI укажите PROXIAPI_API_KEY."
            }
        if not proxiapi_base:
            return {
                "status": "error",
                "message": "Для ProxiAPI укажите PROXIAPI_API_BASE."
            }

    if openai_base and not _is_valid_url(openai_base):
        return {
            "status": "error",
            "message": "OPENAI_API_BASE должен быть корректным URL."
        }

    if proxiapi_base and not _is_valid_url(proxiapi_base):
        return {
            "status": "error",
            "message": "PROXIAPI_API_BASE должен быть корректным URL."
        }

    env_updates = {
        "LLM_PROVIDER": provider,
        "OPENAI_API_KEY": openai_key,
        "OPENAI_API_BASE": openai_base,
        "PROXIAPI_API_KEY": proxiapi_key,
        "PROXIAPI_API_BASE": proxiapi_base,
        "AI_MODEL": model
    }
    _update_env_file(env_updates)
    _apply_runtime_ai_settings(env_updates)
    logger.info("AI settings updated by admin")
    return {"status": "success"}


@router.post("/api/test")
async def test_query(question: str = Form(...), username: str = Depends(verify_admin)):
    """Возвращает ответ модели и контекст (для проверки качества RAG)."""
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
