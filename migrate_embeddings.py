"""Rebuild and verify the FAISS index through the configured AI provider."""
import asyncio
import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.core.provider_clients import close_async_clients
from app.core.provider_clients import provider_credentials
from app.core.rag_engine import RAGEngine
from loguru import logger


async def migrate_embeddings():
    """
    Пересоздание FAISS индексов через выбранный OpenAI-совместимый провайдер.
    
    Этот скрипт необходимо запустить после рефакторинга для обновления
    индексов, которые могли быть созданы с использованием sentence-transformers.
    """
    logger.info("=" * 60)
    logger.info("Начинаем перестроение FAISS индекса через выбранного AI-провайдера")
    logger.info("=" * 60)
    
    # Проверка наличия базы знаний
    if not os.path.exists(settings.KNOWLEDGE_BASE_PATH):
        logger.error(f"Файл базы знаний не найден: {settings.KNOWLEDGE_BASE_PATH}")
        logger.error("Пожалуйста, создайте файл data/knowledge_base.md перед запуском миграции.")
        return False
    
    # Save a recovery pointer for generation-based indices. Old generations
    # remain immutable; legacy root-level index files get conventional copies.
    index_dir = Path(settings.FAISS_INDEX_PATH)
    current_pointer = index_dir / "CURRENT"
    if current_pointer.is_file():
        generation = current_pointer.read_text(encoding="ascii").strip()
        if not generation or Path(generation).name != generation:
            logger.error("Некорректный указатель текущего поколения FAISS")
            return False
        generation_dir = index_dir / "generations" / generation
        if not (generation_dir / "index.faiss").is_file() or not (generation_dir / "metadata.json").is_file():
            logger.error("Текущее поколение FAISS неполное; резервная копия не создана")
            return False
        backup_tmp = index_dir / ".CURRENT.backup.tmp"
        backup_tmp.write_text(generation, encoding="ascii")
        os.replace(backup_tmp, index_dir / "CURRENT.backup")
        logger.info("Сохранён указатель резервной копии поколения: {}", generation)
    else:
        index_file = index_dir / "index.faiss"
        metadata_file = index_dir / "metadata.json"
        if index_file.is_file():
            import shutil

            logger.info("Создаем резервную копию legacy-индекса...")
            shutil.copy2(index_file, str(index_file) + ".backup")
            if metadata_file.is_file():
                shutil.copy2(metadata_file, str(metadata_file) + ".backup")
    
    # Инициализация RAG Engine
    logger.info("Инициализация RAG Engine...")
    rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
    
    # Пересоздание индексов
    logger.info("Начинаем пересоздание FAISS индекса...")
    logger.info("Это может занять несколько минут в зависимости от размера базы знаний.")
    
    try:
        await rag.rebuild_index()
        logger.success("✓ Миграция успешно завершена!")
        logger.info(f"Новый индекс сохранен в: {settings.FAISS_INDEX_PATH}")
        return True
    except Exception as e:
        logger.error(f"✗ Ошибка при миграции: {e}")
        logger.error("Для восстановления используйте backup файлы.")
        return False


async def verify_migration() -> bool:
    """Validate the published index without sending sample queries to the API."""
    logger.info("\n" + "=" * 60)
    logger.info("Проверка работоспособности нового индекса")
    logger.info("=" * 60)
    
    rag = RAGEngine(settings.KNOWLEDGE_BASE_PATH, settings.FAISS_INDEX_PATH)
    
    if rag.index is None or rag.index.ntotal != len(rag.metadata):
        logger.error("Загруженный FAISS-индекс не прошел проверку целостности")
        return False
    
    logger.info("\n" + "=" * 60)
    logger.success("Индекс загружен; векторов: {}", rag.index.ntotal)
    logger.info("Проверка целостности завершена без дополнительных API-запросов.")
    return True


async def main() -> bool:
    """Главная функция миграции."""
    logger.info("")
    logger.info("╔═══════════════════════════════════════════════════════════╗")
    logger.info("║   Перестроение FAISS индекса для выбранного провайдера   ║")
    logger.info("║   Школа Михаила Агеева - Нейро-техподдержка v2.0        ║")
    logger.info("╚═══════════════════════════════════════════════════════════╝")
    logger.info("")
    
    api_key, _ = provider_credentials()
    if not api_key:
        logger.error("Не настроен ключ для выбранного AI-провайдера ({})", settings.LLM_PROVIDER)
        return False

    try:
        success = await migrate_embeddings()
        if success:
            success = await verify_migration()
        if success:
            logger.info("\n" + "=" * 60)
            logger.success("🎉 Пересоздание и проверка индекса завершены!")
            logger.info("Теперь можно запускать приложение: docker compose up -d")
            logger.info("=" * 60 + "\n")
        else:
            logger.error("Пересоздание индекса не удалось; проверьте логи выше.")
        return success
    finally:
        await close_async_clients()


if __name__ == "__main__":
    if not asyncio.run(main()):
        sys.exit(1)
