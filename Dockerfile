# Multi-stage build для минимизации размера образа
FROM python:3.11-slim-bullseye as builder

# Установка только необходимых build-зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Создание wheels для ускорения установки
WORKDIR /tmp
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /wheels -r requirements.txt

# Финальный образ
FROM python:3.11-slim-bullseye

# Метаданные
LABEL maintainer="Школа Михаила Агеева"
LABEL version="2.0.0-refactored"
LABEL description="Нейро-техподдержка с оптимизированным размером образа"

# Установка только runtime зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копирование и установка wheels из builder
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels \
    && find /usr/local -type d -name __pycache__ -exec rm -r {} + || true \
    && find /usr/local -type f -name "*.pyc" -delete \
    && find /usr/local -type f -name "*.pyo" -delete \
    && rm -rf /usr/local/lib/python3.11/site-packages/*/tests \
    && rm -rf /usr/local/lib/python3.11/site-packages/*/test \
    && rm -rf /usr/local/share/doc \
    && rm -rf /usr/local/share/man

# Копирование приложения
COPY ./app /app/app
COPY ./data /app/data

# Создание необходимых директорий
RUN mkdir -p /app/logs /app/data/faiss_index

# Переменные окружения
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
