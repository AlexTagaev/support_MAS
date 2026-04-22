"""Telegram integration based on aiogram."""

import asyncio
import time

from aiogram import Bot
from aiogram import Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import TelegramNetworkError
from aiogram.filters import Command
from aiogram.filters import CommandStart
from aiogram.types import BotCommand
from aiogram.types import Message
from loguru import logger

from app.config import settings
from app.core.ai_client import AIClient
from app.core.context_manager import ContextManager
from app.core.rag_engine import RAGEngine
from app.core.spam_filter import RateLimiter
from app.core.spam_filter import SpamFilter
from app.database.questions_db import QuestionsDB

TELEGRAM_REQUEST_TIMEOUT = 60
SEND_MAX_RETRIES = 3
SEND_RETRY_DELAYS = (1, 2, 4)

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    session=AiohttpSession(timeout=TELEGRAM_REQUEST_TIMEOUT),
)
dp = Dispatcher()

rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
ai = AIClient()
context_manager = ContextManager(max_context=settings.MAX_CONTEXT_MESSAGES)
rate_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_REQUESTS)
spam_filter = SpamFilter()
db = QuestionsDB()


async def safe_answer(message: Message, text: str) -> bool:
    """Send Telegram message with retries for transient network errors."""
    for attempt in range(1, SEND_MAX_RETRIES + 1):
        try:
            await message.answer(text, request_timeout=TELEGRAM_REQUEST_TIMEOUT)
            return True
        except TelegramNetworkError as exc:
            if attempt >= SEND_MAX_RETRIES:
                logger.error("Telegram send failed after {} attempts: {}", attempt, exc)
                return False
            delay = SEND_RETRY_DELAYS[min(attempt - 1, len(SEND_RETRY_DELAYS) - 1)]
            logger.warning(
                "Telegram send failed (attempt {}/{}), retry in {}s: {}",
                attempt,
                SEND_MAX_RETRIES,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    return False


@dp.message(CommandStart())
async def cmd_start(message: Message):
    welcome_text = (
        "Здравствуйте! Я ваш нейро-консультант Школы Михаила Агеева. 🌟\n\n"
        "Я помогу вам узнать больше о наших программах обучения, "
        "методиках духовного развития и философии школы. "
        "Просто задайте свой вопрос, и я постараюсь ответить максимально подробно на основе знаний школы. "
        "Чем я могу быть полезен?"
    )
    await safe_answer(message, welcome_text)


@dp.message(Command("clear_history"))
async def cmd_clear_history(message: Message):
    user_id = f"telegram_{message.from_user.id}"
    await context_manager.clear_context(user_id)
    await safe_answer(message, "История диалога очищена. Можем начать с чистого листа.")


@dp.message()
async def handle_message(message: Message):
    if message.text and message.text.startswith("/"):
        return

    user_id = f"telegram_{message.from_user.id}"
    text = message.text
    if not text:
        return

    started_at = time.monotonic()

    if not await rate_limiter.check_limit(user_id):
        await safe_answer(message, "Превышен лимит запросов. Попробуйте позже.")
        return
    await rate_limiter.increment(user_id)

    if await spam_filter.is_spam(user_id, text):
        return

    await db.add_question(text, "telegram")

    rag_started_at = time.monotonic()
    history = await context_manager.get_context(user_id)
    rag_context = await rag.get_context_for_query(text)
    rag_ms = (time.monotonic() - rag_started_at) * 1000

    llm_started_at = time.monotonic()
    response_text = await ai.generate_response(
        user_question=text,
        rag_context=rag_context,
        conversation_history=history,
        system_prompt=settings.SYSTEM_PROMPT,
    )
    llm_ms = (time.monotonic() - llm_started_at) * 1000

    await context_manager.add_message(user_id, "user", text)
    await context_manager.add_message(user_id, "assistant", response_text)

    send_started_at = time.monotonic()
    sent = await safe_answer(message, response_text)
    send_ms = (time.monotonic() - send_started_at) * 1000
    total_ms = (time.monotonic() - started_at) * 1000

    logger.info(
        "Telegram pipeline user={} sent={} rag_ms={:.0f} llm_ms={:.0f} send_ms={:.0f} total_ms={:.0f}",
        user_id,
        sent,
        rag_ms,
        llm_ms,
        send_ms,
        total_ms,
    )


async def start_bot():
    if settings.TELEGRAM_USE_WEBHOOK:
        logger.info("Telegram bot starting in Webhook mode")
    else:
        logger.info("Telegram bot starting in Polling mode")
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Запустить бота"),
                BotCommand(command="clear_history", description="Очистить историю диалога"),
            ]
        )
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
