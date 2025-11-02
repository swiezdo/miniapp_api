# app.py
# FastAPI приложение для Tsushima Mini App API
# Проверка пуша на GitHub

import os
import shutil
import json
import time
import requests
import tempfile
import sqlite3
from fastapi import FastAPI, HTTPException, Depends, Header, Form, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from PIL import Image, ImageOps
import re

# Импортируем наши модули
from security import validate_init_data, get_user_id_from_init_data
from db import init_db, get_user, upsert_user, create_build, get_build, get_user_builds, update_build_visibility, delete_build, update_build, get_all_users, get_mastery, create_comment, get_build_comments

# Загружаем переменные окружения
load_dotenv()

# Создаем FastAPI приложение
app = FastAPI(
    title="Tsushima Mini App API",
    description="API для Telegram Mini App Tsushima.Ru",
    version="1.0.0"
)

# Получаем конфигурацию из .env
BOT_TOKEN = os.getenv("BOT_TOKEN")
ALLOWED_ORIGIN = os.getenv("ALLOWED_ORIGIN")
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")

# Параметры для отправки уведомлений/сообщений
TROPHY_GROUP_CHAT_ID = os.getenv("TROPHY_GROUP_CHAT_ID", "-1002348168326")
TROPHY_GROUP_TOPIC_ID = os.getenv("TROPHY_GROUP_TOPIC_ID", "5675")
BOT_USERNAME = os.getenv("BOT_USERNAME", "swiezdo_testbot")

# Удалены кеш и загрузка данных трофеев

# Функции для работы с Telegram Bot API
async def send_telegram_message(chat_id: str, text: str, reply_markup: dict = None, message_thread_id: str = None):
    """
    Отправляет сообщение в Telegram через Bot API.
    """
    import aiohttp
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    if message_thread_id:
        data["message_thread_id"] = message_thread_id
    
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            return await response.json()

async def send_telegram_photo(chat_id: str, photo_path: str, caption: str = "", reply_markup: dict = None, message_thread_id: str = None):
    """
    Отправляет фотографию в Telegram через Bot API.
    """
    import aiohttp
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    with open(photo_path, 'rb') as photo_file:
        data = aiohttp.FormData()
        data.add_field('chat_id', chat_id)
        data.add_field('photo', photo_file, filename='photo.jpg')
        data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')
        
        if message_thread_id:
            data.add_field('message_thread_id', message_thread_id)
        
        if reply_markup:
            data.add_field('reply_markup', json.dumps(reply_markup))
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.json()

async def send_telegram_media_group(chat_id: str, photo_paths: List[str], caption: str = "", message_thread_id: str = None):
    """
    Отправляет группу фотографий в Telegram через Bot API.
    """
    import aiohttp
    
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMediaGroup"
    
    media = []
    for i, photo_path in enumerate(photo_paths):
        media.append({
            "type": "photo",
            "media": f"attach://photo_{i}"
        })
    
    # Открываем все файлы
    photo_files = []
    try:
        for photo_path in photo_paths:
            photo_files.append(open(photo_path, 'rb'))
        
        data = aiohttp.FormData()
        data.add_field('chat_id', chat_id)
        data.add_field('media', json.dumps(media))
        data.add_field('parse_mode', 'HTML')
        
        if message_thread_id:
            data.add_field('message_thread_id', message_thread_id)
        
        # Добавляем файлы в FormData
        for i, photo_file in enumerate(photo_files):
            data.add_field(f'photo_{i}', photo_file, filename=f'photo_{i}.jpg')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                result = await response.json()
                return result
    finally:
        # Закрываем все файлы
        for photo_file in photo_files:
            photo_file.close()

# Проверяем обязательные переменные
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env файле")
if not ALLOWED_ORIGIN:
    raise ValueError("ALLOWED_ORIGIN не установлен в .env файле")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://swiezdo.github.io", "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Инициализируем базу данных при запуске
init_db(DB_PATH)

# Удалена синхронизация трофеев при запуске

# Глобальный обработчик OPTIONS запросов
@app.options("/{path:path}")
async def options_handler(path: str, request: Request):
    """
    Глобальный обработчик OPTIONS запросов для CORS.
    """
    print(f"🔍 Глобальный OPTIONS запрос для пути: /{path}")
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": request.headers.get("origin", "*"),
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


def get_current_user(x_telegram_init_data: Optional[str] = Header(None)) -> int:
    """
    Dependency для получения текущего пользователя из Telegram initData.
    
    Args:
        x_telegram_init_data: Заголовок X-Telegram-Init-Data
    
    Returns:
        user_id (int) при успешной валидации
    
    Raises:
        HTTPException: При ошибке авторизации
    """
    if not x_telegram_init_data:
        raise HTTPException(
            status_code=401,
            detail="Отсутствует заголовок X-Telegram-Init-Data"
        )
    
    # Валидируем initData
    init_data = validate_init_data(x_telegram_init_data, BOT_TOKEN)
    if not init_data:
        raise HTTPException(
            status_code=401,
            detail="Невалидные данные авторизации"
        )
    
    # Извлекаем user_id
    user_id = get_user_id_from_init_data(init_data)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Не удалось извлечь user_id из данных авторизации"
        )
    
    return user_id


def validate_psn_format(psn: str) -> bool:
    """
    Валидирует формат PSN никнейма.
    
    Args:
        psn: PSN никнейм
    
    Returns:
        True если формат корректный
    """
    if not psn:
        return False
    
    # Проверяем по регулярному выражению: 3-16 символов, A-Z, a-z, 0-9, -, _
    pattern = r'^[A-Za-z0-9_-]{3,16}$'
    return bool(re.match(pattern, psn))


@app.get("/health")
async def health_check():
    """
    Эндпоинт для проверки работоспособности API.
    """
    return {"status": "ok", "message": "Tsushima Mini App API работает"}


# Эндпоинты трофеев удалены





@app.options("/api/profile.get")
async def options_profile_get():
    """
    OPTIONS эндпоинт для CORS preflight запросов.
    """
    print(f"🔍 OPTIONS /api/profile.get - ALLOWED_ORIGIN: {ALLOWED_ORIGIN}")
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


@app.options("/api/profile.save")
async def options_profile_save():
    """
    OPTIONS эндпоинт для CORS preflight запросов.
    """
    print(f"🔍 OPTIONS /api/profile.save - ALLOWED_ORIGIN: {ALLOWED_ORIGIN}")
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": ALLOWED_ORIGIN,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "true",
        }
    )


@app.get("/api/profile.get")
async def get_profile(user_id: int = Depends(get_current_user)):
    """
    Получает профиль текущего пользователя.
    
    Args:
        user_id: ID пользователя (из dependency)
    
    Returns:
        JSON с данными профиля или 404 если профиль не найден
    """
    profile = get_user(DB_PATH, user_id)
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Профиль не найден"
        )
    
    # Убираем служебные поля из ответа
    response_data = {
        "user_id": user_id,  # Нужен для загрузки аватарки на фронтенде
        "real_name": profile.get("real_name", ""),
        "psn_id": profile.get("psn_id", ""),
        "platforms": profile.get("platforms", []),
        "modes": profile.get("modes", []),
        "goals": profile.get("goals", []),
        "difficulties": profile.get("difficulties", []),
        "avatar_url": profile.get("avatar_url")
    }
    
    return response_data


@app.post("/api/profile.save")
async def save_profile(
    user_id: int = Depends(get_current_user),
    real_name: str = Form(...),
    psn_id: str = Form(...),
    platforms: List[str] = Form(default=[]),
    modes: List[str] = Form(default=[]),
    goals: List[str] = Form(default=[]),
    difficulties: List[str] = Form(default=[])
):
    """
    Сохраняет или обновляет профиль пользователя.
    
    Args:
        user_id: ID пользователя (из dependency)
        real_name: Реальное имя пользователя
        psn_id: PSN никнейм
        platforms: Список платформ
        modes: Список режимов
        goals: Список целей
        difficulties: Список сложностей
    
    Returns:
        JSON с результатом операции
    """
    # Валидация входных данных
    if not real_name or not real_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Поле 'real_name' обязательно для заполнения"
        )

    if not validate_psn_format(psn_id):
        raise HTTPException(
            status_code=400,
            detail="Неверный формат PSN никнейма (3-16 символов: A-Z, a-z, 0-9, -, _)"
        )

    # Подготавливаем данные для сохранения
    profile_data = {
        "real_name": real_name.strip(),
        "psn_id": psn_id.strip(),
        "platforms": platforms,
        "modes": modes,
        "goals": goals,
        "difficulties": difficulties
    }

    # Сохраняем профиль
    success = upsert_user(DB_PATH, user_id, profile_data)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Ошибка при сохранении профиля"
        )

    return {"status": "ok", "message": "Профиль успешно сохранен"}


@app.get("/api/users.list")
async def get_users_list(user_id: int = Depends(get_current_user)):
    """
    Получает список всех пользователей.
    
    Args:
        user_id: ID пользователя (из dependency, для проверки авторизации)
    
    Returns:
        JSON со списком пользователей (user_id, psn_id, avatar_url и max_mastery_levels)
    """
    users = get_all_users(DB_PATH)
    
    # Загружаем конфиг мастерства для определения максимальных уровней
    try:
        config = load_mastery_config()
        
        # Создаем словарь максимальных уровней по категориям
        max_levels_map = {}
        for category in config.get('categories', []):
            category_key = category.get('key')
            max_levels = category.get('maxLevels', 0)
            if category_key:
                max_levels_map[category_key] = max_levels
        
        # Определяем категории с максимальными уровнями для каждого пользователя
        for user in users:
            max_mastery_levels = []
            mastery = user.get('mastery', {})
            
            # Проверяем категории в строгом порядке: solo, hellmode, raid, speedrun
            categories_order = ['solo', 'hellmode', 'raid', 'speedrun']
            for category_key in categories_order:
                if category_key in max_levels_map:
                    max_level = max_levels_map[category_key]
                    current_level = mastery.get(category_key, 0)
                    if current_level >= max_level and max_level > 0:
                        max_mastery_levels.append(category_key)
            
            # Удаляем поле mastery из ответа (оставляем только max_mastery_levels)
            user.pop('mastery', None)
            user['max_mastery_levels'] = max_mastery_levels
    
    except Exception as e:
        print(f"Ошибка обработки уровней мастерства: {e}")
        # В случае ошибки просто добавляем пустой массив для всех пользователей
        for user in users:
            user.pop('mastery', None)
            user['max_mastery_levels'] = []
    
    return {"users": users}


@app.get("/api/users.getProfile")
async def get_user_profile(
    target_user_id: int,
    user_id: int = Depends(get_current_user)
):
    """
    Получает профиль указанного пользователя.
    
    Args:
        target_user_id: ID пользователя, чей профиль нужно получить
        user_id: ID текущего пользователя (из dependency, для проверки авторизации)
    
    Returns:
        JSON с данными профиля или 404 если профиль не найден
    """
    profile = get_user(DB_PATH, target_user_id)
    
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Профиль пользователя не найден"
        )
    
    # Убираем служебные поля из ответа
    response_data = {
        "user_id": profile.get("user_id"),
        "real_name": profile.get("real_name", ""),
        "psn_id": profile.get("psn_id", ""),
        "platforms": profile.get("platforms", []),
        "modes": profile.get("modes", []),
        "goals": profile.get("goals", []),
        "difficulties": profile.get("difficulties", []),
        "avatar_url": profile.get("avatar_url")
    }
    
    return response_data


@app.get("/api/stats")
async def get_stats():
    """
    Возвращает статистику API (количество пользователей).
    """
    from db import get_user_count
    
    user_count = get_user_count(DB_PATH)
    
    return {
        "total_users": user_count,
        "api_version": "1.0.0"
    }


# ========== API ЭНДПОИНТЫ ДЛЯ АВАТАРОК ==========

@app.post("/api/users/avatars/{target_user_id}/upload")
async def upload_avatar(
    target_user_id: int,
    avatar: UploadFile = File(...),
    user_id: int = Depends(get_current_user)
):
    """
    Загружает аватарку пользователя.
    
    Args:
        target_user_id: ID пользователя, для которого загружается аватарка
        avatar: Загружаемое изображение
        user_id: ID текущего пользователя (для проверки прав)
    
    Returns:
        JSON с результатом операции
    """
    # Проверка прав доступа
    if target_user_id != user_id:
        raise HTTPException(
            status_code=403,
            detail="Вы можете загружать аватарку только для себя"
        )
    
    # Валидация типа файла
    if not avatar.content_type or not avatar.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="Разрешены только изображения"
        )
    
    # Обрабатываем и сохраняем изображение
    try:
        # Создаем директорию для пользователя
        user_dir = os.path.join(os.path.dirname(DB_PATH), 'users', str(user_id))
        os.makedirs(user_dir, exist_ok=True)
        
        # Путь для сохранения аватарки
        avatar_path = os.path.join(user_dir, 'avatar.jpg')
        
        # Открываем изображение через Pillow
        image = Image.open(avatar.file)
        
        # Исправляем ориентацию согласно EXIF-метаданным
        image = ImageOps.exif_transpose(image)
        
        # Квадратная обрезка по центру
        width, height = image.size
        min_dimension = min(width, height)
        left = (width - min_dimension) // 2
        top = (height - min_dimension) // 2
        right = left + min_dimension
        bottom = top + min_dimension
        image = image.crop((left, top, right, bottom))
        
        # Ресайз до 300x300
        image = image.resize((300, 300), Image.Resampling.LANCZOS)
        
        # Конвертируем в RGB если нужно
        if image.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'P':
                image = image.convert('RGBA')
            background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
            image = background
        
        # Сохраняем как JPEG
        image.save(avatar_path, 'JPEG', quality=85, optimize=True)
        
        # Обновляем avatar_url в БД
        avatar_url = f"/users/{user_id}/avatar.jpg"
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users SET avatar_url = ? WHERE user_id = ?
        ''', (avatar_url, user_id))
        conn.commit()
        conn.close()
        
        return {
            "status": "ok",
            "message": "Аватарка успешно загружена",
            "avatar_url": avatar_url
        }
        
    except Exception as e:
        print(f"Ошибка обработки аватарки: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки аватарки: {str(e)}"
        )


@app.get("/users/{user_id}/avatar.jpg")
async def get_avatar(user_id: int):
    """
    Возвращает аватарку пользователя.
    
    Args:
        user_id: ID пользователя
    
    Returns:
        Изображение аватарки или 404 если не найдена
    """
    avatar_path = os.path.join(os.path.dirname(DB_PATH), 'users', str(user_id), 'avatar.jpg')
    
    if not os.path.exists(avatar_path):
        raise HTTPException(
            status_code=404,
            detail="Аватарка не найдена"
        )
    
    return FileResponse(avatar_path, media_type='image/jpeg')


# ========== API ЭНДПОИНТЫ ДЛЯ БИЛДОВ ==========

@app.post("/api/builds.create")
async def create_build_endpoint(
    user_id: int = Depends(get_current_user),
    name: str = Form(...),
    class_name: str = Form(...),
    tags: str = Form(...),  # JSON строка
    description: str = Form(""),
    photo_1: UploadFile = File(...),
    photo_2: UploadFile = File(...)
):
    """
    Создает новый билд с загрузкой изображений.
    """
    # Получаем профиль пользователя для получения psn_id
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(
            status_code=404,
            detail="Профиль пользователя не найден"
        )
    
    author = user_profile.get('psn_id', '')
    if not author:
        raise HTTPException(
            status_code=400,
            detail="PSN ID не указан в профиле"
        )
    
    # Валидация названия
    if not name or not name.strip():
        raise HTTPException(
            status_code=400,
            detail="Название билда обязательно"
        )
    
    # Валидация класса
    if not class_name or not class_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Класс обязателен"
        )
    
    # Парсим теги (может быть JSON строка или строка через запятую)
    try:
        import json
        # Пытаемся распарсить как JSON
        if tags.startswith('[') and tags.endswith(']'):
            tags_list = json.loads(tags)
        else:
            # Иначе парсим как строку через запятую
            tags_list = [t.strip() for t in tags.split(',') if t.strip()]
    except:
        # Если не удалось распарсить, пытаемся как строку через запятую
        try:
            tags_list = [t.strip() for t in tags.split(',') if t.strip()] if tags else []
        except:
            tags_list = []
    
    # Создаем временный билд для получения build_id
    build_data = {
        'user_id': user_id,
        'author': author,
        'name': name.strip(),
        'class': class_name.strip(),
        'tags': tags_list,
        'description': description.strip(),
        'photo_1': '',  # Временно пустое
        'photo_2': '',  # Временно пустое
        'is_public': 0
    }
    
    build_id = create_build(DB_PATH, build_data)
    if not build_id:
        raise HTTPException(
            status_code=500,
            detail="Ошибка создания билда"
        )
    
    # Создаем директорию для билда
    builds_dir = os.path.join(os.path.dirname(DB_PATH), 'builds', str(build_id))
    os.makedirs(builds_dir, exist_ok=True)
    
    # Обрабатываем и сохраняем изображения
    try:
        # Обработка первого изображения
        photo_1_path = os.path.join(builds_dir, 'photo_1.jpg')
        image1 = Image.open(photo_1.file)
        # Исправляем ориентацию согласно EXIF-метаданным
        image1 = ImageOps.exif_transpose(image1)
        # Конвертируем в RGB если нужно (PNG с альфа-каналом)
        if image1.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image1.size, (255, 255, 255))
            if image1.mode == 'P':
                image1 = image1.convert('RGBA')
            background.paste(image1, mask=image1.split()[-1] if image1.mode == 'RGBA' else None)
            image1 = background
        image1.save(photo_1_path, 'JPEG', quality=85, optimize=True)
        photo_1.file.seek(0)  # Возвращаем курсор
        
        # Обработка второго изображения
        photo_2_path = os.path.join(builds_dir, 'photo_2.jpg')
        image2 = Image.open(photo_2.file)
        # Исправляем ориентацию согласно EXIF-метаданным
        image2 = ImageOps.exif_transpose(image2)
        if image2.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', image2.size, (255, 255, 255))
            if image2.mode == 'P':
                image2 = image2.convert('RGBA')
            background.paste(image2, mask=image2.split()[-1] if image2.mode == 'RGBA' else None)
            image2 = background
        image2.save(photo_2_path, 'JPEG', quality=85, optimize=True)
        
        # Обновляем пути к изображениям в БД
        photo_1_url = f"/builds/{build_id}/photo_1.jpg"
        photo_2_url = f"/builds/{build_id}/photo_2.jpg"
        
        # Обновляем билд с путями
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE builds SET photo_1 = ?, photo_2 = ? WHERE build_id = ?
        ''', (photo_1_url, photo_2_url, build_id))
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"Ошибка обработки изображений: {e}")
        # Удаляем билд при ошибке
        delete_build(DB_PATH, build_id, user_id)
        # Удаляем папку
        if os.path.exists(builds_dir):
            shutil.rmtree(builds_dir)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки изображений: {str(e)}"
        )
    
    return {
        "status": "ok",
        "message": "Билд успешно создан",
        "build_id": build_id
    }


@app.get("/api/builds.getMy")
async def get_my_builds(user_id: int = Depends(get_current_user)):
    """
    Получает все билды текущего пользователя.
    """
    builds = get_user_builds(DB_PATH, user_id)
    return {
        "status": "ok",
        "builds": builds
    }


@app.get("/api/builds.getPublic")
async def get_public_builds_endpoint():
    """
    Получает все публичные билды.
    """
    from db import get_public_builds as db_get_public_builds
    builds = db_get_public_builds(DB_PATH)
    return {
        "status": "ok",
        "builds": builds
    }

@app.get("/api/builds.search")
async def search_builds_endpoint(query: str, limit: int = 10):
    """
    Поиск публичных билдов по названию, описанию, тегам, классу, автору или ID.
    
    Args:
        query: Поисковый запрос (текст или число для поиска по ID)
        limit: Максимальное количество результатов (по умолчанию 10)
    
    Returns:
        JSON со списком найденных публичных билдов
    """
    from db import search_builds as db_search_builds
    
    builds = db_search_builds(DB_PATH, query, limit)
    return {
        "status": "ok",
        "builds": builds
    }


@app.get("/api/builds.get/{build_id}")
async def get_build_by_id_endpoint(build_id: int):
    """Получить билд по ID"""
    build = get_build(DB_PATH, build_id)
    
    if not build:
        raise HTTPException(status_code=404, detail="Билд не найден")
    
    # Проверка на публичность
    if not build.get('is_public'):
        return JSONResponse(
            status_code=403,
            content={"error": "Билд не опубликован", "is_private": True}
        )
    
    return JSONResponse(content={"build": build})


@app.get("/api/builds.getUserBuilds")
async def get_user_builds_endpoint(
    target_user_id: int,
    user_id: int = Depends(get_current_user)
):
    """
    Получает публичные билды указанного пользователя.
    
    Args:
        target_user_id: ID пользователя, чьи билды нужно получить
        user_id: ID текущего пользователя (из dependency, для проверки авторизации)
    
    Returns:
        JSON со списком публичных билдов пользователя
    """
    from db import get_user_builds as db_get_user_builds
    all_builds = db_get_user_builds(DB_PATH, target_user_id)
    
    # Фильтруем только публичные билды
    public_builds = [build for build in all_builds if build.get('is_public') == 1]
    
    return {
        "status": "ok",
        "builds": public_builds
    }


@app.post("/api/builds.togglePublish")
async def toggle_build_publish(
    user_id: int = Depends(get_current_user),
    build_id: int = Form(...),
    is_public: int = Form(...)
):
    """
    Переключает публичность билда.
    """
    # Валидация is_public
    if is_public not in (0, 1):
        raise HTTPException(
            status_code=400,
            detail="is_public должен быть 0 или 1"
        )
    
    success = update_build_visibility(DB_PATH, build_id, user_id, is_public)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Билд не найден или у вас нет прав на его изменение"
        )
    
    return {
        "status": "ok",
        "message": "Видимость билда обновлена"
    }


@app.delete("/api/builds.delete")
async def delete_build_endpoint(
    build_id: int,
    user_id: int = Depends(get_current_user)
):
    """
    Удаляет билд и папку с изображениями.
    """
    # Удаляем из БД
    success = delete_build(DB_PATH, build_id, user_id)
    
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Билд не найден или у вас нет прав на его удаление"
        )
    
    # Удаляем папку с изображениями
    builds_dir = os.path.join(os.path.dirname(DB_PATH), 'builds', str(build_id))
    if os.path.exists(builds_dir):
        try:
            shutil.rmtree(builds_dir)
        except Exception as e:
            print(f"Ошибка удаления папки билда: {e}")
    
    return {
        "status": "ok",
        "message": "Билд успешно удален"
    }


@app.post("/api/builds.update")
async def update_build_endpoint(
    user_id: int = Depends(get_current_user),
    build_id: int = Form(...),
    name: str = Form(...),
    class_name: str = Form(...),
    tags: str = Form(...),  # JSON строка
    description: str = Form(""),
    photo_1: Optional[UploadFile] = File(None),
    photo_2: Optional[UploadFile] = File(None)
):
    """
    Обновляет существующий билд.
    """
    print(f"🔧 Обновление билда {build_id}, пользователь {user_id}")
    print(f"📋 Полученные параметры: name={name[:20]}..., class={class_name}, photo_1={photo_1 is not None}, photo_2={photo_2 is not None}")
    
    # Проверяем что билд существует и принадлежит пользователю
    build = get_build(DB_PATH, build_id)
    if not build:
        raise HTTPException(
            status_code=404,
            detail="Билд не найден"
        )
    
    if build['user_id'] != user_id:
        raise HTTPException(
            status_code=403,
            detail="У вас нет прав на изменение этого билда"
        )
    
    # Валидация данных
    if not name or not name.strip():
        raise HTTPException(
            status_code=400,
            detail="Название билда обязательно"
        )
    
    if not class_name or not class_name.strip():
        raise HTTPException(
            status_code=400,
            detail="Класс обязателен"
        )
    
    # Парсим теги
    try:
        import json
        if tags.startswith('[') and tags.endswith(']'):
            tags_list = json.loads(tags)
        else:
            tags_list = [t.strip() for t in tags.split(',') if t.strip()]
    except:
        tags_list = [t.strip() for t in tags.split(',') if t.strip()] if tags else []
    
    # Подготавливаем данные для обновления
    build_data = {
        'name': name.strip(),
        'class': class_name.strip(),
        'tags': tags_list,
        'description': description.strip()
    }
    
    # Обрабатываем изображения только если они переданы
    builds_dir = os.path.join(os.path.dirname(DB_PATH), 'builds', str(build_id))
    os.makedirs(builds_dir, exist_ok=True)
    
    # Проверяем наличие файлов
    if photo_1:
        try:
            # Читаем содержимое файла для проверки
            photo_1.file.seek(0)
            file_content = photo_1.file.read()
            photo_1.file.seek(0)
            
            if len(file_content) > 0:
                photo_1_path = os.path.join(builds_dir, 'photo_1.jpg')
                image1 = Image.open(photo_1.file)
                image1 = ImageOps.exif_transpose(image1)
                if image1.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', image1.size, (255, 255, 255))
                    if image1.mode == 'P':
                        image1 = image1.convert('RGBA')
                    background.paste(image1, mask=image1.split()[-1] if image1.mode == 'RGBA' else None)
                    image1 = background
                image1.save(photo_1_path, 'JPEG', quality=85, optimize=True)
                build_data['photo_1'] = f"/builds/{build_id}/photo_1.jpg"
                print(f"✅ Обновлено фото 1 для билда {build_id}, размер: {len(file_content)} байт")
            else:
                print(f"⚠️ Фото 1 пустое для билда {build_id}")
        except Exception as e:
            print(f"❌ Ошибка обработки первого изображения для билда {build_id}: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка обработки первого изображения: {str(e)}"
            )
    
    if photo_2:
        try:
            # Читаем содержимое файла для проверки
            photo_2.file.seek(0)
            file_content = photo_2.file.read()
            photo_2.file.seek(0)
            
            if len(file_content) > 0:
                photo_2_path = os.path.join(builds_dir, 'photo_2.jpg')
                image2 = Image.open(photo_2.file)
                image2 = ImageOps.exif_transpose(image2)
                if image2.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', image2.size, (255, 255, 255))
                    if image2.mode == 'P':
                        image2 = image2.convert('RGBA')
                    background.paste(image2, mask=image2.split()[-1] if image2.mode == 'RGBA' else None)
                    image2 = background
                image2.save(photo_2_path, 'JPEG', quality=85, optimize=True)
                build_data['photo_2'] = f"/builds/{build_id}/photo_2.jpg"
                print(f"✅ Обновлено фото 2 для билда {build_id}, размер: {len(file_content)} байт")
            else:
                print(f"⚠️ Фото 2 пустое для билда {build_id}")
        except Exception as e:
            print(f"❌ Ошибка обработки второго изображения для билда {build_id}: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка обработки второго изображения: {str(e)}"
            )
    
    print(f"📝 Данные для обновления билда {build_id}: {list(build_data.keys())}")
    
    # Обновляем билд в БД
    success = update_build(DB_PATH, build_id, user_id, build_data)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Ошибка обновления билда"
        )
    
    return {
        "status": "ok",
        "message": "Билд успешно обновлен",
        "build_id": build_id
    }


@app.get("/builds/{build_id}/{photo_name}")
async def get_build_photo(build_id: int, photo_name: str):
    """
    Возвращает изображение билда.
    """
    photo_path = os.path.join(os.path.dirname(DB_PATH), 'builds', str(build_id), photo_name)
    
    if not os.path.exists(photo_path):
        raise HTTPException(
            status_code=404,
            detail="Изображение не найдено"
        )
    
    return FileResponse(photo_path, media_type='image/jpeg')


@app.post("/api/comments.create")
async def create_comment_endpoint(
    user_id: int = Depends(get_current_user),
    build_id: int = Form(...),
    comment_text: str = Form(...)
):
    """
    Создает новый комментарий к билду.
    
    Args:
        user_id: ID текущего пользователя (из dependency)
        build_id: ID билда, к которому добавляется комментарий
        comment_text: Текст комментария (максимум 500 символов)
    
    Returns:
        JSON с информацией о созданном комментарии
    """
    # Проверяем, что билд существует
    build = get_build(DB_PATH, build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Билд не найден")
    
    # Валидация комментария
    comment_text = comment_text.strip()
    if len(comment_text) == 0:
        raise HTTPException(status_code=400, detail="Комментарий не может быть пустым")
    
    if len(comment_text) > 500:
        raise HTTPException(status_code=400, detail="Комментарий слишком длинный (максимум 500 символов)")
    
    # Создаем комментарий
    comment_id = create_comment(DB_PATH, build_id, user_id, comment_text)
    
    if not comment_id:
        raise HTTPException(status_code=500, detail="Ошибка создания комментария")
    
    return {
        "status": "ok",
        "comment_id": comment_id,
        "message": "Комментарий успешно создан"
    }


@app.get("/api/comments.get")
async def get_comments_endpoint(build_id: int):
    """
    Получает все комментарии для билда.
    
    Args:
        build_id: ID билда
    
    Returns:
        JSON со списком комментариев
    """
    # Проверяем, что билд существует
    build = get_build(DB_PATH, build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Билд не найден")
    
    comments = get_build_comments(DB_PATH, build_id)
    
    return {
        "status": "ok",
        "comments": comments
    }


    # Удалён функционал информации о трофеях

@app.get("/api/user_info/{user_id}")
async def get_user_info(user_id: int):
    """Получает информацию о пользователе по ID"""
    try:
        user = get_user(DB_PATH, user_id)
        if user:
            return user
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=404, detail="User not found")

# ========== API ЭНДПОИНТЫ ДЛЯ ТРОФЕЕВ ==========

# Удалены эндпоинты отправки заявок на трофеи


# Удалён эндпоинт одобрения трофея


@app.post("/api/feedback.submit")
async def submit_feedback(
    user_id: int = Depends(get_current_user),
    description: str = Form(...),
    photos: Optional[List[UploadFile]] = File(default=None)
):
    """
    Отправляет отзыв/баг-репорт в админскую группу.
    """
    # Получаем профиль пользователя для получения psn_id
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(
            status_code=404,
            detail="Профиль пользователя не найден"
        )
    
    psn_id = user_profile.get('psn_id', '')
    if not psn_id:
        raise HTTPException(
            status_code=400,
            detail="PSN ID не указан в профиле"
        )
    
    # Валидация описания
    if not description or not description.strip():
        raise HTTPException(
            status_code=400,
            detail="Описание обязательно"
        )
    
    # Валидация количества фото
    if photos and len(photos) > 10:
        raise HTTPException(
            status_code=400,
            detail="Можно прикрепить не более 10 изображений"
        )
    
    # Проверяем что все файлы - изображения
    if photos:
        for photo in photos:
            if not photo.content_type or not photo.content_type.startswith('image/'):
                raise HTTPException(
                    status_code=400,
                    detail="Разрешены только изображения"
                )
    
    # Создаем временную директорию для фотографий
    temp_dir = None
    photo_paths = []
    
    try:
        if photos and len(photos) > 0:
            temp_dir = tempfile.mkdtemp(prefix='feedback_')
            
            # Обрабатываем и сохраняем изображения
            for i, photo in enumerate(photos):
                photo_path = os.path.join(temp_dir, f'photo_{i+1}.jpg')
                
                # Открываем изображение через Pillow
                image = Image.open(photo.file)
                
                # Исправляем ориентацию согласно EXIF-метаданным
                image = ImageOps.exif_transpose(image)
                
                # Конвертируем в RGB если нужно
                if image.mode in ('RGBA', 'LA', 'P'):
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    if image.mode == 'P':
                        image = image.convert('RGBA')
                    background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = background
                
                # Сохраняем как JPEG
                image.save(photo_path, 'JPEG', quality=85, optimize=True)
                photo_paths.append(photo_path)
                
                # Возвращаем курсор файла
                photo.file.seek(0)
    
    except Exception as e:
        # Удаляем временную директорию при ошибке
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки изображений: {str(e)}"
        )
    
    # Формируем сообщение для группы
    message_text = f"""💬 <b>Новый отзыв/баг-репорт</b>

👤 <b>Пользователь:</b> {psn_id}

💬 <b>Описание:</b>
{description.strip()}
"""
    
    # Отправляем уведомление в группу БЕЗ message_thread_id (в основную тему)
    try:
        if len(photo_paths) == 1:
            # Одна фотография - отправляем как фото с подписью
            await send_telegram_photo(
                chat_id=TROPHY_GROUP_CHAT_ID,
                photo_path=photo_paths[0],
                caption=message_text
            )
        elif len(photo_paths) > 1:
            # Несколько фотографий - сначала текст, потом медиагруппа
            await send_telegram_message(
                chat_id=TROPHY_GROUP_CHAT_ID,
                text=message_text
            )
            
            # Затем отправляем медиагруппу с фото
            await send_telegram_media_group(
                chat_id=TROPHY_GROUP_CHAT_ID,
                photo_paths=photo_paths
            )
        else:
            # Нет фотографий - только текстовое сообщение
            await send_telegram_message(
                chat_id=TROPHY_GROUP_CHAT_ID,
                text=message_text
            )
    
    except Exception as e:
        print(f"Ошибка отправки отзыва в группу: {e}")
        # Не прерываем выполнение, но логируем ошибку
    
    finally:
        # Удаляем временную директорию
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Ошибка удаления временной директории: {e}")
    
    return {
        "status": "ok",
        "message": "Отзыв успешно отправлен"
    }


# Удалён эндпоинт отклонения трофея


# Удалён роут изображений заявок на трофеи


# ========== API ЭНДПОИНТЫ ДЛЯ МАСТЕРСТВА ==========

@app.get("/api/mastery.get")
async def get_mastery_levels(user_id: int = Depends(get_current_user)):
    """
    Получает уровни мастерства текущего пользователя.
    
    Returns:
        Словарь с уровнями по категориям: {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0}
    """
    try:
        mastery = get_mastery(DB_PATH, user_id)
        return mastery
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения уровней мастерства: {str(e)}"
        )


# Импортируем функцию загрузки конфига из отдельного модуля
from mastery_config import load_mastery_config


@app.post("/api/mastery.submitApplication")
async def submit_mastery_application(
    user_id: int = Depends(get_current_user),
    category_key: str = Form(...),
    current_level: int = Form(...),
    next_level: int = Form(...),
    comment: Optional[str] = Form(default=None),
    photos: Optional[List[UploadFile]] = File(default=None)
):
    """
    Отправляет заявку на повышение уровня мастерства в админскую группу.
    """
    # Получаем профиль пользователя для получения psn_id
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(
            status_code=404,
            detail="Профиль пользователя не найден"
        )
    
    psn_id = user_profile.get('psn_id', '')
    if not psn_id:
        raise HTTPException(
            status_code=400,
            detail="PSN ID не указан в профиле"
        )
    
    # Загружаем конфиг мастерства
    try:
        config = load_mastery_config()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка загрузки конфига мастерства: {str(e)}"
        )
    
    # Находим категорию в конфиге
    category = None
    for cat in config.get('categories', []):
        if cat.get('key') == category_key:
            category = cat
            break
    
    if not category:
        raise HTTPException(
            status_code=400,
            detail=f"Категория {category_key} не найдена в конфиге"
        )
    
    max_levels = category.get('maxLevels', 0)
    
    # Валидация
    if photos is None or len(photos) == 0:
        raise HTTPException(
            status_code=400,
            detail="Необходимо прикрепить хотя бы одно изображение"
        )
    
    if len(photos) > 9:
        raise HTTPException(
            status_code=400,
            detail="Можно прикрепить не более 9 изображений"
        )
    
    # Проверяем что все файлы - изображения
    for photo in photos:
        if not photo.content_type or not photo.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Разрешены только изображения"
            )
    
    # Валидация уровней
    if next_level != current_level + 1:
        raise HTTPException(
            status_code=400,
            detail=f"Следующий уровень должен быть {current_level + 1}, получен {next_level}"
        )
    
    if current_level >= max_levels:
        raise HTTPException(
            status_code=400,
            detail="Текущий уровень уже максимальный"
        )
    
    # Получаем информацию об уровнях из конфига
    current_level_data = None
    next_level_data = None
    
    for level in category.get('levels', []):
        if level.get('level') == current_level:
            current_level_data = level
        if level.get('level') == next_level:
            next_level_data = level
    
    if not next_level_data:
        raise HTTPException(
            status_code=400,
            detail=f"Уровень {next_level} не найден в конфиге для категории {category_key}"
        )
    
    # Создаем временную директорию для фотографий
    temp_dir = None
    photo_paths = []
    
    try:
        temp_dir = tempfile.mkdtemp(prefix='mastery_app_')
        
        # Обрабатываем и сохраняем изображения
        for i, photo in enumerate(photos):
            photo_path = os.path.join(temp_dir, f'photo_{i+1}.jpg')
            
            # Открываем изображение через Pillow
            image = Image.open(photo.file)
            
            # Исправляем ориентацию согласно EXIF-метаданным
            image = ImageOps.exif_transpose(image)
            
            # Конвертируем в RGB если нужно
            if image.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            
            # Сохраняем как JPEG
            image.save(photo_path, 'JPEG', quality=85, optimize=True)
            photo_paths.append(photo_path)
            
            # Возвращаем курсор файла
            photo.file.seek(0)
    
    except Exception as e:
        # Удаляем временную директорию при ошибке
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки изображений: {str(e)}"
        )
    
    # Формируем сообщение для группы
    current_level_name = current_level_data.get('name', f'Уровень {current_level}') if current_level_data else f'Уровень {current_level}'
    next_level_name = next_level_data.get('name', f'Уровень {next_level}')
    next_level_description = next_level_data.get('description', '')
    next_level_proof = next_level_data.get('proof', '')
    category_name = category.get('name', category_key)
    
    comment_text = comment.strip() if comment and comment.strip() else "Без комментария"
    
    message_text = f"""🏆 <b>Заявка на повышение уровня</b>

👤 <b>PSN ID:</b> {psn_id}
📂 <b>Категория:</b> {category_name}
📊 <b>Текущий уровень:</b> Уровень {current_level} — {current_level_name}
⬆️ <b>Запрашиваемый уровень:</b> Уровень {next_level} — {next_level_name}
📝 <b>Описание уровня:</b>
{next_level_description}

📸 <b>Требуемые доказательства:</b>
{next_level_proof}

💬 <b>Комментарий:</b> {comment_text}"""
    
    # Создаем inline кнопки
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "Одобрить",
                    "callback_data": f"approve_mastery:{user_id}:{category_key}:{next_level}"
                },
                {
                    "text": "Отклонить",
                    "callback_data": f"reject_mastery:{user_id}:{category_key}:{next_level}"
                }
            ]
        ]
    }
    
    # Отправляем уведомление в группу с message_thread_id (в отдельную тему)
    try:
        if len(photo_paths) == 1:
            # Одна фотография - отправляем как фото с подписью и кнопками
            await send_telegram_photo(
                chat_id=TROPHY_GROUP_CHAT_ID,
                photo_path=photo_paths[0],
                caption=message_text,
                reply_markup=reply_markup,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
        else:
            # Несколько фотографий - сначала текст с кнопками, потом медиагруппа
            await send_telegram_message(
                chat_id=TROPHY_GROUP_CHAT_ID,
                text=message_text,
                reply_markup=reply_markup,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
            
            # Затем отправляем медиагруппу с фото
            await send_telegram_media_group(
                chat_id=TROPHY_GROUP_CHAT_ID,
                photo_paths=photo_paths,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
    
    except Exception as e:
        print(f"Ошибка отправки заявки в группу: {e}")
        # Не прерываем выполнение, но логируем ошибку
    
    finally:
        # Удаляем временную директорию
        if temp_dir and os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"Ошибка удаления временной директории: {e}")
    
    return {
        "status": "ok",
        "message": "Заявка успешно отправлена"
    }


# ========== API ENDPOINTS ДЛЯ ОБРАБОТКИ ЗАЯВОК (вызываются ботом) ==========

def verify_bot_authorization(authorization: Optional[str] = Header(None)) -> bool:
    """
    Проверяет авторизацию бота для внутренних endpoints.
    Бот должен передать BOT_TOKEN в заголовке Authorization.
    """
    if not authorization:
        return False
    # Формат: "Bearer {BOT_TOKEN}" или просто "{BOT_TOKEN}"
    token = authorization.replace("Bearer ", "").strip()
    return token == BOT_TOKEN


@app.post("/api/mastery.approve")
async def approve_mastery_application(
    user_id: int = Form(...),
    category_key: str = Form(...),
    next_level: int = Form(...),
    moderator_username: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    """
    Одобряет заявку на повышение уровня мастерства.
    Вызывается ботом при нажатии кнопки "Одобрить".
    """
    # Проверка авторизации бота
    if not verify_bot_authorization(authorization):
        raise HTTPException(status_code=401, detail="Неавторизованный запрос")
    
    # Импортируем функции для работы с БД
    from db import set_mastery, get_user, get_mastery
    
    # Получаем текущий уровень пользователя из БД
    mastery_data = get_mastery(DB_PATH, user_id)
    current_level = mastery_data.get(category_key, 0)
    
    # Проверяем, что next_level действительно current_level + 1
    expected_next_level = current_level + 1
    if next_level != expected_next_level:
        raise HTTPException(
            status_code=400,
            detail=f"Несоответствие уровней: текущий {current_level}, переданный next_level {next_level}, ожидаемый {expected_next_level}"
        )
    
    # Обновляем уровень в БД (записываем current_level + 1)
    new_level = current_level + 1
    success = set_mastery(DB_PATH, user_id, category_key, new_level)
    if not success:
        raise HTTPException(status_code=500, detail="Ошибка обновления уровня в БД")
    
    # Получаем информацию о пользователе
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(status_code=404, detail="Профиль пользователя не найден")
    
    psn_id = user_profile.get('psn_id', '')
    username = user_profile.get('real_name', '')
    
    # Загружаем конфиг для получения названий
    try:
        config = load_mastery_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки конфига: {str(e)}")
    
    # Находим категорию и уровень в конфиге
    category = None
    level_data = None
    for cat in config.get('categories', []):
        if cat.get('key') == category_key:
            category = cat
            for level in cat.get('levels', []):
                if level.get('level') == next_level:
                    level_data = level
                    break
            break
    
    category_name = category.get('name', category_key) if category else category_key
    level_name = level_data.get('name', f'Уровень {next_level}') if level_data else f'Уровень {next_level}'
    
    # Отправляем уведомление пользователю в личку с полной информацией
    try:
        user_notification = f"""✅ <b>Ваша заявка на повышение уровня мастерства была одобрена!</b>

Категория: <b>{category_name}</b>
Запрашиваемый уровень: Уровень {next_level} — {level_name}

📊 <b>Текущий уровень:</b> Уровень {next_level} — {level_name}"""
        
        await send_telegram_message(
            chat_id=str(user_id),
            text=user_notification
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    # Отправляем сообщение в группу поздравлений (если указан в .env)
    # Но CONGRATULATIONS_CHAT_ID теперь не в API, нужно передать его боту или вернуть в ответе
    # Пока пропускаем, бот сам отправит
    
    return {
        "status": "ok",
        "success": True,
        "category_name": category_name,
        "level_name": level_name,
        "psn_id": psn_id,
        "username": username,
        "user_id": user_id
    }


@app.post("/api/mastery.reject")
async def reject_mastery_application(
    user_id: int = Form(...),
    category_key: str = Form(...),
    next_level: int = Form(...),
    reason: str = Form(...),
    moderator_username: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    """
    Отклоняет заявку на повышение уровня мастерства.
    Вызывается ботом после получения причины отклонения от модератора.
    """
    # Проверка авторизации бота
    if not verify_bot_authorization(authorization):
        raise HTTPException(status_code=401, detail="Неавторизованный запрос")
    
    # Импортируем функции для работы с БД
    from db import get_user
    
    # Получаем информацию о пользователе
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(status_code=404, detail="Профиль пользователя не найден")
    
    # Загружаем конфиг для получения названий
    try:
        config = load_mastery_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки конфига: {str(e)}")
    
    # Находим категорию и уровень в конфиге
    category = None
    level_data = None
    for cat in config.get('categories', []):
        if cat.get('key') == category_key:
            category = cat
            for level in cat.get('levels', []):
                if level.get('level') == next_level:
                    level_data = level
                    break
            break
    
    category_name = category.get('name', category_key) if category else category_key
    level_name = level_data.get('name', f'Уровень {next_level}') if level_data else f'Уровень {next_level}'
    
    # Отправляем уведомление пользователю в личку с полной информацией
    try:
        user_notification = f"""❌ <b>К сожалению, ваша заявка на повышение уровня мастерства была отклонена.</b>

Категория: <b>{category_name}</b>
Запрашиваемый уровень: Уровень {next_level} — {level_name}

Причина: {reason}"""
        
        await send_telegram_message(
            chat_id=str(user_id),
            text=user_notification
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    return {
        "status": "ok",
        "success": True,
        "category_name": category_name,
        "level_name": level_name
    }


# Обработчик ошибок для CORS
@app.exception_handler(HTTPException)
async def cors_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    print("🚀 Запуск Tsushima Mini App API...")
    print(f"📁 База данных: {DB_PATH}")
    print(f"🌐 Разрешенный origin: {ALLOWED_ORIGIN}")
    print(f"🤖 Bot token: {BOT_TOKEN[:10]}..." if BOT_TOKEN else "❌ Bot token не найден")
    
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
