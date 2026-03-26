from typing import List, Dict, Optional

from openai import AsyncOpenAI
from loguru import logger

from app.config import settings

class AIClient:
    def __init__(self):
        pass

    @staticmethod
    def _build_client() -> AsyncOpenAI:
        """Создает клиента по текущему провайдеру из настроек."""
        provider = settings.LLM_PROVIDER
        if provider == "proxiapi":
            return AsyncOpenAI(
                api_key=settings.PROXIAPI_API_KEY,
                base_url=settings.PROXIAPI_API_BASE
            )
        return AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE
        )

    async def generate_response(
        self,
        user_question: str,
        rag_context: str,
        conversation_history: List[Dict],
        system_prompt: str
    ) -> str:
        """Генерация ответа через GPT-4.1-mini."""
        try:
            client = self._build_client()
            messages = [
                {"role": "system", "content": system_prompt.format(rag_context=rag_context, conversation_history="", user_question="")}
            ]
            
            # Добавляем историю (последние 5 сообщений)
            for msg in conversation_history:
                messages.append(msg)
                
            messages.append({"role": "user", "content": user_question})

            response = await client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=messages,
                temperature=settings.AI_TEMPERATURE,
                max_tokens=settings.AI_MAX_TOKENS,
                top_p=settings.AI_TOP_P,
                frequency_penalty=0.3,
                presence_penalty=0.3
            )
            
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI generation error: {e}")
            return "Извините, произошла ошибка при генерации ответа. Пожалуйста, попробуйте позже или обратитесь в хелп-чат: https://t.me/Ageev_Help_chat"
