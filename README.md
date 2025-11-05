# Tsushima Mini App API

FastAPI сервер для Telegram Mini App игры Ghost of Tsushima: Legends.

## Описание

Этот API предоставляет функциональность для:
- Управления профилями игроков (создание, редактирование, просмотр)
- Управления билдами персонажей (создание, редактирование, публикация, поиск)
- Системы комментариев и реакций (лайки/дизлайки)
- Системы мастерства (уровни по категориям, заявки на повышение)
- Загрузки аватарок и обработки изображений
- Валидации данных от Telegram WebApp
- Создания скриншотов профилей через Playwright

## Технологии

- **Python 3.8+**
- **FastAPI** - современный веб-фреймворк
- **SQLite** - база данных
- **Uvicorn** - ASGI сервер
- **Pillow** - обработка изображений
- **Playwright** - создание скриншотов профилей
- **aiohttp** - асинхронные HTTP запросы к Telegram Bot API

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd miniapp_api
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate     # Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Установите Playwright браузеры:
```bash
playwright install chromium
```

5. Настройте переменные окружения:
Создайте файл `.env` в корне проекта:
```env
BOT_TOKEN=your_telegram_bot_token
ALLOWED_ORIGIN=https://swiezdo.github.io
DB_PATH=/root/miniapp_api/app.db
TROPHY_GROUP_CHAT_ID=-1002348168326
TROPHY_GROUP_TOPIC_ID=5675
BOT_USERNAME=your_bot_username
```

## Запуск

### Разработка
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

### Production (systemd)
```bash
sudo systemctl start miniapp_api
sudo systemctl status miniapp_api
```

## Структура проекта

После рефакторинга код разделен на модули:

```
miniapp_api/
├── app.py              # Главный FastAPI файл с endpoints
├── db.py               # Работа с SQLite БД (context manager)
├── security.py         # Валидация Telegram initData (HMAC-SHA256)
├── image_utils.py      # Обработка изображений (EXIF, RGB, обрезка)
├── telegram_utils.py   # Работа с Telegram Bot API
├── user_utils.py       # Утилиты для работы с пользователями
├── mastery_utils.py    # Утилиты для работы с мастерством
├── mastery_config.py   # Загрузка конфига мастерства
├── profile_preview.html # HTML шаблон для скриншотов профилей
├── app.db              # SQLite база данных
├── users/              # Аватарки пользователей
├── builds/             # Фото билдов
├── requirements.txt    # Зависимости
└── CONTEXT.md          # Контекст для AI-ассистента
```

## API Endpoints

### Профили пользователей

- `GET /api/profile.get` - получение профиля текущего пользователя
- `POST /api/profile.save` - сохранение/обновление профиля
- `GET /api/users.list` - список всех пользователей с уровнями мастерства
- `GET /api/users.getProfile` - получение профиля по user_id
- `POST /api/users/avatars/{target_user_id}/upload` - загрузка аватарки
- `GET /users/{user_id}/avatar.jpg` - получение аватарки пользователя

### Билды

- `POST /api/builds.create` - создание нового билда (с загрузкой фото)
- `GET /api/builds.getMy` - получение всех билдов текущего пользователя
- `GET /api/builds.getPublic` - получение всех публичных билдов
- `GET /api/builds.search?query=...&limit=10` - поиск публичных билдов
- `GET /api/builds.get/{build_id}` - получение билда по ID
- `GET /api/builds.getUserBuilds?target_user_id=...` - публичные билды пользователя
- `POST /api/builds.togglePublish` - публикация/скрытие билда
- `DELETE /api/builds.delete?build_id=...` - удаление билда
- `POST /api/builds.update` - обновление билда (с опциональной загрузкой фото)
- `GET /builds/{build_id}/{photo_name}` - получение фото билда

### Комментарии

- `POST /api/comments.create` - создание комментария к билду
- `GET /api/comments.get?build_id=...` - получение комментариев билда

### Реакции (лайки/дизлайки)

- `POST /api/builds.toggleReaction` - переключение реакции (лайк/дизлайк)
- `GET /api/builds.getReactions/{build_id}` - получение статистики реакций

### Мастерство

- `GET /api/mastery.get?target_user_id=...` - получение уровней мастерства
- `POST /api/mastery.submitApplication` - подача заявки на повышение уровня
- `POST /api/mastery.approve` - одобрение заявки (только для бота, авторизация через Authorization header)
- `POST /api/mastery.reject` - отклонение заявки (только для бота, авторизация через Authorization header)

### Другое

- `GET /health` - проверка работоспособности API
- `GET /api/stats` - статистика API (количество пользователей)
- `POST /api/feedback.submit` - отправка отзыва/баг-репорта
- `GET /profile-preview/{user_id}` - HTML страница для скриншота профиля
- `POST /api/send_profile/{user_id}` - создание и отправка скриншота профиля в Telegram

## Безопасность

### Валидация Telegram initData

- Все endpoints (кроме публичных) требуют заголовок `X-Telegram-Init-Data`
- Валидация через HMAC-SHA256 алгоритм
- Реализовано в `security.py`

### SQL Injection защита

- Использование параметризованных запросов (placeholders `?`)
- Whitelist полей для обновлений (`BUILD_UPDATE_FIELDS`, `category_mapping`)
- Все операции с БД через функции из `db.py`

### Middleware для ботов

- Фильтрация известных бот-запросов (WordPress, phpMyAdmin и т.д.)
- Возвращает 404 без логирования для таких запросов

### CORS

- Настроен для домена GitHub Pages (`https://swiezdo.github.io`)
- Поддержка localhost для разработки

## База данных

### Структура таблиц

- **users**: профили пользователей
  - `user_id` (PRIMARY KEY), `real_name`, `psn_id`, `platforms`, `modes`, `goals`, `difficulties`, `avatar_url`
  
- **builds**: билды персонажей
  - `build_id` (PRIMARY KEY AUTOINCREMENT), `user_id`, `author`, `name`, `class`, `tags`, `description`, `photo_1`, `photo_2`, `created_at`, `is_public`
  
- **mastery**: уровни мастерства
  - `user_id` (PRIMARY KEY), `solo`, `hellmode`, `raid`, `speedrun`
  
- **comments**: комментарии к билдам
  - `comment_id` (PRIMARY KEY AUTOINCREMENT), `build_id`, `user_id`, `comment_text`, `created_at`
  
- **build_reactions**: реакции на билды
  - `reaction_id` (PRIMARY KEY AUTOINCREMENT), `build_id`, `user_id`, `reaction_type` ('like'/'dislike'), `created_at`
  - UNIQUE(build_id, user_id) - один пользователь может поставить только одну реакцию

### Context Manager для БД

Все операции с БД используют `db_connection()` context manager:
- Автоматический commit при успехе
- Автоматический rollback при ошибке
- Правильное закрытие соединений

## Обработка изображений

### Аватарки

- Загружаются через `/api/users/avatars/{target_user_id}/upload`
- Обработка: обрезка до квадрата, ресайз до 400x400, конвертация в RGB, сохранение как JPEG
- Хранение: `/root/miniapp_api/users/{user_id}/avatar.jpg`

### Фото билдов

- Загружаются при создании/обновлении билда
- Обработка: исправление EXIF ориентации, конвертация в RGB, сохранение как JPEG
- Хранение: `/root/miniapp_api/builds/{build_id}/photo_1.jpg`, `photo_2.jpg`

### Временные файлы

- Используется `temp_image_directory()` context manager
- Автоматическая очистка после использования

## Интеграции

### gyozenbot

- **Прямой доступ к SQLite БД**: `/root/miniapp_api/app.db`
- **REST API**: получение билдов, создание скриншотов профилей
- **Общий BOT_TOKEN**: один токен используется и gyozenbot, и miniapp_api

### tsushimaru_app

- **Статические файлы**: `/root/tsushimaru_app/docs` (маунтятся через `/assets`)
- **REST API**: frontend взаимодействует только через REST API
- **Валидация**: через Telegram initData

## Развертывание

### Systemd сервис

Создайте файл `/etc/systemd/system/miniapp_api.service`:
```ini
[Unit]
Description=Tsushima Mini App API
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/miniapp_api
Environment="PATH=/root/miniapp_api/venv/bin"
ExecStart=/root/miniapp_api/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Запуск:
```bash
sudo systemctl daemon-reload
sudo systemctl enable miniapp_api
sudo systemctl start miniapp_api
```

### Обновление кода

```bash
cd /root/miniapp_api
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart miniapp_api
```

## Дополнительная информация

Для более детальной информации о работе с проектом см. [CONTEXT.md](CONTEXT.md) - файл с контекстом для AI-ассистента, содержащий важные нюансы рефакторинга, особенности безопасности и примеры использования.

## Лицензия

MIT License
