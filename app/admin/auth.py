"""Аутентификация в админ-панели через HTTP Basic.

Важно:
- Это минимальная реализация для внутреннего использования.
- В `ADMIN_PASSWORD_HASH` сейчас ожидается пароль (не хеш).
  При выносе в прод стоит заменить на проверку хеша (bcrypt/argon2).
"""

import secrets

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import HTTPBasic
from fastapi.security import HTTPBasicCredentials

from loguru import logger

from app.config import settings

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверяет доступ администратора по HTTP Basic.

    Возвращает имя пользователя при успешной проверке.
    """
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = settings.ADMIN_USERNAME.encode("utf8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    
    # В реальном проекте здесь должна быть проверка хеша пароля
    # Для упрощения сравниваем напрямую (в .env должен быть пароль, а не хеш для этой реализации)
    current_password_bytes = credentials.password.encode("utf8")
    # Предполагаем, что в ADMIN_PASSWORD_HASH хранится сам пароль для простоты примера
    correct_password_bytes = settings.ADMIN_PASSWORD_HASH.encode("utf8")
    is_correct_password = secrets.compare_digest(
        current_password_bytes, correct_password_bytes
    )

    if not (is_correct_username and is_correct_password):
        # Логи пишем без чувствительных данных.
        logger.warning("Admin auth failed for username='{}'", credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
