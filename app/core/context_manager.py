import time
from collections import deque
from typing import List, Dict
from app.config import settings

class ContextManager:
    def __init__(self, max_context: int = 5, ttl: int = 3600):
        self.max_context = max_context
        self.ttl = ttl
        self.contexts = {}  # {user_id: deque([msg1, msg2, ...])}
        self.timestamps = {}  # {user_id: last_activity_time}

    async def add_message(self, user_id: str, role: str, content: str):
        """Добавление сообщения в контекст."""
        if user_id not in self.contexts:
            self.contexts[user_id] = deque(maxlen=self.max_context)
        
        self.contexts[user_id].append({"role": role, "content": content})
        self.timestamps[user_id] = time.time()

    async def get_context(self, user_id: str) -> List[Dict]:
        """Получение истории для пользователя."""
        await self.cleanup_expired()
        if user_id in self.contexts:
            return list(self.contexts[user_id])
        return []

    async def clear_context(self, user_id: str):
        """Очистка контекста."""
        if user_id in self.contexts:
            del self.contexts[user_id]
        if user_id in self.timestamps:
            del self.timestamps[user_id]

    async def cleanup_expired(self):
        """Удаление устаревших контекстов (TTL)."""
        now = time.time()
        expired_users = [
            user_id for user_id, last_ts in self.timestamps.items()
            if now - last_ts > self.ttl
        ]
        for user_id in expired_users:
            await self.clear_context(user_id)
