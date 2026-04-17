"""Настройка логирования для приложения.

Модуль централизует конфигурацию Loguru:
- консольный вывод для разработки;
- запись в файл `logs/app.log` в JSON-формате для последующего анализа.
"""

import sys
from loguru import logger
from app.config import settings

def setup_logger():
    """Инициализирует Loguru и удаляет стандартные обработчики.

    Консоль:
    - удобочитаемый формат с цветами (по умолчанию Loguru).

    Файл:
    - ротация по размеру (`rotation="100 MB"`);
    - хранение истории (`retention="30 days"`);
    - сжатие архивов и сериализация в JSON (`serialize=True`).
    """
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
