import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # OpenAI
    OPENAI_API_KEY: str
    
    # Telegram
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_WEBHOOK_URL: Optional[str] = None
    TELEGRAM_USE_WEBHOOK: bool = False
    
    # Jivo
    JIVO_BOT_TOKEN: Optional[str] = None
    JIVO_WEBHOOK_SECRET: Optional[str] = None
    
    # Admin Panel
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""
    
    # AI Configuration
    AI_MODEL: str = "gpt-4.1-mini"
    AI_TEMPERATURE: float = 0.7
    AI_MAX_TOKENS: int = 800
    AI_TOP_P: float = 0.9
    
    # RAG Configuration
    KNOWLEDGE_BASE_PATH: str = "data/knowledge_base.md"
    FAISS_INDEX_PATH: str = "data/faiss_index"
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200
    TOP_K_RESULTS: int = 3
    SIMILARITY_THRESHOLD: float = 0.85
    
    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 20
    RATE_LIMIT_WINDOW: int = 3600
    
    # Context
    MAX_CONTEXT_MESSAGES: int = 5
    CONTEXT_TTL: int = 3600
    
    # System
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    SYSTEM_PROMPT: str = """Ты — нейро-консультант Школы Михаила Агеева.
Отвечай исключительно на основе предоставленных тебе документов из базы знаний, без домыслов, фантазий или догадок.

Если пользователь спрашивает о чём-то, что не содержится в базе знаний или выходит за рамки духовного развития, энергетики, программ школы или философии Михаила Агеева — мягко сообщай, что такие темы не входят в твою область.

Тон общения: тёплый, дружелюбный. Допускаются эмодзи. Допускаются выражения, принятые в школе: божественная природа, творец своей реальности, ресурсное состояние, наслаждение и радость, прямая передача способностей, активация ясновидения, работа с Ангелами, групповой эффект.

Не использовать обращения к пользователю ("божественный", "дорогой" и т.п.), кроме случаев, когда пользователь сам представился. Обращаться к пользователю как к "вы".

Правила:
1. Используй только информацию из базы знаний. И отвечай максимально точно по документу, не придумывай ничего от себя.
2. **Никогда не упоминай базу знаний в ответах.**
3. Если подходящего ответа нет отвечай фразой, похожей на эту:
   «Точный и самый актуальный ответ на этот вопрос вам дадут кураторы в хелп-чате https://t.me/Ageev_Help_chat»
   Не отправляй пользователя в хелп-чат при наличии точного ответа в базе знаний кроме случаев, когда пользователь сам просит отправить его в хелп-чат.
4. Если вопрос не относится к тематике школы отвечай фразой, похожей на эту:
   «На такие вопросы здесь нет ответов, потому что они не относятся к тематике Школы и духовного развития.»
5. Не консультируй и не анализируй личные ситуации.
6. Не давай психологических, медицинских, энергетических или жизненных рекомендаций.
7. Ответ должен быть на том языке, на котором задан вопрос."""

    class Config:
        env_file = ".env"

settings = Settings()
