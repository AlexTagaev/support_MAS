"""FastAPI entry point and application lifecycle."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from loguru import logger

from app.admin.routes import router as admin_router
from app.config import settings
from app.core.provider_clients import close_async_clients
from app.core.rag_engine import get_rag_engine
from app.database.questions_db import QuestionsDB, engine
from app.integrations.jivo_webhook import router as jivo_router
from app.integrations.telegram_bot import bot, drain_question_analytics, start_bot
from app.utils.logger import setup_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logger()
    if settings.TELEGRAM_USE_WEBHOOK:
        raise RuntimeError("Telegram webhook mode is not implemented; set TELEGRAM_USE_WEBHOOK=false")

    db = QuestionsDB()
    await db.init_db()
    app.state.db = db
    app.state.telegram_task = asyncio.create_task(start_bot(), name="telegram-polling")
    logger.info("Application started in Telegram polling mode")
    try:
        yield
    finally:
        app.state.telegram_task.cancel()
        await asyncio.gather(app.state.telegram_task, return_exceptions=True)
        await drain_question_analytics()
        await bot.session.close()
        await engine.dispose()
        await close_async_clients()


app = FastAPI(
    title="Школа Агеева - Нейро-техподдержка",
    version="1.0.0",
    debug=settings.DEBUG,
    lifespan=lifespan,
)
app.include_router(admin_router)
app.include_router(jivo_router)


@app.get("/health")
async def health_check(request: Request):
    """Report real local readiness without calling paid AI APIs."""
    checks = {"database": "error", "faiss_index": "error", "telegram_polling": "error"}
    try:
        await request.app.state.db.check_db()
        checks["database"] = "ok"
    except Exception:
        logger.exception("Database readiness check failed")

    rag = get_rag_engine()
    if rag.index is not None:
        checks["faiss_index"] = "ok"
    task = getattr(request.app.state, "telegram_task", None)
    if task is not None and not task.done():
        checks["telegram_polling"] = "ok"

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail={"status": "not_ready", "checks": checks})
    return {"status": "healthy", "version": "1.0.0", "checks": checks}


@app.post("/api/telegram/webhook")
async def telegram_webhook():
    """Webhook delivery is not implemented; polling is the supported mode."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Telegram webhook mode is not implemented; use polling",
    )
