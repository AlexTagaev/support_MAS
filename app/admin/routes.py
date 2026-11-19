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

from fastapi import APIRouter, Depends, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.admin.auth import verify_admin
from app.config import settings
from app.core.ai_client import AIClient
from app.core.rag_engine import get_rag_engine
from app.database.questions_db import QuestionsDB
from app.admin.integration_settings import integration_settings

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/admin/templates")

# В текущей архитектуре используем глобальные singletons на модуль.
# Это упрощает запуск. При росте нагрузки лучше перейти на DI.
rag = get_rag_engine()
db = QuestionsDB()
ai = AIClient()


async def verify_same_origin(request: Request) -> None:
    """Reject cross-origin browser requests to state-changing admin routes."""
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")
    source = origin or referer
    host = request.headers.get("host", "").lower()
    source_host = urlparse(source).netloc.lower() if source else ""
    if not host or not source_host or source_host != host:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-origin admin request rejected",
        )


def _update_env_file(updates: dict[str, str]) -> None:
    """Обновляет .env и добавляет отсутствующие ключи."""
    env_path = Path(".env")
    if not env_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Persistent .env file is not mounted; AI settings were not saved",
        )
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
async def save_knowledge(
    content: str = Form(...),
    username: str = Depends(verify_admin),
    _same_origin: None = Depends(verify_same_origin),
):
    """Сохраняет обновлённый Markdown базы знаний на диск."""
    with open(settings.KNOWLEDGE_BASE_PATH, "w", encoding="utf-8") as f:
        f.write(content)
    return {"status": "success"}

@router.post("/api/rebuild")
async def rebuild_index(
    username: str = Depends(verify_admin),
    _same_origin: None = Depends(verify_same_origin),
):
    """Пересобирает FAISS индекс по актуальной базе знаний."""
    try:
        await rag.rebuild_index()
    except ValueError as exc:
        logger.warning("Knowledge index rebuild rejected: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Проверьте, что база знаний не пуста и может быть обработана.",
        ) from exc
    except Exception as exc:
        logger.exception("Knowledge index rebuild failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось пересобрать индекс. Проверьте доступность AI API и попробуйте ещё раз.",
        ) from exc
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
            "openai_api_base": settings.OPENAI_API_BASE or "",
            "openai_key_configured": bool(settings.OPENAI_API_KEY),
            "proxiapi_key_configured": bool(settings.PROXIAPI_API_KEY),
            "proxiapi_api_base": settings.PROXIAPI_API_BASE,
            "ai_model": settings.AI_MODEL,
            "jivo": integration_settings.jivo_status(),
        }
    )


@router.post("/api/settings/ai")
async def save_ai_settings(
    llm_provider: str = Form(...),
    openai_api_key: str = Form(""),
    clear_openai_api_key: str = Form(""),
    openai_api_base: str = Form(""),
    proxiapi_api_key: str = Form(""),
    clear_proxiapi_api_key: str = Form(""),
    proxiapi_api_base: str = Form(...),
    ai_model: str = Form(...),
    username: str = Depends(verify_admin),
    _same_origin: None = Depends(verify_same_origin),
):
    """Сохраняет AI-настройки в `.env` и применяет их в runtime."""
    provider = llm_provider.strip().lower()
    openai_key = openai_api_key.strip() or settings.OPENAI_API_KEY
    if clear_openai_api_key:
        openai_key = ""
    openai_base = openai_api_base.strip()
    proxiapi_key = proxiapi_api_key.strip() or ("" if clear_proxiapi_api_key else settings.PROXIAPI_API_KEY or "")
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
        "OPENAI_API_BASE": openai_base,
        "PROXIAPI_API_BASE": proxiapi_base,
        "AI_MODEL": model
    }
    if openai_api_key.strip() or clear_openai_api_key:
        env_updates["OPENAI_API_KEY"] = openai_key
    if proxiapi_api_key.strip() or clear_proxiapi_api_key:
        env_updates["PROXIAPI_API_KEY"] = proxiapi_key
    _update_env_file(env_updates)
    _apply_runtime_ai_settings(env_updates)
    logger.info("AI settings updated by admin")
    return {"status": "success"}


@router.post("/api/settings/jivo")
async def save_jivo_settings(
    enabled: bool = Form(False),
    bot_token: str = Form(""),
    webhook_secret: str = Form(""),
    clear_bot_token: bool = Form(False),
    clear_webhook_secret: bool = Form(False),
    username: str = Depends(verify_admin),
    _same_origin: None = Depends(verify_same_origin),
):
    """Stores Jivo connection details. Webhook processing is not enabled yet."""
    integration_settings.save_jivo(
        enabled=enabled,
        bot_token=bot_token.strip(),
        webhook_secret=webhook_secret.strip(),
        clear_token=clear_bot_token,
        clear_secret=clear_webhook_secret,
    )
    logger.info("Jivo integration settings saved; webhook handling remains inactive")
    return {"status": "saved", "message": "Параметры сохранены. Обработка вебхуков пока не подключена."}


@router.post("/api/test")
async def test_query(
    question: str = Form(...),
    username: str = Depends(verify_admin),
    _same_origin: None = Depends(verify_same_origin),
):
    """Возвращает ответ модели и контекст (для проверки качества RAG)."""
    if not question.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Введите непустой вопрос.",
        )
    if rag.index is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Сначала постройте индекс базы знаний.",
        )
    try:
        rag_context = await rag.get_context_for_query(question)
    except Exception as exc:
        logger.exception("Admin RAG test lookup failed: {}", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Не удалось выполнить поиск по базе знаний.",
        ) from exc
    if not rag_context.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="По запросу не найден контекст в базе знаний.",
        )
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
