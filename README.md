# Neuro-Support for Mikhail Ageev School

Back-end система автоматической техподдержки на базе GPT-4.1-mini.

## Установка и запуск

1. Клонируйте репозиторий.
2. Создайте `.env` файл на основе `.env.example` и заполните API ключи.
3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```
4. Запустите приложение:
   ```bash
   uvicorn app.main:app --reload
   ```

## Админ-панель
Доступна по адресу: `http://localhost:8000/admin`
Логин/пароль настраиваются в `.env`.

## Структура проекта
- `app/core`: Ядро системы (RAG, AI, Context).
- `app/integrations`: Telegram и Jivo.
- `app/admin`: Веб-интерфейс администратора.
- `data/`: База знаний и индексы.
