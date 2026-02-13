FROM python:3.11-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Копирование зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY ./app ./app
COPY ./data ./data

# Создание директорий
RUN mkdir -p /app/logs /app/data/faiss_index

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Запуск приложения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
