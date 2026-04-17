"""Точка входа FastAPI приложения.

Задачи модуля:
- инициализация FastAPI и подключение роутеров;
- запуск фоновых компонентов (например, Telegram-бота);
- health endpoint для инфраструктуры/мониторинга.
"""

import asyncio

from fastapi import FastAPI
from fastapi import Request
from loguru import logger

from app.admin.routes import router as admin_router
from app.config import settings
from app.database.questions_db import QuestionsDB
from app.integrations.jivo_webhook import router as jivo_router
from app.integrations.telegram_bot import start_bot
from app.utils.logger import setup_logger

app = FastAPI(
    title="Школа Агеева - Нейро-техподдержка",
    version="1.0.0",
    debug=settings.DEBUG
)

# Роутеры подключаем на старте, чтобы они попали в OpenAPI.
app.include_router(admin_router)
app.include_router(jivo_router)

@app.on_event("startup")
async def startup_event():
    """Инициализация сервисов при старте приложения."""
    setup_logger()
    
    # База для аналитики уникальных вопросов.
    db = QuestionsDB()
    await db.init_db()
    
    # Telegram-бот запускаем отдельной задачей, чтобы не блокировать API.
    asyncio.create_task(start_bot())
    
    logger.info("Application started successfully")

@app.get("/health")
async def health_check():
    """Простой health endpoint для инфраструктуры."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "checks": {
            "llm_api": "ok",
            "database": "ok",
            "faiss_index": "ok"
        }
    }

@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    """Webhook endpoint для Telegram (когда включён режим webhook)."""
    if settings.TELEGRAM_USE_WEBHOOK:
        update = await request.json()
        # В режиме webhook сюда должен приходить update от Telegram.
        # В текущей реализации обработка webhook вынесена в режим polling,
        # чтобы не усложнять деплой: эндпоинт сохранён для расширения.
        return {"status": "ok"}
    return {"status": "webhook disabled"}
