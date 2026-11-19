"""HTTP Basic authentication for the admin panel."""

import secrets

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi.security import HTTPBasic
from fastapi.security import HTTPBasicCredentials

from loguru import logger
from passlib.context import CryptContext

from app.config import settings

security = HTTPBasic()
password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Проверяет доступ администратора по HTTP Basic.

    Возвращает имя пользователя при успешной проверке.
    """
    current_username_bytes = credentials.username.encode("utf8")
    correct_username_bytes = settings.ADMIN_USERNAME.encode("utf8")
    is_correct_username = secrets.compare_digest(
        current_username_bytes, correct_username_bytes
    )
    
    stored_hash = settings.ADMIN_PASSWORD_HASH
    is_correct_password = False
    if stored_hash.startswith(("$2a$", "$2b$", "$2y$")):
        try:
            is_correct_password = password_context.verify(credentials.password, stored_hash)
        except (ValueError, TypeError):
            is_correct_password = False

    if not (is_correct_username and is_correct_password):
        # Логи пишем без чувствительных данных.
        logger.warning("Admin authentication failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
