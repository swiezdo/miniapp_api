# app.py
# FastAPI приложение для Tsushima Mini App API
# Проверка пуша на GitHub

import os
import shutil
import json
import requests
import tempfile
import sqlite3
import io
import traceback
import re
from fastapi import FastAPI, HTTPException, Depends, Header, Form, File, UploadFile, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from typing import Optional, List, Dict, Any
from PIL import Image
from playwright.async_api import async_playwright

# Импортируем наши модули
from security import validate_init_data, get_user_id_from_init_data
from db import init_db, get_user, upsert_user, create_build, get_build, get_user_builds, update_build_visibility, delete_build, update_build, get_all_users, get_mastery, create_comment, get_build_comments, toggle_reaction, get_reactions, update_avatar_url, update_build_photos
from image_utils import process_image_for_upload, process_avatar_image, validate_image_file, temp_image_directory
from telegram_utils import send_telegram_message, send_photos_to_telegram_group
from user_utils import get_user_with_psn, format_profile_response
from mastery_utils import find_category_by_key, parse_tags
from mastery_config import load_mastery_config

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
# Функции для работы с Telegram Bot API перенесены в telegram_utils.py

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

# Настраиваем статические файлы для ассетов (мастерство и другие)
tsushimaru_docs_path = "/root/tsushimaru_app/docs"
if os.path.exists(tsushimaru_docs_path):
    app.mount("/assets", StaticFiles(directory=tsushimaru_docs_path), name="assets")

# Удалена синхронизация трофеев при запуске

# Глобальный обработчик OPTIONS запросов
@app.options("/{path:path}")
async def options_handler(path: str, request: Request):
    """
    Глобальный обработчик OPTIONS запросов для CORS.
    """
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
# Дублирующиеся OPTIONS handlers удалены - используется глобальный handler


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
    return format_profile_response(profile, user_id)


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
    return format_profile_response(profile, target_user_id)


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
    if not validate_image_file(avatar):
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
        
        # Обрабатываем аватарку (обрезка, ресайз, конвертация)
        process_avatar_image(image, avatar_path)
        
        # Обновляем avatar_url в БД
        avatar_url = f"/users/{user_id}/avatar.jpg"
        update_avatar_url(DB_PATH, user_id, avatar_url)
        
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
    user_profile, author = get_user_with_psn(DB_PATH, user_id)
    
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
    
    # Парсим теги
    tags_list = parse_tags(tags)
    
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
        process_image_for_upload(image1, photo_1_path)
        photo_1.file.seek(0)  # Возвращаем курсор
        
        # Обработка второго изображения
        photo_2_path = os.path.join(builds_dir, 'photo_2.jpg')
        image2 = Image.open(photo_2.file)
        process_image_for_upload(image2, photo_2_path)
        
        # Обновляем пути к изображениям в БД
        photo_1_url = f"/builds/{build_id}/photo_1.jpg"
        photo_2_url = f"/builds/{build_id}/photo_2.jpg"
        
        # Обновляем билд с путями
        update_build_photos(DB_PATH, build_id, photo_1_url, photo_2_url)
        
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
    tags_list = parse_tags(tags)
    
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
    
    # Обрабатываем первое изображение если передано
    if photo_1:
        try:
            # Проверяем что файл не пустой (используем размер файла)
            photo_1.file.seek(0, 2)  # Переходим в конец файла
            file_size = photo_1.file.tell()
            photo_1.file.seek(0)  # Возвращаемся в начало
            
            if file_size > 0:
                photo_1_path = os.path.join(builds_dir, 'photo_1.jpg')
                image1 = Image.open(photo_1.file)
                process_image_for_upload(image1, photo_1_path)
                build_data['photo_1'] = f"/builds/{build_id}/photo_1.jpg"
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка обработки первого изображения: {str(e)}"
            )
    
    # Обрабатываем второе изображение если передано
    if photo_2:
        try:
            # Проверяем что файл не пустой (используем размер файла)
            photo_2.file.seek(0, 2)  # Переходим в конец файла
            file_size = photo_2.file.tell()
            photo_2.file.seek(0)  # Возвращаемся в начало
            
            if file_size > 0:
                photo_2_path = os.path.join(builds_dir, 'photo_2.jpg')
                image2 = Image.open(photo_2.file)
                process_image_for_upload(image2, photo_2_path)
                build_data['photo_2'] = f"/builds/{build_id}/photo_2.jpg"
        except Exception as e:
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка обработки второго изображения: {str(e)}"
            )
    
    
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


# ========== API ЭНДПОИНТЫ ДЛЯ РЕАКЦИЙ (ЛАЙКИ/ДИЗЛАЙКИ) ==========

@app.post("/api/builds.toggleReaction")
async def toggle_reaction_endpoint(
    user_id: int = Depends(get_current_user),
    build_id: int = Form(...),
    reaction_type: str = Form(...)
):
    """
    Переключает реакцию пользователя на билд (лайк/дизлайк).
    
    Args:
        user_id: ID текущего пользователя (из dependency)
        build_id: ID билда
        reaction_type: Тип реакции ('like' или 'dislike')
    
    Returns:
        JSON с обновленной статистикой реакций
    """
    # Проверяем, что билд существует
    build = get_build(DB_PATH, build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Билд не найден")
    
    # Проверяем, что билд публичный
    if not build.get('is_public'):
        raise HTTPException(status_code=403, detail="Реакции можно ставить только на публичные билды")
    
    # Валидация типа реакции
    if reaction_type not in ('like', 'dislike'):
        raise HTTPException(status_code=400, detail="reaction_type должен быть 'like' или 'dislike'")
    
    try:
        # Переключаем реакцию
        result = toggle_reaction(DB_PATH, build_id, user_id, reaction_type)
        
        return {
            "status": "ok",
            "likes_count": result['likes_count'],
            "dislikes_count": result['dislikes_count'],
            "current_user_reaction": result['current_user_reaction']
        }
    except Exception as e:
        print(f"Ошибка переключения реакции: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка переключения реакции: {str(e)}")


@app.get("/api/builds.getReactions/{build_id}")
async def get_reactions_endpoint(
    build_id: int,
    user_id: int = Depends(get_current_user)
):
    """
    Получает статистику реакций для билда и текущую реакцию пользователя.
    
    Args:
        build_id: ID билда
        user_id: ID текущего пользователя (из dependency)
    
    Returns:
        JSON со статистикой реакций
    """
    # Проверяем, что билд существует
    build = get_build(DB_PATH, build_id)
    if not build:
        raise HTTPException(status_code=404, detail="Билд не найден")
    
    try:
        # Получаем реакции
        result = get_reactions(DB_PATH, build_id, user_id)
        
        return {
            "status": "ok",
            "likes_count": result['likes_count'],
            "dislikes_count": result['dislikes_count'],
            "current_user_reaction": result['current_user_reaction']
        }
    except Exception as e:
        print(f"Ошибка получения реакций: {e}")
        raise HTTPException(status_code=500, detail=f"Ошибка получения реакций: {str(e)}")


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
    user_profile, psn_id = get_user_with_psn(DB_PATH, user_id)
    
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
            if not validate_image_file(photo):
                raise HTTPException(
                    status_code=400,
                    detail="Разрешены только изображения"
                )
    
    # Формируем сообщение для группы
    message_text = f"""💬 <b>Новый отзыв/баг-репорт</b>

👤 <b>Пользователь:</b> {psn_id}

💬 <b>Описание:</b>
{description.strip()}
"""
    
    # Обрабатываем и отправляем фотографии
    photo_paths = []
    try:
        if photos and len(photos) > 0:
            with temp_image_directory(prefix='feedback_') as temp_dir:
                # Обрабатываем и сохраняем изображения
                for i, photo in enumerate(photos):
                    photo_path = os.path.join(temp_dir, f'photo_{i+1}.jpg')
                    
                    # Открываем изображение через Pillow
                    image = Image.open(photo.file)
                    
                    # Обрабатываем изображение
                    process_image_for_upload(image, photo_path)
                    photo_paths.append(photo_path)
                    
                    # Возвращаем курсор файла
                    photo.file.seek(0)
                
                # Отправляем уведомление в группу БЕЗ message_thread_id (в основную тему)
                try:
                    await send_photos_to_telegram_group(
                        bot_token=BOT_TOKEN,
                        chat_id=TROPHY_GROUP_CHAT_ID,
                        photo_paths=photo_paths,
                        message_text=message_text
                    )
                except Exception as e:
                    print(f"Ошибка отправки отзыва в группу: {e}")
                    # Не прерываем выполнение, но логируем ошибку
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки изображений: {str(e)}"
        )
    
    return {
        "status": "ok",
        "message": "Отзыв успешно отправлен"
    }


# Удалён эндпоинт отклонения трофея


# Удалён роут изображений заявок на трофеи


# ========== API ЭНДПОИНТЫ ДЛЯ МАСТЕРСТВА ==========

@app.get("/api/mastery.get")
async def get_mastery_levels(
    target_user_id: Optional[int] = None,
    user_id: int = Depends(get_current_user)
):
    """
    Получает уровни мастерства пользователя.
    
    Args:
        target_user_id: ID пользователя, чьё мастерство нужно получить (если не указан, возвращает данные текущего пользователя)
        user_id: ID текущего пользователя (из dependency, для проверки авторизации)
    
    Returns:
        Словарь с уровнями по категориям: {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0}
    """
    try:
        # Если указан target_user_id, используем его, иначе берем текущего пользователя
        target_id = target_user_id if target_user_id is not None else user_id
        mastery = get_mastery(DB_PATH, target_id)
        return mastery
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения уровней мастерства: {str(e)}"
        )


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
    user_profile, psn_id = get_user_with_psn(DB_PATH, user_id)
    
    # Загружаем конфиг мастерства
    try:
        config = load_mastery_config()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка загрузки конфига мастерства: {str(e)}"
        )
    
    # Находим категорию в конфиге
    category = find_category_by_key(config, category_key)
    
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
        if not validate_image_file(photo):
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
    
    # Обрабатываем и отправляем фотографии
    try:
        with temp_image_directory(prefix='mastery_app_') as temp_dir:
            photo_paths = []
            
            # Обрабатываем и сохраняем изображения
            for i, photo in enumerate(photos):
                photo_path = os.path.join(temp_dir, f'photo_{i+1}.jpg')
                
                # Открываем изображение через Pillow
                image = Image.open(photo.file)
                
                # Обрабатываем изображение
                process_image_for_upload(image, photo_path)
                photo_paths.append(photo_path)
                
                # Возвращаем курсор файла
                photo.file.seek(0)
            
            # Отправляем уведомление в группу с message_thread_id (в отдельную тему)
            try:
                await send_photos_to_telegram_group(
                    bot_token=BOT_TOKEN,
                    chat_id=TROPHY_GROUP_CHAT_ID,
                    photo_paths=photo_paths,
                    message_text=message_text,
                    reply_markup=reply_markup,
                    message_thread_id=TROPHY_GROUP_TOPIC_ID
                )
            except Exception as e:
                print(f"Ошибка отправки заявки в группу: {e}")
                # Не прерываем выполнение, но логируем ошибку
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки изображений: {str(e)}"
        )
    
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
    from db import set_mastery, get_mastery
    
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
    category = find_category_by_key(config, category_key)
    level_data = None
    if category:
        for level in category.get('levels', []):
            if level.get('level') == next_level:
                level_data = level
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
            bot_token=BOT_TOKEN,
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
    category = find_category_by_key(config, category_key)
    level_data = None
    if category:
        for level in category.get('levels', []):
            if level.get('level') == next_level:
                level_data = level
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
            bot_token=BOT_TOKEN,
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
# ========== API ЭНДПОИНТЫ ДЛЯ СКРИНШОТА ПРОФИЛЯ ==========

@app.get("/profile-preview/{user_id}", response_class=HTMLResponse)
async def get_profile_preview(user_id: int):
    """
    Возвращает HTML-страницу профиля для скриншота.
    
    Args:
        user_id: ID пользователя, чей профиль нужно показать
    """
    # Читаем HTML-шаблон
    template_path = os.path.join(os.path.dirname(__file__), 'profile_preview.html')
    
    if not os.path.exists(template_path):
        raise HTTPException(status_code=500, detail="HTML template not found")
    
    with open(template_path, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Получаем данные профиля
    profile = get_user(DB_PATH, user_id)
    
    # Получаем данные мастерства
    mastery_levels = get_mastery(DB_PATH, user_id)
    
    # Загружаем конфиг мастерства
    try:
        mastery_config = load_mastery_config()
    except Exception as e:
        print(f"Ошибка загрузки конфига мастерства: {e}")
        mastery_config = None
    
    # Формируем данные профиля для встраивания в HTML
    profile_data = {
        "user_id": user_id,
        "real_name": profile.get('real_name', '') if profile else '',
        "psn_id": profile.get('psn_id', '') if profile else '',
        "platforms": profile.get('platforms', []) if profile else [],
        "modes": profile.get('modes', []) if profile else [],
        "goals": profile.get('goals', []) if profile else [],
        "difficulties": profile.get('difficulties', []) if profile else [],
        "avatar_url": profile.get('avatar_url', '') if profile else '',
        "mastery": mastery_levels,
        "mastery_config": mastery_config
    }
    
    # Встраиваем данные профиля напрямую в HTML (без JavaScript)
    def format_array(arr):
        if not arr or not isinstance(arr, list) or len(arr) == 0:
            return '—'
        return '\n'.join(arr)
    
    # Формируем значения для подстановки
    real_name = profile_data.get('real_name', '') or '—'
    psn_id = profile_data.get('psn_id', '') or '—'
    
    platforms_list = profile_data.get('platforms', [])
    modes_list = profile_data.get('modes', [])
    goals_list = profile_data.get('goals', [])
    difficulties_list = profile_data.get('difficulties', [])
    
    # Подставляем данные напрямую в HTML
    html_content = html_content.replace('<div id="v_real_name" class="value">—</div>', 
                                       f'<div id="v_real_name" class="value">{real_name}</div>')
    html_content = html_content.replace('<div id="v_psn_id" class="value">—</div>', 
                                       f'<div id="v_psn_id" class="value">{psn_id}</div>')
    
    # Заменяем значения на обычный текст через запятую (вместо чипов)
    platforms_text = ", ".join(platforms_list) if platforms_list else "—"
    modes_text = ", ".join(modes_list) if modes_list else "—"
    goals_text = ", ".join(goals_list) if goals_list else "—"
    difficulties_text = ", ".join(difficulties_list) if difficulties_list else "—"
    
    html_content = html_content.replace(
        '<div id="v_platform" class="value"></div>',
        f'<div id="v_platform" class="value">{platforms_text}</div>'
    )
    html_content = html_content.replace(
        '<div id="v_modes" class="value"></div>',
        f'<div id="v_modes" class="value">{modes_text}</div>'
    )
    html_content = html_content.replace(
        '<div id="v_goals" class="value"></div>',
        f'<div id="v_goals" class="value">{goals_text}</div>'
    )
    html_content = html_content.replace(
        '<div id="v_difficulty" class="value"></div>',
        f'<div id="v_difficulty" class="value">{difficulties_text}</div>'
    )
    
    # Скрываем контейнеры для чипов (они больше не нужны)
    html_content = html_content.replace(
        '<div id="v_platform_chips" class="chips-container"></div>',
        '<div id="v_platform_chips" class="chips-container" style="display: none;"></div>'
    )
    html_content = html_content.replace(
        '<div id="v_modes_chips" class="chips-container"></div>',
        '<div id="v_modes_chips" class="chips-container" style="display: none;"></div>'
    )
    html_content = html_content.replace(
        '<div id="v_goals_chips" class="chips-container"></div>',
        '<div id="v_goals_chips" class="chips-container" style="display: none;"></div>'
    )
    html_content = html_content.replace(
        '<div id="v_difficulty_chips" class="chips-container"></div>',
        '<div id="v_difficulty_chips" class="chips-container" style="display: none;"></div>'
    )
    
    # Обработка аватарки
    avatar_url = profile_data.get('avatar_url', '')
    if avatar_url:
        if not avatar_url.startswith('http'):
            # Определяем базовый URL (предполагаем localhost для скриншота)
            base_url = "http://localhost:8000"
            avatar_url = f"{base_url}{avatar_url}"
        # Заменяем placeholder на изображение
        avatar_html = f'''<img id="avatarImg" src="{avatar_url}" alt="Аватар" style="display: block;" />
            <div class="avatar-placeholder" id="avatarPlaceholder" style="display: none;">+</div>'''
        html_content = html_content.replace(
            '<img id="avatarImg" src="" alt="Аватар" style="display: none;" />\n            <div class="avatar-placeholder" id="avatarPlaceholder" style="display: flex; align-items: center; justify-content: center; font-size: 32px; color: var(--muted);">+</div>',
            avatar_html
        )
    
    # Генерируем текстовый список мастерства
    mastery_list = []
    
    if mastery_config and mastery_levels:
        # Порядок категорий
        category_order = ['solo', 'hellmode', 'raid', 'speedrun']
        
        for category_key in category_order:
            current_level = mastery_levels.get(category_key, 0)
            
            # Пропускаем категории с нулевым уровнем
            if current_level == 0:
                continue
            
            # Находим категорию в конфиге
            category = None
            for cat in mastery_config.get('categories', []):
                if cat.get('key') == category_key:
                    category = cat
                    break
            
            if not category:
                continue
            
            max_levels = category.get('maxLevels', 0)
            
            # Находим данные уровня
            level_data = None
            for level in category.get('levels', []):
                if level.get('level') == current_level:
                    level_data = level
                    break
            
            level_name = level_data.get('name', f'Уровень {current_level}') if level_data else f'Уровень {current_level}'
            category_name = category.get('name', category_key)
            
            # Формат: "Категория (уровень/макс Уровень) - Название уровня"
            mastery_item = f"{category_name} ({current_level}/{max_levels}) - {level_name}"
            mastery_list.append(mastery_item)
    
    # Вставляем список мастерства
    mastery_text = "\n".join(mastery_list) if mastery_list else "—"
    html_content = html_content.replace(
        '<div id="v_mastery" class="value lines">—</div>',
        f'<div id="v_mastery" class="value lines">{mastery_text}</div>'
    )
    
    # Добавляем скрипт для сигнала готовности (данные уже заполнены)
    script_replacement = """
        <script>
            // Данные уже заполнены в HTML, просто сигнализируем готовность
            (function() {
                const readyEl = document.getElementById('profile-ready');
                if (readyEl) {
                    readyEl.textContent = 'ready';
                    readyEl.setAttribute('data-ready', 'true');
                }
                
                // Если есть аватарка, проверяем её загрузку
                const avatarImg = document.getElementById('avatarImg');
                if (avatarImg && avatarImg.src) {
                    avatarImg.onload = function() {
                        const readyEl = document.getElementById('profile-ready');
                        if (readyEl) {
                            readyEl.setAttribute('data-ready', 'true');
                        }
                    };
                    avatarImg.onerror = function() {
                        // Если аватарка не загрузилась, показываем placeholder
                        avatarImg.style.display = 'none';
                        const placeholder = document.getElementById('avatarPlaceholder');
                        if (placeholder) {
                            placeholder.style.display = 'flex';
                        }
                        const readyEl = document.getElementById('profile-ready');
                        if (readyEl) {
                            readyEl.setAttribute('data-ready', 'true');
                        }
                    };
                    // Если изображение уже загружено
                    if (avatarImg.complete) {
                        const readyEl = document.getElementById('profile-ready');
                        if (readyEl) {
                            readyEl.setAttribute('data-ready', 'true');
                        }
                    }
                } else {
                    // Нет аватарки, страница готова
                    const readyEl = document.getElementById('profile-ready');
                    if (readyEl) {
                        readyEl.setAttribute('data-ready', 'true');
                    }
                }
                
                // Мастерство теперь просто текст, не нужно ждать загрузки изображений
                const readyElFinal = document.getElementById('profile-ready');
                if (readyElFinal) {
                    readyElFinal.setAttribute('data-ready', 'true');
                }
            })();
        </script>
    """
    
    # Заменяем placeholder script блок
    html_content = re.sub(
        r'<script>\s*// Placeholder.*?</script>',
        script_replacement,
        html_content,
        flags=re.DOTALL
    )
    
    # Если не нашли placeholder, добавляем скрипт перед закрывающим тегом body
    if 'data-ready' not in html_content:
        html_content = html_content.replace('</body>', script_replacement + '\n</body>')
    
    return html_content


async def screenshot_profile(user_id: int, base_url: str = "http://localhost:8000") -> bytes:
    """
    Создает скриншот страницы профиля через Playwright.
    
    Args:
        user_id: ID пользователя
        base_url: Базовый URL сервера (по умолчанию localhost:8000)
    
    Returns:
        PNG изображение в виде bytes
    """
    url = f"{base_url}/profile-preview/{user_id}"
    
    async with async_playwright() as p:
        # Запускаем браузер в headless режиме
        browser = await p.chromium.launch(headless=True)
        
        try:
            # Создаем контекст с мобильным viewport
            context = await browser.new_context(
                viewport={"width": 375, "height": 812},
                device_scale_factor=2,
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
            )
            
            # Создаем страницу
            page = await context.new_page()
            
            try:
                # Переходим на страницу
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # Ждем, пока данные профиля загрузятся и заполнятся
                # Ожидаем либо появления элемента #profile-ready с атрибутом data-ready,
                # либо проверяем, что данные заполнены
                try:
                    # Ждем появления элемента и заполнения данных
                    await page.wait_for_function(
                        """
                        () => {
                            const readyEl = document.getElementById('profile-ready');
                            if (!readyEl) return false;
                            
                            // Проверяем, что данные заполнены (не прочерки)
                            const realName = document.getElementById('v_real_name')?.textContent || '';
                            const psnId = document.getElementById('v_psn_id')?.textContent || '';
                            
                            // Элемент готов И данные заполнены
                            return readyEl.getAttribute('data-ready') === 'true' && 
                                   (realName !== '—' || psnId !== '—');
                        }
                        """,
                        timeout=10000
                    )
                    # Дополнительная небольшая задержка для завершения рендеринга
                    await page.wait_for_timeout(300)
                except Exception as e:
                    # Если не дождались, проверяем состояние страницы
                    print(f"Warning: Timeout waiting for profile data: {e}")
                    # Проверяем, есть ли хотя бы какие-то данные
                    has_data = await page.evaluate("""
                        () => {
                            const realName = document.getElementById('v_real_name')?.textContent || '';
                            const psnId = document.getElementById('v_psn_id')?.textContent || '';
                            return realName !== '—' || psnId !== '—';
                        }
                    """)
                    if not has_data:
                        # Если данных нет, ждем еще
                        await page.wait_for_timeout(2000)
                        # Проверяем еще раз
                        has_data = await page.evaluate("""
                            () => {
                                const realName = document.getElementById('v_real_name')?.textContent || '';
                                const psnId = document.getElementById('v_psn_id')?.textContent || '';
                                return realName !== '—' || psnId !== '—';
                            }
                        """)
                        if not has_data:
                            print("Warning: Profile data still not loaded after extended wait")
                
                # Определяем реальную высоту контента и делаем скриншот
                content_bounds = await page.evaluate("""
                    () => {
                        const card = document.querySelector('.card');
                        if (!card) return null;
                        
                        // Получаем позицию и размеры карточки
                        const rect = card.getBoundingClientRect();
                        
                        // Добавляем небольшой отступ снизу для красоты
                        const padding = 20;
                        
                        // Ширина должна быть полной шириной экрана, обрезаем только снизу
                        const fullWidth = window.innerWidth || document.documentElement.clientWidth || 375;
                        
                        // Высота = позиция карточки сверху + высота карточки + отступ
                        return {
                            x: 0,
                            y: 0,
                            width: Math.ceil(fullWidth),
                            height: Math.ceil(rect.height + rect.top + padding)
                        };
                    }
                """)
                
                if content_bounds and content_bounds['height'] > 0:
                    # Делаем скриншот только нужной области
                    screenshot_bytes = await page.screenshot(
                        type="png",
                        clip=content_bounds
                    )
                else:
                    # Fallback на полный скриншот, если не удалось определить размеры
                    screenshot_bytes = await page.screenshot(type="png", full_page=True)
                
                return screenshot_bytes
                
            finally:
                await page.close()
                await context.close()
                
        finally:
            await browser.close()


async def send_photo_to_telegram(chat_id: str, photo_buffer: bytes, caption: str = "", message_thread_id: Optional[int] = None) -> dict:
    """
    Отправляет фото в Telegram через Bot API используя requests.
    
    Args:
        chat_id: ID чата для отправки
        photo_buffer: Буфер с изображением (PNG bytes)
        caption: Подпись к фото
        message_thread_id: ID темы (если есть)
    
    Returns:
        Результат запроса к Telegram API
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    # Подготавливаем данные для отправки
    files = {
        'photo': ('profile.png', io.BytesIO(photo_buffer), 'image/png')
    }
    
    data = {
        'chat_id': chat_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    
    if message_thread_id:
        data['message_thread_id'] = message_thread_id
    
    # Отправляем запрос
    response = requests.post(url, files=files, data=data, timeout=30)
    
    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Telegram API error: {response.text}"
        )
    
    return response.json()


@app.post("/api/send_profile/{user_id}")
async def send_profile_screenshot(
    user_id: int,
    chat_id: str = Query(..., description="ID чата для отправки фото"),
    message_thread_id: Optional[int] = Query(None, description="ID темы (если есть)"),
    base_url: Optional[str] = Query(None, description="Базовый URL сервера (по умолчанию localhost:8000)")
):
    """
    Создает скриншот профиля пользователя и отправляет его в Telegram.
    
    Args:
        user_id: ID пользователя, чей профиль нужно отправить
        chat_id: ID чата для отправки фото
        message_thread_id: ID темы (опционально)
        base_url: Базовый URL сервера (для создания скриншота)
    
    Returns:
        JSON с результатом операции
    """
    try:
        # Определяем базовый URL
        if not base_url:
            # Используем localhost для скриншота, так как Playwright работает локально
            # Внешний API_BASE_URL может быть недоступен изнутри сервера
            base_url = "http://localhost:8000"
        
        # Проверяем существование профиля
        profile = get_user(DB_PATH, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Профиль не найден")
        
        # Создаем скриншот
        screenshot_bytes = await screenshot_profile(user_id, base_url)
        
        # Формируем подпись
        caption_parts = []
        if profile.get('real_name'):
            caption_parts.append(f"👤 <b>{profile['real_name']}</b>")
        if profile.get('psn_id'):
            caption_parts.append(f"🎮 PSN: {profile['psn_id']}")
        
        caption = "\n".join(caption_parts) if caption_parts else "👤 Профиль пользователя"
        
        # Отправляем фото в Telegram
        result = await send_photo_to_telegram(
            chat_id=chat_id,
            photo_buffer=screenshot_bytes,
            caption=caption,
            message_thread_id=message_thread_id
        )
        
        return {
            "status": "ok",
            "message": "Скриншот профиля успешно отправлен",
            "telegram_result": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка при создании и отправке скриншота: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при создании скриншота: {str(e)}"
        )


@app.exception_handler(HTTPException)
async def cors_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# Запуск приложения
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
