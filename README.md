# Нейро-техподдержка сайта Школы Михаила Агеева

![Version](https://img.shields.io/badge/version-2.0.0--refactored-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![Docker](https://img.shields.io/badge/docker-optimized-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

Интеллектуальная система автоматической технической поддержки на базе **GPT-4.1-mini** с использованием технологии **RAG (Retrieval-Augmented Generation)** для консультирования учеников и посетителей Школы Михаила Агеева.

## 🌟 Основные возможности

- **🤖 Умные ответы**: Генерация ответов на основе векторной базы знаний (Markdown + FAISS).
- **💬 Канал пилота**: Telegram Bot. В админке можно заранее сохранить настройки Jivo, но обработка его вебхуков ещё не подключена.
- **🧠 Память диалога**: Контекст последних двух пар сообщений хранится в памяти до одного часа.
- **📊 Аналитика**: Автоматическое выявление и сохранение уникальных вопросов пользователей с векторным сравнением.
- **⚙️ Админ-панель**: Веб-интерфейс для управления базой знаний, просмотра статистики и тестирования бота.
- **🛡️ Безопасность**: Rate Limiting (20 запросов на пользователя в чате за час), защита от спама и Basic Auth для админки.

---

## Статус пилотной конфигурации

- Telegram работает через long polling; webhook-режим при запуске отклоняется.
- В стандартной конфигурации админка доступна через localhost на сервере; используйте SSH-туннель. Опциональный профиль Nginx открывает HTTP-порт 80 без TLS и не подходит для публичной эксплуатации до настройки HTTPS.
- Jivo выключен по умолчанию. Админка сохраняет его настройки, но endpoint вебхука пока отвечает HTTP 503.
- Контейнер ограничен одним CPU и 1200 MB памяти. Фактическое потребление зависит от размера индекса, запросов и используемого AI-провайдера; измерения нагрузки ещё не проводились.
- Ответы и embeddings требуют сети и действующего ключа выбранного провайдера.

---

## 📋 Требования

### Требования для пилотного сервера
- **CPU**: 1 vCPU
- **RAM**: 2 GB; контейнер ограничен 1200 MB, чтобы оставить память ОС
- **Диск**: от 10 GB свободного места; рабочие данные находятся в `data/` и `logs/`
- **ОС**: Ubuntu Server 24.04 LTS без графического интерфейса
- **Управление**: SSH; админка по SSH-туннелю
- **Docker Engine** и Compose plugin (`docker compose`)

### Ключи
- Ключ выбранного AI-провайдера: OpenAI или ProxiAPI
- **Telegram Bot Token**: получить у @BotFather
- Jivo по умолчанию выключен. Настройки Jivo в админке не включают обработку вебхуков.

---

## 🚀 Быстрый старт

### 1. Клонирование репозитория на Ubuntu Server
```bash
git clone <repository-url>
cd support_MAS
```

### 2. Настройка окружения
Создайте файл `.env` на основе шаблона:
```bash
cp .env.example .env
```

Отредактируйте `.env` и заполните обязательные поля:
```env
# AI provider
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_API_BASE=
# Если используете ProxiAPI, выберите LLM_PROVIDER=proxiapi,
# оставьте OPENAI_API_KEY пустым и заполните PROXIAPI_API_KEY.
PROXIAPI_API_KEY=
PROXIAPI_API_BASE=https://api.proxyapi.ru/openai/v1

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_USE_WEBHOOK=false

# Admin Panel
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=replace_with_bcrypt_hash
```

Оставьте `TELEGRAM_USE_WEBHOOK=false`: в пилоте используется polling. Перед первым запуском соберите образ и создайте bcrypt-хеш пароля админки:
```bash
docker compose build app
docker compose run --rm --no-deps app python -c 'from getpass import getpass; from passlib.context import CryptContext; print(CryptContext(schemes=["bcrypt"]).hash(getpass("Пароль админки: ")))'
```
Скопируйте выведенный хеш в `ADMIN_PASSWORD_HASH` в `.env`, затем создайте каталоги и ограничьте доступ к секретам:
```bash
mkdir -p data/faiss_index logs
chmod 700 data logs
chmod 600 .env
```

### 3. Запуск через Docker (рекомендуется)
```bash
docker compose up -d
```

**Ожидаемое время:** 3-5 минут для первой сборки.

### 4. Инициализация базы знаний
После запуска необходимо векторизовать базу знаний:

**Вариант A (через админку):**
1. С компьютера администратора создайте SSH-туннель:
   ```bash
   ssh -L 8000:127.0.0.1:8000 <user>@<server-ip>
   ```
2. Откройте админку: http://localhost:8000/admin
3. Перейдите в раздел **База знаний**
4. Нажмите кнопку **"Пересоздать индексы"**
5. Дождитесь уведомления об успешном завершении

**Вариант B (через миграционный скрипт):**
```bash
# Запустите до приложения (или после его остановки)
docker compose run --rm --no-deps app python migrate_embeddings.py
```
Скрипт работает отдельным процессом. Если приложение уже запущено, используйте пересборку из админки, чтобы обновить индекс и в его памяти.

Compose публикует порт приложения только на `127.0.0.1`; он недоступен напрямую извне VPS. Каталог `data/` сохраняет SQLite, FAISS, интеграционные настройки и базу знаний; `logs/` сохраняет файловые логи. Docker-журнал ограничен по размеру.

Перед обновлением и редактированием базы знаний сделайте резервную копию:
```bash
docker compose down
tar -czf support-data-$(date +%F-%H%M).tar.gz data logs .env
docker compose up -d
```
Архив содержит секреты из `.env` и настроек интеграций; храните его с ограниченным доступом и не добавляйте в Git.

### 5. Проверка работоспособности
```bash
curl http://localhost:8000/health
```

Ожидаемый ответ:
```json
{
  "status": "healthy",
  "checks": { "database": "ok", "faiss_index": "ok", "telegram_polling": "ok" }
}
```
До создания FAISS-индекса проверка готовности вернёт HTTP 503; после успешной пересборки она должна стать healthy.

---

## ⚙️ Конфигурация

### Переменные окружения

| Переменная | Описание | По умолчанию | Обязательна |
|------------|----------|--------------|-------------|
| `LLM_PROVIDER` | Провайдер LLM (`openai`/`proxiapi`) | `openai` | ✅ |
| `OPENAI_API_KEY` | API ключ OpenAI, если выбран провайдер `openai` | - | Только для OpenAI |
| `OPENAI_API_BASE` | Base URL OpenAI (обычно пусто) | - | ❌ |
| `PROXIAPI_API_KEY` | API ключ ProxiAPI | - | Только для ProxiAPI |
| `PROXIAPI_API_BASE` | Base URL ProxiAPI | `https://api.proxyapi.ru/openai/v1` | ❌ |
| `TELEGRAM_BOT_TOKEN` | Токен Telegram бота | - | ✅ |
| `TELEGRAM_WEBHOOK_URL` | URL для webhook (если используется) | - | ❌ |
| `TELEGRAM_USE_WEBHOOK` | Использовать webhook вместо polling | `false` | ❌ |
| `JIVO_BOT_TOKEN` | Токен Jivo бота | - | ❌ |
| `JIVO_WEBHOOK_SECRET` | Секрет для Jivo webhook | - | ❌ |
| `ADMIN_USERNAME` | Логин для админки | `admin` | ✅ |
| `ADMIN_PASSWORD_HASH` | Bcrypt-хеш пароля админки | - | ✅ |
| `AI_MODEL` | Общая модель для OpenAI/ProxiAPI | `gpt-4.1-mini` | ❌ |
| `AI_TEMPERATURE` | Температура генерации | `0.7` | ❌ |
| `AI_MAX_TOKENS` | Максимум токенов в ответе | `800` | ❌ |
| `CHUNK_SIZE` | Размер чанка для RAG | `1000` | ❌ |
| `TOP_K_RESULTS` | Количество релевантных фрагментов | `3` | ❌ |
| `SIMILARITY_THRESHOLD` | Порог схожести вопросов (0-1) | `0.85` | ❌ |
| `RATE_LIMIT_REQUESTS` | Лимит запросов на пару чат/пользователь за окно | `20` | ❌ |
| `RATE_LIMIT_WINDOW` | Временное окно (секунды) | `3600` | ❌ |
| `MAX_CONTEXT_MESSAGES` | Размер истории диалога | `5` | ❌ |
| `LOG_LEVEL` | Уровень логирования | `INFO` | ❌ |

---

## 📖 Использование

### Telegram Bot

1. **Запуск диалога**: Найдите вашего бота в Telegram и отправьте `/start`.
2. **Вопросы**: Просто пишите свои вопросы — бот ответит на основе базы знаний.
3. **Очистка истории**: Команда `/clear_history` сбрасывает контекст диалога.
4. **Команды в меню**: При запуске бот автоматически регистрирует `/start` и `/clear_history` и сбрасывает webhook в polling-режиме.

### Админ-панель

Доступ: http://localhost:8000/admin (или ваш домен)

#### Разделы:

**1. Аналитика** (`/admin/`)
- Просмотр списка уникальных вопросов пользователей
- Метаданные: источник (Telegram/Jivo), дата, количество повторений
- Помогает выявлять пробелы в базе знаний

**2. База знаний** (`/admin/knowledge`)
- Редактирование файла `knowledge_base.md` через веб-интерфейс
- Кнопка **"Сохранить"** — сохраняет изменения
- Кнопка **"Пересоздать индексы"** — обновляет FAISS индексы (обязательно после правок!)

**3. Тестирование** (`/admin/test`)
- Проверка ответов бота без отправки в Telegram
- Показывает найденные фрагменты из базы знаний
- Полезно для отладки некорректных ответов

**4. Настройки AI** (`/admin/settings`)
- Выбор провайдера (`openai` или `proxiapi`)
- Редактирование ключей и base URL для обоих провайдеров
- Изменение `AI_MODEL` (одна модель для обоих провайдеров)
- Сохранение настроек одновременно в `.env` и runtime-конфиг

---

## 🏗 Архитектура

### Структура проекта

```
support_MAS/
├── app/
│   ├── admin/              # Веб-интерфейс администратора
│   │   ├── templates/      # HTML шаблоны (Jinja2)
│   │   ├── auth.py         # HTTP Basic Auth
│   │   └── routes.py       # API endpoints админки
│   ├── core/               # Ядро системы
│   │   ├── rag_engine.py   # RAG логика + FAISS
│   │   ├── ai_client.py    # OpenAI GPT-4.1-mini клиент
│   │   ├── context_manager.py  # Управление контекстом диалогов
│   │   └── spam_filter.py  # Rate Limiter + Spam Filter
│   ├── database/           # Работа с БД
│   │   ├── models.py       # SQLAlchemy модели
│   │   └── questions_db.py # Уникальные вопросы
│   ├── integrations/       # Внешние интеграции
│   │   ├── telegram_bot.py # Telegram bot (aiogram)
│   │   └── jivo_webhook.py # Заготовка вебхука Jivo (503 до реализации)
│   ├── utils/              # Вспомогательные утилиты
│   │   └── logger.py       # Настройка логирования
│   ├── config.py           # Конфигурация (Pydantic Settings)
│   └── main.py             # Точка входа FastAPI
├── data/
│   ├── knowledge_base.md   # База знаний (редактируется)
│   ├── faiss_index/        # Векторные индексы FAISS
│   └── database.db         # SQLite база
├── logs/                   # Логи приложения
├── tests/                  # Тесты (pytest)
├── migrate_embeddings.py   # Миграционный скрипт
├── Dockerfile              # Multi-stage Docker build
├── docker-compose.yml      # Оркестрация контейнеров
├── requirements.txt        # Python зависимости (продакшн)
├── requirements-dev.txt    # Python зависимости (разработка)
└── .dockerignore           # Исключения для Docker образа
```

### Технологический стек

**Backend:**
- Python 3.11
- FastAPI (асинхронный REST API)
- Uvicorn (ASGI сервер)

**AI & ML:**
- OpenAI SDK (GPT-4.1-mini, text-embedding-3-small)
- FAISS (векторный поиск)
- NumPy (работа с массивами)

**Интеграции:**
- Aiogram 3.x (Telegram Bot API)
- HTTPX connection pooling через OpenAI SDK

**База данных:**
- SQLite + SQLAlchemy (Async)
- Aiosqlite (асинхронный драйвер)

**Frontend (админка):**
- Jinja2 (шаблонизатор)
- Bootstrap 5 (CSS фреймворк)
- Vanilla JavaScript

**Инфраструктура:**
- Docker + Docker Compose
- Nginx (reverse proxy)

### Поток данных

```
┌─────────────────────────────────────────────────────────────┐
│                    Канал пилота                             │
│                 ┌──────────────┐                             │
│                 │ Telegram Bot │                             │
│                 └──────┬───────┘                             │
└────────────────────────┼────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  FastAPI Backend                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              Message Handler                           │  │
│  │  • Rate Limiting (20 req/chat-user/hour)              │  │
│  │  • Spam Filter                                        │  │
│  │  • Context Manager (2 exchanges, TTL 1h)             │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │                                           │
│                  ▼                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │              RAG Engine                                │  │
│  │  • FAISS Vector Search (IndexFlatL2)                  │  │
│  │  • Embeddings (text-embedding-3-small)                │  │
│  │  • Top-K Relevance Scoring                           │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │                                           │
│                  ▼                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │           GPT-4.1-mini Integration                     │  │
│  │  • System Prompt Injection                            │  │
│  │  • Context + RAG Results                              │  │
│  │  • Response Generation                                │  │
│  └───────────────┬───────────────────────────────────────┘  │
│                  │                                           │
│                  ▼                                           │
│  ┌───────────────────────────────────────────────────────┐  │
│  │         Analytics & Storage                            │  │
│  │  • Unique Questions DB (Cosine Similarity ≥ 0.85)   │  │
│  │  • Metadata Storage (SQLite)                          │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 Разработка

### Локальная разработка (без Docker)

1. **Установка зависимостей:**
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt
```

2. **Запуск приложения:**
```bash
uvicorn app.main:app --reload --port 8000
```

3. **Запуск тестов:**
```bash
pytest tests/ -v --cov=app
```

4. **Проверка качества кода:**
```bash
# Поиск неиспользуемых импортов
autoflake --check --recursive app/

# Поиск мертвого кода
vulture app/ --min-confidence 80

# Форматирование
black app/

# Линтер
flake8 app/
```

---

## 📊 Мониторинг

### Health Check
```bash
curl http://localhost:8000/health
```

Проверка показывает локальную готовность приложения: база, FAISS-индекс и задача Telegram polling. Внешний AI API не вызывается из healthcheck.

Ответ:
```json
{
  "status": "healthy",
  "checks": {
    "database": "ok",
    "faiss_index": "ok",
    "telegram_polling": "ok"
  }
}
```

### Логи

**Просмотр логов контейнера:**
```bash
docker-compose logs -f app
```

**Файловые логи:**
- Расположение: `./logs/app.log`
- Формат: JSON (структурированные логи)
- Ротация: 100 MB
- Хранение: 30 дней
- Сжатие: ZIP

### Метрики производительности

**Использование ресурсов:**
```bash
docker stats neuro-support
```

**Размер образа:**
```bash
docker images | grep neuro-support
```

---

## 🐛 Troubleshooting

### Контейнер не запускается

**Проблема:** `docker-compose up` падает с ошибкой.

**Решения:**
1. Проверьте логи: `docker-compose logs app`
2. Убедитесь, что порты 8000, 80, 443 свободны
3. Проверьте наличие файла `.env` с корректными значениями
4. Пересоберите образ: `docker-compose build --no-cache`

### Telegram бот не отвечает

**Проблема:** Бот не реагирует на сообщения.

**Решения:**
1. **Конфликт подключений:** Убедитесь, что бот не запущен в другом месте
   ```bash
   # Сброс webhook
   https://api.telegram.org/bot<TOKEN>/deleteWebhook
   ```
2. **Неверный токен:** Проверьте `TELEGRAM_BOT_TOKEN` в `.env`
3. **Polling mode:** Убедитесь, что `TELEGRAM_USE_WEBHOOK=false`
4. Проверьте логи: `docker-compose logs app | grep telegram`

### Первый ответ есть, второй "виснет"

**Проблема:** Первый ответ уходит, а на втором кажется, что бот завис.

**Что это обычно значит:**
- Чаще всего это сетевой сбой до Telegram API (`api.telegram.org:443`), а не зависание RAG/LLM.
- Проверьте ошибки `TelegramNetworkError`, `ClientConnectorError`, `ConnectionRefusedError` в логах.

**Что уже учтено в коде:**
1. Ретраи отправки сообщений в Telegram (`1/2/4` сек).
2. Увеличенные таймауты отправки.
3. Логи этапов пайплайна: `rag_ms`, `llm_ms`, `send_ms`, `total_ms`.

**Как проверить:**
```bash
docker-compose logs -f app
```
Ищите строки вида:
```text
Telegram pipeline user=... sent=... rag_ms=... llm_ms=... send_ms=... total_ms=...
```

### RAG не находит ответы

**Проблема:** Бот отвечает "Точный ответ дадут в хелп-чате" на все вопросы.

**Решения:**
1. **Индекс не создан:** Зайдите в админку и пересоздайте индексы
2. **Пустая база знаний:** Заполните файл `data/knowledge_base.md`
3. **Низкий TOP_K:** Увеличьте `TOP_K_RESULTS` в `.env` до 5
4. Проверьте наличие файлов:
   ```bash
   ls -lh data/faiss_index/
   # Должны быть: index.faiss, metadata.json
   ```

### Превышен лимит памяти

**Проблема:** Контейнер падает с ошибкой OOM (Out of Memory).

**Решения:**
1. Увеличьте лимит в `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 4G  # Было 2G
   ```
2. Уменьшите размер базы знаний (разбейте на модули)
3. Уменьшите `CHUNK_SIZE` в `.env` до 500

### OpenAI API ошибки

**Проблема:** Ошибки `OpenAIError: Unauthorized` или `Rate limit exceeded`.

**Решения:**
1. **Неверный ключ:** Проверьте `OPENAI_API_KEY` в `.env`
2. **Нет средств:** Пополните баланс на https://platform.openai.com/account/billing
3. **Rate limit:** Подождите или увеличьте лимит в настройках OpenAI

### Админка не открывается / цикл авторизации

**Проблема:** После ввода логина/пароля форма появляется снова.

**Решения:**
1. **Неверные данные:** Проверьте `ADMIN_USERNAME` и `ADMIN_PASSWORD_HASH` в `.env`
2. **Кэш браузера:** Откройте в режиме инкогнито
3. **Формат пароля:** `ADMIN_PASSWORD_HASH` должен содержать bcrypt-хеш, а не обычный пароль. Сгенерируйте его командой из раздела быстрого старта.
4. **Пробелы в .env:** Убедитесь, что нет лишних пробелов:
   ```env
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD_HASH=$2b$12$...
   # НЕ: ADMIN_USERNAME = admin
   ```
5. Перезапустите контейнер: `docker compose restart app`

---

## 🔄 Обновление

### Обновление кода

```bash
# 1. Остановка контейнеров
docker-compose down

# 2. Получение обновлений
git pull origin main

# 3. Пересборка образа
docker-compose up -d --build

# 4. Проверка
docker-compose logs -f app
```

### Обновление базы знаний

**Через админку (рекомендуется):**
1. http://localhost:8000/admin/knowledge
2. Внесите изменения в текст
3. Нажмите **"Сохранить"**
4. Нажмите **"Пересоздать индексы"** (обязательно!)

**Напрямую через файл:**
```bash
# 1. Редактируйте файл
nano data/knowledge_base.md

# 2. Пересоздайте индексы
python migrate_embeddings.py

# Или через админку
```

### Миграция между версиями

При обновлении с v1.0 на v2.0:
```bash
# 1. Создайте backup
cp -r data data.backup

# 2. Запустите миграционный скрипт
python migrate_embeddings.py

# 3. Проверьте работоспособность
curl http://localhost:8000/health
```

---

## ❓ FAQ

### Сколько стоит OpenAI API?
Стоимость зависит от текущей цены выбранной модели, числа и длины запросов, а также embeddings. Проверьте актуальные тарифы у [OpenAI](https://openai.com/api/pricing/) или выбранного провайдера; фиксированная месячная оценка без измерений не приводится.

### Можно ли использовать ProxiAPI вместо OpenAI?
Да. Укажите в `.env`:
- `LLM_PROVIDER=proxiapi`
- `PROXIAPI_API_KEY=<ваш ключ>`
- `PROXIAPI_API_BASE=https://api.proxyapi.ru/openai/v1`

То же самое можно настроить через `/admin/settings` без ручного
редактирования файла. Настройки применяются сразу и сохраняются в `.env`,
который приложение читает и после перезапуска контейнера.

### Можно ли использовать другую AI модель?
Да. Измените `AI_MODEL` в `.env` или в админке и укажите модель, поддерживаемую выбранным провайдером. Текущая настройка — `gpt-4.1-mini`; перед публичным запуском проверьте её доступность и срок поддержки в [каталоге моделей OpenAI](https://developers.openai.com/api/docs/models/gpt-4.1-mini) либо у своего провайдера.

### Работает ли система без интернета?
Нет. Требуется доступ к API выбранного провайдера (OpenAI или ProxiAPI)
для генерации ответов и embeddings.

### Можно ли заменить OpenAI на локальную модель (LLaMA, Mistral)?
Технически да, но потребуется:
1. Переписать `ai_client.py` для работы с локальной моделью
2. Настроить локальный inference сервер (Ollama, vLLM)
3. Заменить OpenAI Embeddings на локальные (sentence-transformers вернется, +2.5 GB к образу)

### Сколько вопросов в час может обработать?
На пару чат/пользователь действует лимит по умолчанию 20 запросов за час. Общая пропускная способность не измерялась и зависит в основном от задержки и лимитов AI-провайдера; перед увеличением аудитории проведите нагрузочную проверку.

### Как добавить новый канал связи (WhatsApp, Viber)?
Создайте новый обработчик в `app/integrations/` по аналогии с `telegram_bot.py` или `jivo_webhook.py`.

### Можно ли использовать PostgreSQL вместо SQLite?
Да, замените `DATABASE_URL` в `app/database/questions_db.py` и установите `asyncpg`.

---

## 📝 Changelog

### v2.0.0-refactored (2026-02-14)
#### ⚡ Оптимизация
- Уменьшен размер Docker образа: 15-20 GB → **6 GB** (экономия 10+ GB)
- Ускорена сборка образа: 10-15 мин → **3-5 мин** (3x быстрее)
- Снижено потребление RAM: 1 GB idle → **512 MB** (2x меньше)

#### 🏗️ Инфраструктура
- Реализован multi-stage Docker build
- Создан `.dockerignore` для исключения ненужных файлов
- Добавлены health checks в Docker Compose
- Настроены ограничения ресурсов контейнера (CPU, RAM)

#### 📦 Зависимости
- Удалены неиспользуемые тяжелые библиотеки:
  - ❌ `sentence-transformers` (~2.5 GB) — не использовался
  - ❌ `torch` (~1.5 GB) — не использовался
  - ❌ `aiohttp` — заменен на `httpx`
- Создан отдельный `requirements-dev.txt` для разработки
- Оптимизирован `requirements.txt` (минимальный набор)

#### 🔧 Улучшения кода
- Добавлен миграционный скрипт `migrate_embeddings.py`
- Lazy imports для тяжелых библиотек (pandas)
- Оптимизировано логирование
- Улучшена обработка ошибок

#### 📖 Документация
- Полностью переписан README.md
- Добавлен раздел Troubleshooting
- Обновлены инструкции по установке
- Добавлен FAQ

### v1.0.0 (2026-02-13)
#### 🎉 Первый релиз
- 🤖 Telegram Bot (aiogram 3.x, polling)
- ⚙️ Настройки Jivo в админке; обработка вебхуков не подключена
- 📚 RAG система на базе FAISS + OpenAI Embeddings
- 🎨 Веб-админка (FastAPI + Jinja2 + Bootstrap 5)
- 📊 Аналитика уникальных вопросов
- 🛡️ Rate Limiting и Spam Filter
- 🧠 Context Manager для памяти диалога
- 🔐 HTTP Basic Auth для админки
- 📝 Логирование в JSON формат
- 🐳 Docker + Docker Compose

---

## 📄 Лицензия

MIT License. См. файл [LICENSE](LICENSE) для деталей.

---

## 👥 Контакты

**Проект:** Нейро-техподдержка Школы Михаила Агеева  
**Сайт:** https://mikhail-ageev.ru/  
**Help-chat:** https://t.me/Ageev_Help_chat  
**Версия:** 2.0.0-refactored  
**Дата релиза:** 14.04.2026

---

_Разработано с ❤️ для Школы Михаила Агеева (2026)_
