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
from app.core.rag_engine import get_rag_engine
from app.core.spam_filter import RateLimiter
from app.core.spam_filter import SpamFilter
from app.database.questions_db import QuestionsDB

TELEGRAM_REQUEST_TIMEOUT = 60
SEND_MAX_RETRIES = 3
SEND_RETRY_DELAYS = (1, 2, 4)
MAX_PENDING_ANALYTICS = 32

bot = Bot(
    token=settings.TELEGRAM_BOT_TOKEN,
    session=AiohttpSession(timeout=TELEGRAM_REQUEST_TIMEOUT),
)
dp = Dispatcher()

rag = get_rag_engine()
ai = AIClient()
rate_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_REQUESTS, window=settings.RATE_LIMIT_WINDOW)
spam_filter = SpamFilter()
db = QuestionsDB()
context_manager = ContextManager(max_context=settings.MAX_CONTEXT_MESSAGES, ttl=settings.CONTEXT_TTL)
user_locks: dict[str, asyncio.Lock] = {}
analytics_tasks: set[asyncio.Task] = set()
analytics_semaphore = asyncio.Semaphore(4)


def conversation_key(message: Message) -> str | None:
    """Keep each user's history separate for each Telegram chat."""
    if message.from_user is None or message.chat is None:
        return None
    return f"telegram_{message.chat.id}_{message.from_user.id}"


async def _record_question_analytics(question: str) -> None:
    """Store analytics without delaying the Telegram response path."""
    try:
        async with analytics_semaphore:
            await db.add_question(question, "telegram")
    except Exception as exc:
        logger.warning("Question analytics unavailable: {}", exc)


def schedule_question_analytics(question: str) -> None:
    """Schedule a best-effort analytics write in the background."""
    if len(analytics_tasks) >= MAX_PENDING_ANALYTICS:
        logger.warning("Question analytics queue is full; dropping this analytics event")
        return
    task = asyncio.create_task(
        _record_question_analytics(question),
        name="telegram-question-analytics",
    )
    analytics_tasks.add(task)
    task.add_done_callback(analytics_tasks.discard)


async def drain_question_analytics(timeout: float = 5.0) -> None:
    """Give pending analytics a short shutdown window, then cancel them."""
    pending = tuple(analytics_tasks)
    if not pending:
        return
    _, unfinished = await asyncio.wait(pending, timeout=timeout)
    if unfinished:
        for task in unfinished:
            task.cancel()
        await asyncio.gather(*unfinished, return_exceptions=True)


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
    user_id = conversation_key(message)
    if user_id is None:
        return
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        await context_manager.clear_context(user_id)
        await safe_answer(message, "История диалога очищена. Можем начать с чистого листа.")


@dp.message()
async def handle_message(message: Message):
    user_id = conversation_key(message)
    if user_id is None:
        return
    lock = user_locks.setdefault(user_id, asyncio.Lock())
    async with lock:
        await _process_message(message, user_id)


async def _process_message(message: Message, user_id: str):
    if message.text and message.text.startswith("/"):
        return

    text = message.text
    if not text or not text.strip():
        return

    if rag.index is None:
        await safe_answer(
            message,
            "Сервис временно запускается. Пожалуйста, повторите запрос немного позже.",
        )
        return

    started_at = time.monotonic()

    if not await rate_limiter.check_limit(user_id):
        await safe_answer(message, "Превышен лимит запросов. Попробуйте позже.")
        return
    await rate_limiter.increment(user_id)

    if await spam_filter.is_spam(user_id, text):
        return

    schedule_question_analytics(text)

    rag_started_at = time.monotonic()
    history = await context_manager.get_context(user_id)
    try:
        rag_context = await rag.get_context_for_query(text)
    except Exception as exc:
        logger.exception("RAG lookup failed: {}", exc)
        await safe_answer(
            message,
            "Не удалось получить информацию для ответа. Пожалуйста, попробуйте позже.",
        )
        return
    if not rag_context.strip():
        await safe_answer(
            message,
            "Не удалось найти информацию по этому запросу. Попробуйте переформулировать его или обратитесь в поддержку.",
        )
        return
    rag_ms = (time.monotonic() - rag_started_at) * 1000

    llm_started_at = time.monotonic()
    response_text = await ai.generate_response(
        user_question=text,
        rag_context=rag_context,
        conversation_history=history,
        system_prompt=settings.SYSTEM_PROMPT,
    )
    llm_ms = (time.monotonic() - llm_started_at) * 1000

    send_started_at = time.monotonic()
    sent = await safe_answer(message, response_text)
    if sent:
        await context_manager.add_exchange(user_id, text, response_text)
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
        raise RuntimeError("Telegram webhook mode is not implemented")
    logger.info("Telegram bot starting in Polling mode")
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить бота"),
            BotCommand(command="clear_history", description="Очистить историю диалога"),
        ]
    )
    await bot.delete_webhook(drop_pending_updates=False)
    await dp.start_polling(bot)
