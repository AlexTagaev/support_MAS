"""
Миграционный скрипт для пересоздания FAISS индексов с OpenAI Embeddings API.

Использование:
    python migrate_embeddings.py
"""
import asyncio
import os
import sys

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.rag_engine import RAGEngine
from app.config import settings
from loguru import logger


async def migrate_embeddings():
    """
    Пересоздание FAISS индексов с использованием OpenAI Embeddings API.
    
    Этот скрипт необходимо запустить после рефакторинга для обновления
    индексов, которые могли быть созданы с использованием sentence-transformers.
    """
    logger.info("=" * 60)
    logger.info("Начинаем миграцию FAISS индексов на OpenAI Embeddings")
    logger.info("=" * 60)
    
    # Проверка наличия базы знаний
    if not os.path.exists(settings.KNOWLEDGE_BASE_PATH):
        logger.error(f"Файл базы знаний не найден: {settings.KNOWLEDGE_BASE_PATH}")
        logger.error("Пожалуйста, создайте файл data/knowledge_base.md перед запуском миграции.")
        return False
    
    # Создание backup существующего индекса (если есть)
    index_file = os.path.join(settings.FAISS_INDEX_PATH, "index.faiss")
    metadata_file = os.path.join(settings.FAISS_INDEX_PATH, "metadata.json")
    
    if os.path.exists(index_file):
        logger.info("Создаем резервную копию существующего индекса...")
        backup_index = index_file + ".backup"
        backup_metadata = metadata_file + ".backup"
        
        import shutil
        shutil.copy2(index_file, backup_index)
        if os.path.exists(metadata_file):
            shutil.copy2(metadata_file, backup_metadata)
        
        logger.info(f"Backup сохранен: {backup_index}")
    
    # Инициализация RAG Engine
    logger.info("Инициализация RAG Engine...")
    rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
    
    # Пересоздание индексов
    logger.info("Начинаем пересоздание индексов с OpenAI Embeddings...")
    logger.info("Это может занять несколько минут в зависимости от размера базы знаний.")
    
    try:
        rag.rebuild_index()
        logger.success("✓ Миграция успешно завершена!")
        logger.info(f"Новый индекс сохранен в: {settings.FAISS_INDEX_PATH}")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка при миграции: {e}")
        logger.error("Для восстановления используйте backup файлы.")
        return False


async def verify_migration():
    """Проверка работоспособности нового индекса."""
    logger.info("\n" + "=" * 60)
    logger.info("Проверка работоспособности нового индекса")
    logger.info("=" * 60)
    
    rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
    
    # Тестовые запросы
    test_queries = [
        "Как записаться на программу?",
        "Расскажи о школе",
        "Контакты школы"
    ]
    
    for query in test_queries:
        logger.info(f"\nТестовый запрос: '{query}'")
        results = await rag.search(query, top_k=3)
        
        if results:
            logger.success(f"✓ Найдено {len(results)} релевантных фрагментов")
            logger.info(f"  Первый результат (первые 100 символов): {results[0]['text'][:100]}...")
        else:
            logger.warning("✗ Результаты не найдены")
    
    logger.info("\n" + "=" * 60)
    logger.success("Проверка завершена!")


async def main():
    """Главная функция миграции."""
    logger.info("")
    logger.info("╔═══════════════════════════════════════════════════════════╗")
    logger.info("║   Миграция FAISS индексов на OpenAI Embeddings API       ║")
    logger.info("║   Школа Михаила Агеева - Нейро-техподдержка v2.0        ║")
    logger.info("╚═══════════════════════════════════════════════════════════╝")
    logger.info("")
    
    # Проверка API ключа
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("sk-..."):
        logger.error("ОШИБКА: Не настроен OPENAI_API_KEY в файле .env")
        logger.error("Пожалуйста, добавьте ваш OpenAI API ключ и повторите попытку.")
        return
    
    # Выполнение миграции
    success = await migrate_embeddings()
    
    if success:
        # Проверка работоспособности
        await verify_migration()
        
        logger.info("\n" + "=" * 60)
        logger.success("🎉 Миграция полностью завершена!")
        logger.info("Теперь вы можете запустить приложение:")
        logger.info("  docker-compose up -d --build")
        logger.info("=" * 60 + "\n")
    else:
        logger.error("\n" + "=" * 60)
        logger.error("❌ Миграция не удалась. Проверьте логи выше.")
        logger.error("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
