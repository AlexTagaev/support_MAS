import sys
from loguru import logger
from app.config import settings

def setup_logger():
    # Удаляем стандартный обработчик
    logger.remove()
    
    # Добавляем вывод в консоль
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.LOG_LEVEL
    )
    
    # Добавляем запись в JSON лог
    logger.add(
        "logs/app.log",
        format="{time} | {level} | {message}",
        rotation="100 MB",
        retention="30 days",
        compression="zip",
        serialize=True,
        level=settings.LOG_LEVEL
    )
