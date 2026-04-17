"""Telegram-интеграция на базе aiogram.

Модуль содержит:
- обработчики команд и сообщений;
- интеграцию с RAG (поиск контекста) и LLM (генерация ответа);
- защиту от спама и rate limiting;
- запись уникальных вопросов в БД для аналитики.
"""

from aiogram import Bot
from aiogram import Dispatcher
from aiogram.filters import Command
from app.core.ai_client import AIClient
from app.core.context_manager import ContextManager
from app.core.rag_engine import RAGEngine
from app.core.spam_filter import RateLimiter
from app.core.spam_filter import SpamFilter
from app.database.questions_db import QuestionsDB
from app.config import settings
from loguru import logger

bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
dp = Dispatcher()

# Инициализация компонентов. Для небольшого сервиса допустимо хранить
# их как singletons уровня модуля. При росте проекта лучше перейти на DI.
rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
ai = AIClient()
context_manager = ContextManager(max_context=settings.MAX_CONTEXT_MESSAGES)
rate_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_REQUESTS)
spam_filter = SpamFilter()
db = QuestionsDB()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Стартовое приветствие."""
    welcome_text = (
        "Здравствуйте! Я ваш нейро-консультант Школы Михаила Агеева. 🌟\n\n"
        "Я помогу вам узнать больше о наших программах обучения, "
        "методиках духовного развития и философии школы. "
        "Просто задайте свой вопрос, и я постараюсь ответить максимально подробно на основе знаний школы. "
        "Чем я могу быть полезен?"
    )
    await message.answer(welcome_text)

@dp.message(Command("clear_history"))
async def cmd_clear_history(message: Message):
    """Команда для очистки диалоговой истории пользователя."""
    user_id = f"telegram_{message.from_user.id}"
    await context_manager.clear_context(user_id)
    await message.answer("История нашего диалога очищена. Можем начать общение с чистого листа!")

@dp.message()
async def handle_message(message: Message):
    """Основной обработчик входящих сообщений пользователя."""
    if message.text and message.text.startswith("/"):
        return
    user_id = f"telegram_{message.from_user.id}"
    text = message.text

    if not text:
        return

    # Rate limiting: защищает от перегрузки и случайных циклов.
    if not await rate_limiter.check_limit(user_id):
        await message.answer("Превышен лимит запросов. Попробуйте позже.")
        return
    await rate_limiter.increment(user_id)

    # Спам-фильтр: ранний выход без ответа (чтобы не поощрять спам).
    if await spam_filter.is_spam(user_id, text):
        return

    # Аналитика: сохраняем уникальные вопросы для админки.
    await db.add_question(text, "telegram")

    # RAG + LLM: сначала подбираем контекст, затем генерируем ответ.
    history = await context_manager.get_context(user_id)
    rag_context = await rag.get_context_for_query(text)
    
    response_text = await ai.generate_response(
        user_question=text,
        rag_context=rag_context,
        conversation_history=history,
        system_prompt=settings.SYSTEM_PROMPT
    )

    # Обновляем контекст только после успешной генерации ответа.
    await context_manager.add_message(user_id, "user", text)
    await context_manager.add_message(user_id, "assistant", response_text)

    await message.answer(response_text)

async def start_bot():
    """Запускает Telegram-бота в режиме polling или webhook."""
    if settings.TELEGRAM_USE_WEBHOOK:
        logger.info("Telegram bot starting in Webhook mode")
        # Webhook setup is handled in main.py
    else:
        logger.info("Telegram bot starting in Polling mode")
        await dp.start_polling(bot)
