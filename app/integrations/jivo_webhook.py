import httpx
from fastapi import APIRouter, Request
from app.config import settings
from app.core.rag_engine import RAGEngine
from app.core.ai_client import AIClient
from app.core.context_manager import ContextManager
from app.core.spam_filter import RateLimiter, SpamFilter
from app.database.questions_db import QuestionsDB
from loguru import logger

router = APIRouter()

# Инициализация (в идеале через DI)
rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
ai = AIClient()
context_manager = ContextManager(max_context=settings.MAX_CONTEXT_MESSAGES)
rate_limiter = RateLimiter(max_requests=settings.RATE_LIMIT_REQUESTS)
spam_filter = SpamFilter()
db = QuestionsDB()

@router.post("/api/jivo/webhook")
async def jivo_webhook(request: Request):
    payload = await request.json()
    event_name = payload.get("event_name")
    
    if event_name != "chat.message":
        return {"status": "ok"}

    message_data = payload.get("message", {})
    client_id = f"jivo_{message_data.get('client_id')}"
    text = message_data.get("text")

    if not text:
        return {"status": "ok"}

    # Логика аналогична Telegram
    if not await rate_limiter.check_limit(client_id):
        await send_jivo_message(message_data.get('client_id'), "Превышен лимит запросов.")
        return {"status": "ok"}
    await rate_limiter.increment(client_id)

    if await spam_filter.is_spam(client_id, text):
        return {"status": "ok"}

    await db.add_question(text, "jivo")

    history = await context_manager.get_context(client_id)
    rag_context = await rag.get_context_for_query(text)
    
    response_text = await ai.generate_response(
        user_question=text,
        rag_context=rag_context,
        conversation_history=history,
        system_prompt=settings.SYSTEM_PROMPT
    )

    await context_manager.add_message(client_id, "user", text)
    await context_manager.add_message(client_id, "assistant", response_text)

    await send_jivo_message(message_data.get('client_id'), response_text)
    
    return {"status": "ok"}

async def send_jivo_message(client_id: str, text: str):
    url = "https://api.jivo.ru/bot/v1/message"
    headers = {
        "Authorization": f"Bearer {settings.JIVO_BOT_TOKEN}",
        "Content-Type": "application/json"
    }
    body = {
        "client_id": client_id,
        "message": {
            "type": "text",
            "text": text
        }
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(url, headers=headers, json=body)
        except Exception as e:
            logger.error(f"Error sending message to Jivo: {e}")
