# app.py
# FastAPI приложение для Tsushima Mini App API
# Проверка пуша на GitHub

import os
import uvicorn
import shutil
import json
import time
import requests
from fastapi import FastAPI, HTTPException, Depends, Header, Form, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from PIL import Image, ImageOps
import re

# Импортируем наши модули
from security import validate_init_data, get_user_id_from_init_data
from db import init_db, get_user, upsert_user, create_build, get_build, get_user_builds, update_build_visibility, delete_build, add_trophy_to_user, get_all_users

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
DB_PATH = os.getenv("DB_PATH", "/home/ubuntu/miniapp_api/app.db")

# Переменные для системы трофеев
TROPHY_GROUP_CHAT_ID = os.getenv("TROPHY_GROUP_CHAT_ID", "-1002348168326")
TROPHY_GROUP_TOPIC_ID = os.getenv("TROPHY_GROUP_TOPIC_ID", "5675")
BOT_USERNAME = os.getenv("BOT_USERNAME", "swiezdo_testbot")

# Кеш для данных трофеев
_trophies_cache: Dict[str, Any] = {}
_trophies_cache_time: float = 0
CACHE_TTL = 3600  # 1 час

def load_trophies_data() -> Dict[str, Any]:
    """
    Загружает данные трофеев с фронтенда с кешированием.
    """
    global _trophies_cache, _trophies_cache_time
    
    current_time = time.time()
    
    # Проверяем кеш
    if _trophies_cache and (current_time - _trophies_cache_time) < CACHE_TTL:
        return _trophies_cache
    
    # Загружаем с фронтенда
    try:
        frontend_url = os.getenv('FRONTEND_URL', ALLOWED_ORIGIN)
        trophies_url = f"{frontend_url}/docs/assets/data/trophies.json"
        
        response = requests.get(trophies_url, timeout=10)
        response.raise_for_status()
        
        _trophies_cache = response.json()
        _trophies_cache_time = current_time
        
        return _trophies_cache
    except Exception as e:
        print(f"Ошибка загрузки данных трофея с URL: {e}")
        
        # Если есть старый кеш, используем его
        if _trophies_cache:
            return _trophies_cache
        
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные трофеев")

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

# Настройка CORS (временно разрешаем все origins для тестирования)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Временно разрешаем все origins
    allow_credentials=False,  # Отключаем credentials для тестирования
    allow_methods=["*"],
    allow_headers=["*"],
)

# Инициализируем базу данных при запуске
init_db(DB_PATH)

# Глобальный обработчик OPTIONS запросов
@app.options("/{path:path}")
async def options_handler(path: str):
    """
    Глобальный обработчик OPTIONS запросов для CORS.
    """
    print(f"🔍 Глобальный OPTIONS запрос для пути: /{path}")
    from fastapi.responses import Response
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",  # Временно разрешаем все origins
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "false",
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
        "real_name": profile.get("real_name", ""),
        "psn_id": profile.get("psn_id", ""),
        "platforms": profile.get("platforms", []),
        "modes": profile.get("modes", []),
        "goals": profile.get("goals", []),
        "difficulties": profile.get("difficulties", []),
        "trophies": profile.get("trophies", [])
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
        JSON со списком пользователей (user_id и psn_id)
    """
    users = get_all_users(DB_PATH)
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
        "trophies": profile.get("trophies", [])
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
    
    # Парсим теги (строка через запятую)
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


@app.get("/api/trophy_info/{trophy_id}")
async def get_trophy_info(trophy_id: str):
    """Получает информацию о трофее по ID"""
    try:
        trophies_data = load_trophies_data()
        trophy_info = trophies_data.get(trophy_id, {})
        return {
            "name": trophy_info.get('name', trophy_id),
            "emoji": trophy_info.get('emoji', '🏆')
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail="Trophy not found")

@app.get("/api/user_info/{user_id}")
async def get_user_info(user_id: int):
    """Получает информацию о пользователе по ID"""
    try:
        user = get_user(DB_PATH, user_id)
        if user:
            return {"psn_id": user.get('psn_id', str(user_id))}
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=404, detail="User not found")

# ========== API ЭНДПОИНТЫ ДЛЯ ТРОФЕЕВ ==========

@app.post("/api/trophies.submit")
async def submit_trophy_application(
    user_id: int = Depends(get_current_user),
    trophy_id: str = Form(...),
    comment: str = Form(""),
    photos: List[UploadFile] = File(...)
):
    """
    Отправляет заявку на получение трофея.
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
    
    # Валидация trophy_id
    if not trophy_id or not trophy_id.strip():
        raise HTTPException(
            status_code=400,
            detail="ID трофея обязателен"
        )
    
    # Валидация количества фото
    if not photos or len(photos) == 0:
        raise HTTPException(
            status_code=400,
            detail="Необходимо прикрепить хотя бы одно изображение"
        )
    
    if len(photos) > 10:
        raise HTTPException(
            status_code=400,
            detail="Можно прикрепить не более 10 изображений"
        )
    
    # Проверяем что все файлы - изображения
    for photo in photos:
        if not photo.content_type or not photo.content_type.startswith('image/'):
            raise HTTPException(
                status_code=400,
                detail="Разрешены только изображения"
            )
    
    # Создаем директорию для заявки
    trophies_dir = os.path.join(os.path.dirname(DB_PATH), 'trophies', str(user_id), trophy_id)
    os.makedirs(trophies_dir, exist_ok=True)
    
    # Обрабатываем и сохраняем изображения
    photo_paths = []
    try:
        for i, photo in enumerate(photos):
            photo_path = os.path.join(trophies_dir, f'photo_{i+1}.jpg')
            
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
        # Удаляем папку при ошибке
        if os.path.exists(trophies_dir):
            shutil.rmtree(trophies_dir)
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки изображений: {str(e)}"
        )
    
    # Загружаем данные трофея из фронтенда
    try:
        trophies_data = load_trophies_data()
        trophy_info = trophies_data.get(trophy_id, {})
        trophy_name = trophy_info.get('name', trophy_id)
        trophy_emoji = trophy_info.get('emoji', '🏆')
        trophy_description = trophy_info.get('description', [])
        
    except Exception as e:
        print(f"Ошибка загрузки данных трофея: {e}")
        trophy_name = trophy_id
        trophy_emoji = '🏆'
        trophy_description = []
    
    # Формируем сообщение для группы
    message_text = f"""🏆 <b>Новая заявка на трофей</b>

👤 <b>Пользователь:</b> {psn_id}
🏆 <b>Трофей:</b> {trophy_name} {trophy_emoji}

📝 <b>Описание трофея:</b>
"""
    
    for desc_line in trophy_description:
        message_text += f"• {desc_line}\n"
    
    if comment.strip():
        message_text += f"\n💬 <b>Комментарий:</b>\n{comment.strip()}"
    
    # Создаем inline кнопки
    reply_markup = {
        "inline_keyboard": [[
            {
                "text": "✅ Одобрить",
                "callback_data": f"trophy_approve:{user_id}:{trophy_id}"
            },
            {
                "text": "❌ Отклонить", 
                "callback_data": f"trophy_reject:{user_id}:{trophy_id}"
            }
        ]]
    }
    
    # Отправляем уведомление в группу
    try:
        if len(photo_paths) == 1:
            # Одна фотография - отправляем как фото с подписью
            await send_telegram_photo(
                chat_id=TROPHY_GROUP_CHAT_ID,
                photo_path=photo_paths[0],
                caption=message_text,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
            
            # Отправляем отдельное сообщение с кнопками
            await send_telegram_message(
                chat_id=TROPHY_GROUP_CHAT_ID,
                text=f"Заявка от {psn_id} на трофей {trophy_name} {trophy_emoji}",
                reply_markup=reply_markup,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
        else:
            # Отправляем сначала текстовое сообщение с полным описанием
            await send_telegram_message(
                chat_id=TROPHY_GROUP_CHAT_ID,
                text=message_text,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
            
            # Затем отправляем медиагруппу с фото
            await send_telegram_media_group(
                chat_id=TROPHY_GROUP_CHAT_ID,
                photo_paths=photo_paths,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
            
            # И отдельное сообщение с кнопками
            await send_telegram_message(
                chat_id=TROPHY_GROUP_CHAT_ID,
                text=f"Заявка от {psn_id} на трофей {trophy_name} {trophy_emoji}",
                reply_markup=reply_markup,
                message_thread_id=TROPHY_GROUP_TOPIC_ID
            )
    
    except Exception as e:
        print(f"Ошибка отправки уведомления в группу: {e}")
        # Не прерываем выполнение, заявка уже сохранена
    
    return {
        "status": "ok",
        "message": "Заявка на трофей успешно отправлена"
    }


@app.post("/api/trophies.approve")
async def approve_trophy_application(
    user_id: int = Form(...),
    trophy_id: str = Form(...)
):
    """
    Одобряет заявку на трофей (вызывается ботом).
    """
    # Добавляем трофей пользователю
    success = add_trophy_to_user(DB_PATH, user_id, trophy_id)
    
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Ошибка добавления трофея пользователю"
        )
    
    # Удаляем папку с заявкой
    trophies_dir = os.path.join(os.path.dirname(DB_PATH), 'trophies', str(user_id), trophy_id)
    if os.path.exists(trophies_dir):
        try:
            shutil.rmtree(trophies_dir)
        except Exception as e:
            print(f"Ошибка удаления папки заявки: {e}")
    
    # Загружаем данные трофея для уведомления
    try:
        trophies_data = load_trophies_data()
        trophy_info = trophies_data.get(trophy_id, {})
        trophy_name = trophy_info.get('name', trophy_id)
        trophy_emoji = trophy_info.get('emoji', '🏆')
        
    except Exception as e:
        print(f"Ошибка загрузки данных трофея: {e}")
        trophy_name = trophy_id
        trophy_emoji = '🏆'
    
    # Отправляем уведомление пользователю
    message_text = f"""🎉 <b>Поздравляем!</b>

Вы получили трофей <b>{trophy_name}</b> {trophy_emoji}

Можете посмотреть его в мини-приложении Tsushima.Ru"""
    
    # Создаем кнопку для открытия мини-приложения
    reply_markup = {
        "inline_keyboard": [[
            {
                "text": "🏆 Открыть приложение",
                "url": f"https://t.me/{BOT_USERNAME}?startapp=command&mode=fullscreen"
            }
        ]]
    }
    
    try:
        await send_telegram_message(
            chat_id=str(user_id),
            text=message_text,
            reply_markup=reply_markup
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю: {e}")
    
    return {
        "status": "ok",
        "message": "Трофей успешно одобрен"
    }


@app.post("/api/trophies.reject")
async def reject_trophy_application(
    user_id: int = Form(...),
    trophy_id: str = Form(...)
):
    """
    Отклоняет заявку на трофей (вызывается ботом).
    """
    # Удаляем папку с заявкой
    trophies_dir = os.path.join(os.path.dirname(DB_PATH), 'trophies', str(user_id), trophy_id)
    if os.path.exists(trophies_dir):
        try:
            shutil.rmtree(trophies_dir)
        except Exception as e:
            print(f"Ошибка удаления папки заявки: {e}")
    
    # Загружаем данные трофея для уведомления
    try:
        trophies_data = load_trophies_data()
        trophy_info = trophies_data.get(trophy_id, {})
        trophy_name = trophy_info.get('name', trophy_id)
        trophy_emoji = trophy_info.get('emoji', '🏆')
        
    except Exception as e:
        print(f"Ошибка загрузки данных трофея: {e}")
        trophy_name = trophy_id
        trophy_emoji = '🏆'
    
    # Отправляем уведомление пользователю
    message_text = f"""❌ <b>Заявка отклонена</b>

Ваша заявка на трофей <b>{trophy_name}</b> {trophy_emoji} была отклонена.

Попробуйте подать заявку снова с более качественными доказательствами."""
    
    try:
        await send_telegram_message(
            chat_id=str(user_id),
            text=message_text
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю: {e}")
    
    return {
        "status": "ok",
        "message": "Заявка на трофей отклонена"
    }


@app.get("/trophies/{user_id}/{trophy_id}/{photo_name}")
async def get_trophy_photo(user_id: int, trophy_id: str, photo_name: str):
    """
    Возвращает изображение заявки на трофей.
    """
    photo_path = os.path.join(os.path.dirname(DB_PATH), 'trophies', str(user_id), trophy_id, photo_name)
    
    if not os.path.exists(photo_path):
        raise HTTPException(
            status_code=404,
            detail="Изображение не найдено"
        )
    
    return FileResponse(photo_path, media_type='image/jpeg')


# Обработчик ошибок для CORS
@app.exception_handler(HTTPException)
async def cors_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Запуск приложения
if __name__ == "__main__":
    print("🚀 Запуск Tsushima Mini App API...")
    print(f"📁 База данных: {DB_PATH}")
    print(f"🌐 Разрешенный origin: {ALLOWED_ORIGIN}")
    print(f"🤖 Bot token: {BOT_TOKEN[:10]}..." if BOT_TOKEN else "❌ Bot token не найден")
    
    uvicorn.run(
        "app:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
        log_level="info"
    )
