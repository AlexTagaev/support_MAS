import time
from typing import Dict, List
from app.config import settings

class RateLimiter:
    def __init__(self, max_requests: int = 20, window: int = 3600):
        self.max_requests = max_requests
        self.window = window
        self.requests = {}  # {user_id: [timestamp1, timestamp2, ...]}

    async def check_limit(self, user_id: str) -> bool:
        """Проверка лимита запросов."""
        now = time.time()
        if user_id not in self.requests:
            return True
        
        # Очистка старых запросов
        self.requests[user_id] = [
            ts for ts in self.requests[user_id]
            if now - ts < self.window
        ]
        
        return len(self.requests[user_id]) < self.max_requests

    async def increment(self, user_id: str):
        """Регистрация запроса."""
        now = time.time()
        if user_id not in self.requests:
            self.requests[user_id] = []
        self.requests[user_id].append(now)

class SpamFilter:
    def __init__(self):
        self.last_messages = {}  # {user_id: [msg1, msg2, msg3]}
        self.blacklist = set()

    async def is_spam(self, user_id: str, message: str) -> bool:
        """Проверка сообщения на спам."""
        if user_id in self.blacklist:
            return True
            
        # Слишком короткое или длинное
        if len(message) < 3 or len(message) > 2000:
            return True
            
        # Повторяющиеся сообщения
        if user_id not in self.last_messages:
            self.last_messages[user_id] = []
        
        self.last_messages[user_id].append(message)
        if len(self.last_messages[user_id]) > 3:
            self.last_messages[user_id].pop(0)
            
        if len(self.last_messages[user_id]) == 3 and len(set(self.last_messages[user_id])) == 1:
            return True
            
        return False

    async def add_to_blacklist(self, user_id: str):
        """Блокировка пользователя."""
        self.blacklist.add(user_id)
