# Multi-stage build для минимизации размера образа
FROM python:3.11-slim-bookworm AS builder

# Создание wheels для ускорения установки
WORKDIR /tmp
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

# Финальный образ
FROM python:3.11-slim-bookworm

# Метаданные
LABEL maintainer="Школа Михаила Агеева"
LABEL version="2.0.0-refactored"
LABEL description="Нейро-техподдержка с оптимизированным размером образа"

WORKDIR /app

# Копирование и установка wheels из builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* && rm -rf /wheels

# Keep cleanup separate from dependency installation so cleanup cannot hide a
# failed pip install through shell error handling.
RUN find /usr/local -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find /usr/local -type f \( -name "*.pyc" -o -name "*.pyo" \) -delete \
    && find /usr/local/lib/python3.11/site-packages -type d \( -name tests -o -name test \) -prune -exec rm -rf {} + \
    && rm -rf /usr/local/share/doc /usr/local/share/man

# Копирование приложения
COPY ./app /app/app
COPY ./data /app/data
COPY ./migrate_embeddings.py /app/migrate_embeddings.py

# Создание необходимых директорий
RUN mkdir -p /app/logs /app/data/faiss_index

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"]

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
