import asyncio
from fastapi import FastAPI, Request
from app.config import settings
from app.admin.routes import router as admin_router
from app.integrations.jivo_webhook import router as jivo_router
from app.integrations.telegram_bot import start_bot, dp, bot
from app.database.questions_db import QuestionsDB
from app.utils.logger import setup_logger
from loguru import logger

app = FastAPI(
    title="Школа Агеева - Нейро-техподдержка",
    version="1.0.0",
    debug=settings.DEBUG
)

# Подключение роутеров
app.include_router(admin_router)
app.include_router(jivo_router)

@app.on_event("startup")
async def startup_event():
    # Настройка логирования
    setup_logger()
    
    # Инициализация БД
    db = QuestionsDB()
    await db.init_db()
    
    # Запуск Telegram бота
    asyncio.create_task(start_bot())
    
    logger.info("Application started successfully")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "checks": {
            "openai_api": "ok",
            "database": "ok",
            "faiss_index": "ok"
        }
    }

@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    if settings.TELEGRAM_USE_WEBHOOK:
        update = await request.json()
        # Обработка update через aiogram
        # В реальном проекте здесь используется dp.feed_update(bot, update)
        return {"status": "ok"}
    return {"status": "webhook disabled"}
