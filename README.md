# Tsushima Mini App API

FastAPI сервер для Telegram Mini App игры Ghost of Tsushima: Legends.

## Описание

Этот API предоставляет функциональность для:
- Управления профилями игроков
- Сохранения и загрузки трофеев
- Управления билдами персонажей
- Валидации данных от Telegram WebApp

## Технологии

- **Python 3.8+**
- **FastAPI** - современный веб-фреймворк
- **SQLite** - база данных
- **Uvicorn** - ASGI сервер

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

4. Настройте переменные окружения:
```bash
cp .env.example .env
# Отредактируйте .env файл с вашими настройками
```

## Запуск

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

- `GET /health` - проверка работоспособности
- `GET /api/profile.get` - получение профиля пользователя
- `POST /api/profile.save` - сохранение профиля пользователя
- `GET /api/stats` - статистика API

## Безопасность

- Валидация Telegram `initData` через HMAC-SHA256
- CORS настроен для домена GitHub Pages
- Переменные окружения для конфиденциальных данных

## Развертывание

Для развертывания на Raspberry Pi с systemd сервисом следуйте инструкциям в документации проекта.

## Лицензия

MIT License
