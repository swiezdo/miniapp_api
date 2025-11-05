# Контекст для AI-ассистента - Mini App API

Этот файл содержит важную информацию для AI-ассистента при работе с проектом miniapp_api.

## Общие принципы

- Проект использует **FastAPI** для REST API
- Код прошел **рефакторинг** - модули вынесены в отдельные файлы
- Все операции с БД используют **context manager** `db_connection`
- **SQL injection защита** через whitelist полей
- **Middleware** для фильтрации бот-запросов

## Важные нюансы и особенности

### Структура модулей после рефакторинга

1. **image_utils.py** - обработка изображений
   - `process_image_for_upload()` - универсальная обработка (EXIF, RGB конвертация)
   - `process_avatar_image()` - специальная обработка аватарок (обрезка, ресайз)
   - `validate_image_file()` - валидация типа файла
   - `temp_image_directory()` - context manager для временных директорий

2. **telegram_utils.py** - работа с Telegram Bot API
   - `send_telegram_message()` - отправка сообщений
   - `send_photos_to_telegram_group()` - отправка медиагрупп

3. **user_utils.py** - работа с пользователями
   - `get_user_with_psn()` - получение профиля с проверкой PSN ID
   - `format_profile_response()` - форматирование ответа профиля

4. **mastery_utils.py** - работа с мастерством
   - `find_category_by_key()` - поиск категории в конфиге
   - `parse_tags()` - парсинг тегов (JSON или строка через запятую)

5. **db.py** - работа с базой данных
   - Все функции используют `db_connection()` context manager
   - Вспомогательные функции: `parse_comma_separated_list()`, `join_comma_separated_list()`
   - `_build_dict_from_row()` - формирование словаря билда
   - `_get_reaction_stats()` - получение статистики реакций

### Безопасность

#### SQL Injection защита

- **set_mastery()**: использует whitelist `category_mapping` для безопасного обновления полей
- **update_build()**: использует whitelist `BUILD_UPDATE_FIELDS` для разрешенных полей
- **Никогда не использовать** f-строки для имен колонок в SQL!

Пример безопасного обновления:
```python
# ПРАВИЛЬНО:
if field_name in BUILD_UPDATE_FIELDS:
    cursor.execute(f'UPDATE builds SET {field_name} = ? WHERE ...', (value,))

# НЕПРАВИЛЬНО:
cursor.execute(f'UPDATE builds SET {field_name} = ? WHERE ...', (value,))  # SQL injection!
```

#### Middleware для ботов

- `filter_bot_requests()` - фильтрует известные бот-запросы (WordPress, phpMyAdmin и т.д.)
- Возвращает 404 без логирования для таких запросов
- Список путей в `bot_paths`

#### Валидация Telegram initData

- Используется HMAC-SHA256 для проверки подлинности
- Реализовано в `security.py`
- Dependency `get_current_user()` извлекает user_id из initData

### База данных

#### Структура таблиц

- **users**: профили пользователей (user_id, real_name, psn_id, platforms, modes, goals, difficulties, avatar_url)
- **builds**: билды (build_id, user_id, author, name, class, tags, description, photo_1, photo_2, created_at, is_public)
- **mastery**: уровни мастерства (user_id, solo, hellmode, raid, speedrun)
- **comments**: комментарии к билдам (comment_id, build_id, user_id, comment_text, created_at)
- **build_reactions**: лайки/дизлайки (reaction_id, build_id, user_id, reaction_type, created_at)

#### Context Manager для БД

Все операции с БД используют `db_connection()`:
```python
with db_connection(db_path) as cursor:
    if cursor is None:
        return None
    cursor.execute(...)
    # Автоматический commit при успехе, rollback при ошибке
```

#### Важные особенности

- **search_builds**: Python-side фильтрация для кириллицы (ОСТАВИТЬ КАК ЕСТЬ!)
  - SQLite LIKE может работать некорректно с кириллицей без специальных collation
  - Фильтрация в Python гарантирует правильную работу с кириллицей

- **parse_comma_separated_list()**: парсит списки из БД (platforms, modes, goals, difficulties)
- **join_comma_separated_list()**: объединяет списки для сохранения в БД

### Обработка изображений

#### Пути хранения

- **Аватарки**: `/root/miniapp_api/users/{user_id}/avatar.jpg`
- **Фото билдов**: `/root/miniapp_api/builds/{build_id}/photo_1.jpg`, `photo_2.jpg`
- **Временные файлы**: через `temp_image_directory()` context manager

#### Процесс обработки

1. Валидация типа файла (`validate_image_file()`)
2. Открытие через Pillow (`Image.open()`)
3. Обработка:
   - Для аватарок: `process_avatar_image()` (обрезка, ресайз)
   - Для билдов/отзывов: `process_image_for_upload()` (EXIF, RGB конвертация)
4. Сохранение как JPEG

### Playwright для скриншотов

- Используется для создания скриншотов профилей
- Endpoint: `/api/send_profile/{user_id}`
- HTML-шаблон: `profile_preview.html`
- Ожидает готовности страницы через JavaScript (`data-ready` атрибут)

## Интеграции с другими проектами

### gyozenbot

- **Прямой доступ к SQLite БД**: `/root/miniapp_api/app.db`
  - gyozenbot использует `sys.path.append('/root/miniapp_api')` для импорта
  - Использует функции из `db.py` напрямую
  
- **REST API**: 
  - gyozenbot вызывает `/api/builds.get/{build_id}` для получения билдов
  - gyozenbot вызывает `/api/send_profile/{user_id}` для скриншотов профилей
  
- **Общий BOT_TOKEN**: один токен используется и gyozenbot, и miniapp_api
  - miniapp_api использует его для отправки уведомлений
  - gyozenbot использует его для работы бота

### tsushimaru_app

- **Статические файлы**: `/root/tsushimaru_app/docs`
  - Маунтятся через `app.mount("/assets", StaticFiles(...))`
  - Содержат `mastery-config.json`, `whats-new.json`
  
- **REST API**: frontend взаимодействует только через REST API
  - Валидация через Telegram initData
  - CORS настроен для GitHub Pages

## Частые задачи и их решения

### Добавление нового endpoint

1. Определить метод (GET/POST/PUT/DELETE)
2. Добавить dependency `get_current_user` если нужна авторизация
3. Использовать функции из модулей (db.py, user_utils.py и т.д.)
4. Обработка ошибок через `HTTPException`

### Работа с изображениями

```python
from image_utils import validate_image_file, process_image_for_upload, temp_image_directory

# Валидация
if not validate_image_file(upload_file):
    raise HTTPException(status_code=400, detail="Только изображения")

# Обработка
image = Image.open(upload_file.file)
process_image_for_upload(image, output_path)

# Временная директория
with temp_image_directory(prefix='prefix_') as temp_dir:
    # Работа с временными файлами
```

### Работа с БД

```python
from db import get_user, upsert_user, create_build, ...

# Всегда используйте функции из db.py, не прямые SQL запросы!
profile = get_user(DB_PATH, user_id)
build_id = create_build(DB_PATH, build_data)
```

### Отправка в Telegram

```python
from telegram_utils import send_telegram_message, send_photos_to_telegram_group

# Сообщение
await send_telegram_message(
    bot_token=BOT_TOKEN,
    chat_id=chat_id,
    text="Сообщение",
    message_thread_id=topic_id  # опционально
)

# Медиагруппа
await send_photos_to_telegram_group(
    bot_token=BOT_TOKEN,
    chat_id=chat_id,
    photo_paths=[path1, path2],
    message_text="Подпись",
    message_thread_id=topic_id  # опционально
)
```

### Обновление билда

```python
# Используйте whitelist полей!
build_data = {
    'name': name,  # В BUILD_UPDATE_FIELDS
    'class': class_name,  # В BUILD_UPDATE_FIELDS
    # ...
}
success = update_build(DB_PATH, build_id, user_id, build_data)
```

### Парсинг тегов

```python
from mastery_utils import parse_tags

# Поддерживает JSON и строку через запятую
tags_list = parse_tags(tags)  # tags может быть '["tag1", "tag2"]' или 'tag1, tag2'
```

## Известные ограничения

1. **search_builds**: Python-side фильтрация для кириллицы - НЕ МЕНЯТЬ!
   - Это сделано специально для корректной работы с кириллицей
   - SQLite LIKE может работать некорректно без специальных collation

2. **Прямой доступ к БД из gyozenbot**: используется `sys.path.append`, что может быть не идеально, но работает

3. **Общий BOT_TOKEN**: один токен для gyozenbot и miniapp_api - учитывать при работе с API

4. **init_db()**: упрощена, убрана сложная логика миграции (база уже существует)

5. **Middleware для ботов**: фильтрует известные пути, но не защищает от всех ботов

## Структура проекта

```
miniapp_api/
├── app.py              # Главный FastAPI файл
├── db.py               # Работа с SQLite БД
├── security.py         # Валидация Telegram initData
├── image_utils.py      # Обработка изображений
├── telegram_utils.py   # Работа с Telegram Bot API
├── user_utils.py       # Утилиты для пользователей
├── mastery_utils.py    # Утилиты для мастерства
├── mastery_config.py   # Загрузка конфига мастерства
├── profile_preview.html # HTML шаблон для скриншотов
├── app.db              # SQLite база данных
├── users/              # Аватарки пользователей
├── builds/             # Фото билдов
├── requirements.txt    # Зависимости
└── CONTEXT.md          # Этот файл
```

## API Endpoints

### Профили
- `GET /api/profile.get` - получение профиля
- `POST /api/profile.save` - сохранение профиля
- `GET /api/users.list` - список пользователей
- `GET /api/users.getProfile` - профиль по ID
- `POST /api/users/avatars/{target_user_id}/upload` - загрузка аватарки
- `GET /users/{user_id}/avatar.jpg` - получение аватарки

### Билды
- `POST /api/builds.create` - создание билда
- `GET /api/builds.getMy` - мои билды
- `GET /api/builds.getPublic` - публичные билды
- `GET /api/builds.search` - поиск билдов
- `GET /api/builds.get/{build_id}` - билд по ID
- `GET /api/builds.getUserBuilds` - билды пользователя
- `POST /api/builds.togglePublish` - публикация/скрытие
- `DELETE /api/builds.delete` - удаление билда
- `POST /api/builds.update` - обновление билда
- `GET /builds/{build_id}/{photo_name}` - фото билда

### Комментарии
- `POST /api/comments.create` - создание комментария
- `GET /api/comments.get` - комментарии билда

### Реакции
- `POST /api/builds.toggleReaction` - лайк/дизлайк
- `GET /api/builds.getReactions/{build_id}` - статистика реакций

### Мастерство
- `GET /api/mastery.get` - уровни мастерства
- `POST /api/mastery.submitApplication` - заявка на повышение
- `POST /api/mastery.approve` - одобрение (только для бота)
- `POST /api/mastery.reject` - отклонение (только для бота)

### Другое
- `GET /health` - проверка работоспособности
- `GET /api/stats` - статистика API
- `POST /api/feedback.submit` - отзыв/баг-репорт
- `GET /profile-preview/{user_id}` - HTML для скриншота
- `POST /api/send_profile/{user_id}` - создание и отправка скриншота

