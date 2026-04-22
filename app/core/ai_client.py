"""Клиент для генерации ответов через OpenAI-совместимый Chat API."""

from typing import Dict
from typing import List

from loguru import logger
from openai import AsyncOpenAI

from app.config import settings


class AIClient:
    """Обертка над Chat Completions API для генерации ответов бота."""

    def __init__(self):
        return

    @staticmethod
    def _build_client() -> AsyncOpenAI:
        """Создает клиента по текущему провайдеру из настроек."""
        provider = settings.LLM_PROVIDER
        if provider == "proxiapi":
            return AsyncOpenAI(
                api_key=settings.PROXIAPI_API_KEY,
                base_url=settings.PROXIAPI_API_BASE,
            )
        return AsyncOpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
        )

    async def generate_response(
        self,
        user_question: str,
        rag_context: str,
        conversation_history: List[Dict],
        system_prompt: str,
    ) -> str:
        """Генерирует ответ модели по вопросу и RAG-контексту."""
        try:
            client = self._build_client()

            # Backward-compatible: if placeholders are absent or broken, keep original prompt.
            try:
                rendered_system_prompt = system_prompt.format(
                    rag_context=rag_context,
                    conversation_history="",
                    user_question="",
                )
            except Exception:
                rendered_system_prompt = system_prompt

            messages = [{"role": "system", "content": rendered_system_prompt}]

            # Always inject retrieval context explicitly.
            context_block = rag_context.strip() if rag_context and rag_context.strip() else "Контекст не найден."
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "Контекст для ответа (используй только его факты; "
                        "если данных недостаточно, честно скажи об этом):\n\n"
                        f"{context_block}"
                    ),
                }
            )

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
                presence_penalty=0.3,
            )

            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"AI generation error: {e}")
            return (
                "Извините, произошла ошибка при генерации ответа. "
                "Пожалуйста, попробуйте позже или обратитесь в хелп-чат: "
                "https://t.me/Ageev_Help_chat"
            )
