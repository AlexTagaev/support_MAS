from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.config import settings
import secrets

security = HTTPBasic()

def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    print(f"DEBUG: Input username: {credentials.username}, Expected: {settings.ADMIN_USERNAME}")
    print(f"DEBUG: Input password: {credentials.password}, Expected: {settings.ADMIN_PASSWORD_HASH}")
    
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
    
    print(f"DEBUG: Username match: {is_correct_username}, Password match: {is_correct_password}")
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
