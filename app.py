# app.py
# FastAPI приложение для Tsushima Mini App API
# Проверка пуша на GitHub

import os
import shutil
import json
import aiohttp
import tempfile
import sqlite3
import io
import html
import traceback
import re
import time
from pathlib import Path
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
from db import (
    init_db,
    get_user,
    upsert_user,
    create_build,
    get_build,
    get_user_builds,
    update_build_visibility,
    delete_build,
    update_build,
    get_all_users,
    get_mastery,
    create_comment,
    get_build_comments,
    toggle_reaction,
    get_reactions,
    update_avatar_url,
    update_build_photos,
    get_trophies,
    add_trophy,
    update_active_trophies,
    delete_user_all_data,
    get_current_rotation_week,
    update_rotation_week,
    log_recent_event,
    get_recent_events,
    get_recent_comments,
)
from image_utils import (
    process_image_for_upload,
    process_avatar_image,
    validate_image_file,
    temp_image_directory,
    detect_media_type,
    guess_media_extension,
    save_upload_file,
)
from telegram_utils import send_telegram_message, send_media_to_telegram_group, get_chat_member
from user_utils import get_user_with_psn, format_profile_response
from mastery_utils import find_category_by_key, parse_tags
from mastery_config import load_mastery_config
from trophy_config import load_trophy_config, find_trophy_by_key

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
raw_allowed_origins = os.getenv("ALLOWED_ORIGIN", "")
ALLOWED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in raw_allowed_origins.split(",")
    if origin.strip()
]
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")

# Параметры для отправки уведомлений/сообщений
TROPHY_GROUP_CHAT_ID = os.getenv("TROPHY_GROUP_CHAT_ID", "")
TROPHY_GROUP_TOPIC_ID = os.getenv("TROPHY_GROUP_TOPIC_ID", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
# ID основной группы (используется для проверки участников)
GROUP_ID = os.getenv("GROUP_ID", "-1002365374672")
# Ссылка на группу для приглашения
GROUP_INVITE_LINK = os.getenv("GROUP_INVITE_LINK", "https://t.me/+ZFiVYVrz-PEzYjBi")

# Путь к данным волн
WAVES_FILE_PATH = "/root/gyozenbot/json/waves.json"
WAVES_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), 'waves_preview.html')
OBJECTIVE_WAVE_NUMBERS = [2, 4, 7, 10, 13]
MOD_WAVE_NUMBERS = [3, 6, 9, 12, 15]
ASSETS_PREFIX = "/assets"

# Удалены кеш и загрузка данных трофеев
# Функции для работы с Telegram Bot API перенесены в telegram_utils.py

MAX_MEDIA_ATTACHMENTS = 18
TELEGRAM_MEDIA_BATCH_LIMIT = 9

# Проверяем обязательные переменные
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env файле")
if not ALLOWED_ORIGINS:
    raise ValueError("ALLOWED_ORIGIN не установлен или пуст в .env файле")

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


@app.middleware("http")
async def filter_bot_requests(request: Request, call_next):
    """
    Фильтрует известные бот-запросы (WordPress, phpMyAdmin и т.д.).
    Возвращает 404 без логирования для таких запросов.
    """
    path = request.url.path.lower()
    
    # Список известных бот-путей
    bot_paths = [
        '/wp-admin', '/wp-login', '/wp-content', '/wp-includes',
        '/phpmyadmin', '/admin', '/administrator',
        '/.env', '/config.php', '/setup-config.php',
        '/wordpress', '/joomla', '/drupal',
        '/xmlrpc.php', '/wp-cron.php', '/wp-trackback.php'
    ]
    
    # Проверяем, является ли путь бот-запросом
    if any(bot_path in path for bot_path in bot_paths):
        # Возвращаем 404 без логирования
        return Response(status_code=404, content="Not Found")
    
    return await call_next(request)

# Раздача статических файлов для preview страниц
app.mount("/css", StaticFiles(directory="/root/tsushimaru_app/docs/css"), name="css")
app.mount("/assets", StaticFiles(directory="/root/tsushimaru_app/docs/assets"), name="assets")

# Инициализируем базу данных при запуске
init_db(DB_PATH)


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
    
    # Загружаем дополнительные данные и формируем расширенные флаги
    try:
        # Опциональный локальный импорт для подсчета публичных билдов
        from db import get_user_public_builds_count as db_get_user_public_builds_count
    except Exception:
        db_get_user_public_builds_count = None
    
    try:
        for u in users:
            uid = u.get('user_id')
            
            # ТРОФЕИ (гарантированно заполняем сначала)
            try:
                trophies_data = get_trophies(DB_PATH, uid) if uid else {'trophies': [], 'active_trophies': []}
                all_trophies = trophies_data.get('trophies', []) or []
                active_trophies = trophies_data.get('active_trophies', []) or []
            except Exception:
                all_trophies = []
                active_trophies = []
            u['active_trophies'] = active_trophies
            u['trophies_count'] = len(all_trophies)
            u['active_trophies_count'] = len(active_trophies)
            u['has_any_trophy'] = len(all_trophies) > 0
            
            # МАСТЕРСТВО → флаг наличия любого прогресса > 0
            mastery = u.get('mastery') or {}
            try:
                levels_iter = [
                    int(mastery.get('solo') or 0),
                    int(mastery.get('hellmode') or 0),
                    int(mastery.get('raid') or 0),
                    int(mastery.get('speedrun') or 0),
                    int(mastery.get('glitch') or 0),
                ]
                u['has_mastery_progress'] = any(level > 0 for level in levels_iter)
            except Exception:
                u['has_mastery_progress'] = False
            # Убираем подробные уровни из ответа (опционально для экономии трафика)
            u.pop('mastery', None)
            
            # БИЛДЫ → количество публичных билдов и флаг
            builds_count = 0
            if db_get_user_public_builds_count and uid:
                try:
                    builds_count = int(db_get_user_public_builds_count(DB_PATH, uid)) or 0
                except Exception:
                    builds_count = 0
            u['builds_count'] = builds_count
            u['has_public_builds'] = builds_count > 0
    
    except Exception as e:
        print(f"Ошибка формирования расширенных полей users.list: {e}")
        # Деградация: гарантируем наличие обязательных полей
        for u in users:
            u['active_trophies'] = u.get('active_trophies', [])
            u['trophies_count'] = u.get('trophies_count', 0)
            u['active_trophies_count'] = u.get('active_trophies_count', 0)
            u['has_any_trophy'] = u.get('has_any_trophy', False)
            u['has_mastery_progress'] = u.get('has_mastery_progress', False)
            u['builds_count'] = u.get('builds_count', 0)
            u['has_public_builds'] = u.get('has_public_builds', False)
            u.pop('mastery', None)
    
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


@app.get("/api/user.checkGroupMembership")
async def check_group_membership(user_id: int = Depends(get_current_user)):
    """
    Проверяет, является ли пользователь участником основной группы.
    
    Args:
        user_id: ID пользователя (из dependency)
    
    Returns:
        JSON с информацией о статусе участия в группе
    """
    try:
        # Получаем информацию об участнике через Telegram Bot API
        result = await get_chat_member(
            bot_token=BOT_TOKEN,
            chat_id=GROUP_ID,
            user_id=user_id
        )
        
        # Проверяем результат запроса
        if not result.get('ok'):
            # Если запрос не успешен, возвращаем ошибку
            error_code = result.get('error_code', 500)
            error_description = result.get('description', 'Неизвестная ошибка')
            raise HTTPException(
                status_code=error_code if error_code < 600 else 500,
                detail=f"Ошибка проверки участника: {error_description}"
            )
        
        # Извлекаем статус участника
        chat_member = result.get('result', {})
        status = chat_member.get('status', 'unknown')
        
        # Определяем, является ли пользователь участником группы
        # Участниками считаются: member, administrator, creator, restricted
        is_member = status in ['member', 'administrator', 'creator', 'restricted']
        
        return {
            "is_member": is_member,
            "status": status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка проверки участника в группе: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при проверке участника в группе: {str(e)}"
        )


@app.post("/api/user.notifyNotRegistered")
async def notify_user_not_in_group(user_id: int = Depends(get_current_user)):
    """
    Отправляет сообщение пользователю о необходимости вступления в группу.
    Вызывается когда пользователь открывает приложение, но не является участником группы.
    
    Args:
        user_id: ID пользователя (из dependency)
    
    Returns:
        JSON с результатом отправки сообщения
    """
    try:
        # Формируем текст сообщения
        message_text = (
            "👋 <b>Добро пожаловать!</b>\n\n"
            "Для использования приложения необходимо быть участником группы <b>Tsushima.Ru</b>.\n\n"
            "Пожалуйста, присоединитесь к группе, чтобы продолжить."
        )
        
        # Создаем inline кнопку со ссылкой на группу
        reply_markup = {
            "inline_keyboard": [[
                {
                    "text": "Присоединиться к группе",
                    "url": GROUP_INVITE_LINK
                }
            ]]
        }
        
        # Отправляем сообщение пользователю в личку
        result = await send_telegram_message(
            bot_token=BOT_TOKEN,
            chat_id=str(user_id),
            text=message_text,
            reply_markup=reply_markup
        )
        
        if result.get('ok'):
            return {
                "success": True,
                "message": "Сообщение отправлено пользователю"
            }
        else:
            error_description = result.get('description', 'Неизвестная ошибка')
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка отправки сообщения: {error_description}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка отправки уведомления пользователю: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при отправке уведомления: {str(e)}"
        )


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


@app.get("/api/rotation/current")
async def get_current_rotation():
    """
    Возвращает текущую неделю ротации (1-16).
    """
    week = get_current_rotation_week(DB_PATH)
    
    if week is None:
        raise HTTPException(status_code=500, detail="Ошибка получения текущей недели")
    
    return {"week": week}


def _read_waves_json() -> dict:
    """
    Загружает данные волн из файла waves.json.
    """
    try:
        with open(WAVES_FILE_PATH, "r", encoding="utf-8") as f:
            waves_data = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Файл waves.json не найден")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Некорректный формат waves.json: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Ошибка чтения waves.json: {exc}")

    if not isinstance(waves_data, dict):
        raise HTTPException(status_code=500, detail="Неверный формат данных waves.json")

    return waves_data


@app.get("/api/waves.get")
async def get_waves_data(user_id: int = Depends(get_current_user)):
    """
    Возвращает данные волн из waves.json.
    """
    return _read_waves_json()


def _safe_text(value, default: str = "—") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _format_week_title(week_value, absolute_value) -> str:
    week = str(week_value).strip() if week_value is not None else ""
    absolute = str(absolute_value).strip() if absolute_value is not None else ""
    if week and absolute:
        return f"{absolute}-ая неделя ({week})"
    if absolute:
        return f"{absolute}-ая неделя"
    if week:
        return f"Неделя {week}"
    return "Волны"


def _get_objective_icon(objectives: Optional[dict], wave_number: int) -> Optional[dict]:
    if not isinstance(objectives, dict):
        return None
    try:
        index = OBJECTIVE_WAVE_NUMBERS.index(wave_number)
    except ValueError:
        return None

    base_key = f"objective{index + 1}"
    filename = objectives.get(f"{base_key}_icon")
    if not filename:
        return None

    description = _safe_text(objectives.get(base_key), "Бонусная задача")
    count = objectives.get(f"{base_key}_num")
    label = str(count).strip() if count is not None and str(count).strip() else None
    tooltip = description if not label else f"{description} — {label}"

    return {
        "path": f"{ASSETS_PREFIX}/icons/objectives/{filename}",
        "badge_class": "waves-icon-badge--objective",
        "description": tooltip,
        "label": label,
    }


def _get_mod_icon(mods: Optional[dict], wave_number: int) -> Optional[dict]:
    if not isinstance(mods, dict):
        return None
    try:
        index = MOD_WAVE_NUMBERS.index(wave_number)
    except ValueError:
        return None

    base_key = f"mod{index + 1}"
    filename = mods.get(f"{base_key}_icon")
    if not filename:
        return None

    description = _safe_text(mods.get(base_key), "Модификатор мира")

    return {
        "path": f"{ASSETS_PREFIX}/icons/mods/{filename}",
        "badge_class": "waves-icon-badge--mod",
        "description": description,
        "label": None,
    }


def _get_wave_icon_data(waves_data: dict, wave_number: int) -> Optional[dict]:
    icon = _get_objective_icon(waves_data.get("objectives"), wave_number)
    if icon:
        return icon
    return _get_mod_icon(waves_data.get("mods"), wave_number)


def _build_wave_icon_cell(waves_data: dict, wave_number: int) -> str:
    icon_data = _get_wave_icon_data(waves_data, wave_number)
    if not icon_data:
        return '<td class="waves-icon"></td>'

    label_html = ""
    if icon_data.get("label"):
        label_html = f'<span class="waves-icon-tag">{html.escape(icon_data["label"])}</span>'

    description = html.escape(icon_data.get("description", ""))
    path = html.escape(icon_data.get("path", ""))
    badge_class = icon_data.get("badge_class", "")

    return (
        '<td class="waves-icon">'
        f'<div class="waves-icon-badge {badge_class}">'
        f'{label_html}'
        f'<img class="waves-icon-img" src="{path}" alt="{description}" title="{description}" data-await="true" />'
        "</div>"
        "</td>"
    )


def _build_waves_table_rows(waves_data: dict) -> str:
    rows: List[str] = []
    waves = waves_data.get("waves")

    for index in range(15):
        wave_number = index + 1
        row_class = ' class="waves-strong"' if wave_number % 3 == 0 else ""

        wave_row = []
        if isinstance(waves, list) and index < len(waves) and isinstance(waves[index], list):
            for value in waves[index]:
                if isinstance(value, str):
                    cleaned = value.strip()
                    if cleaned:
                        wave_row.append(cleaned)

        spawns_text = ", ".join(wave_row) if wave_row else "—"
        spawns_html = html.escape(spawns_text)
        icon_cell = _build_wave_icon_cell(waves_data, wave_number)

        rows.append(
            f'<tr{row_class}>\n'
            f'    {icon_cell}\n'
            f'    <td class="waves-number">{wave_number}.</td>\n'
            f'    <td class="waves-spawns">{spawns_html}</td>\n'
            f'</tr>'
        )

    return "\n".join(rows)


def _build_header_mod_icons(waves_data: dict) -> tuple[str, bool]:
    icons: List[str] = []

    mod1_icon = waves_data.get("mod1_icon")
    if mod1_icon:
        title = _safe_text(waves_data.get("mod1"), "")
        icons.append(
            '<div class="waves-mod-icon">'
            f'<img src="{ASSETS_PREFIX}/icons/mod1/{html.escape(mod1_icon)}" alt="{html.escape(title)}" '
            f'title="{html.escape(title)}" data-await="true" />'
            "</div>"
        )

    mod2_icon = waves_data.get("mod2_icon")
    if mod2_icon:
        title = _safe_text(waves_data.get("mod2"), "")
        icons.append(
            '<div class="waves-mod-icon">'
            f'<img src="{ASSETS_PREFIX}/icons/mod2/{html.escape(mod2_icon)}" alt="{html.escape(title)}" '
            f'title="{html.escape(title)}" data-await="true" />'
            "</div>"
        )

    return ("\n".join(icons), bool(icons))


def render_waves_template(waves_data: dict) -> str:
    if not os.path.exists(WAVES_TEMPLATE_PATH):
        raise HTTPException(status_code=500, detail="HTML template not found")

    with open(WAVES_TEMPLATE_PATH, "r", encoding="utf-8") as template_file:
        html_content = template_file.read()

    topbar_title = _format_week_title(waves_data.get("week"), waves_data.get("absolute_week"))
    map_name = _safe_text(waves_data.get("map"))
    mod1_text = _safe_text(waves_data.get("mod1"))
    mod2_text = _safe_text(waves_data.get("mod2"))

    slug = _safe_text(waves_data.get("slug"), "")
    if slug:
        map_url = f"{ASSETS_PREFIX}/maps/survival/{slug}.jpg"
        map_card_extra_class = "waves-meta-card--with-bg"
        map_bg_style = f"--waves-map-bg: url('{html.escape(map_url, quote=True)}');"
    else:
        map_card_extra_class = ""
        map_bg_style = "--waves-map-bg: none;"

    mod_icons_html, has_mod_icons = _build_header_mod_icons(waves_data)
    mod_icons_class = "waves-mod-icons" if has_mod_icons else "waves-mod-icons hidden"
    mod_icons_html = mod_icons_html or ""

    waves_rows = _build_waves_table_rows(waves_data)
    has_waves = bool(waves_rows.strip())
    empty_class = "hidden" if has_waves else ""

    replacements = {
        "__TOPBAR_TITLE__": html.escape(topbar_title),
        "__MAP_CARD_EXTRA_CLASS__": map_card_extra_class,
        "__MOD_ICONS_CLASS__": mod_icons_class,
        "__MOD_ICONS__": mod_icons_html,
        "__MAP_NAME__": html.escape(map_name),
        "__MOD1__": html.escape(mod1_text),
        "__MOD2__": html.escape(mod2_text),
        "__WAVES_ROWS__": waves_rows,
        "__EMPTY_CLASS__": empty_class,
    }

    for placeholder, value in replacements.items():
        html_content = html_content.replace(placeholder, value)

    html_content = html_content.replace(
        'style="--waves-map-bg: none;"',
        f'style="{map_bg_style}"',
        1,
    )

    script_content = """
        (function() {
            const readyEl = document.getElementById('waves-ready');
            if (!readyEl) {
                return;
            }
            const images = Array.from(document.querySelectorAll('img[data-await="true"]'));
            if (!images.length) {
                readyEl.setAttribute('data-ready', 'true');
                return;
            }
            let remaining = images.length;
            const markReady = () => {
                readyEl.setAttribute('data-ready', 'true');
            };
            const finalize = () => {
                remaining -= 1;
                if (remaining <= 0) {
                    markReady();
                }
            };
            images.forEach((img) => {
                if (img.complete) {
                    finalize();
                } else {
                    img.addEventListener('load', finalize, { once: true });
                    img.addEventListener('error', finalize, { once: true });
                }
            });
        })();
    """.strip()

    html_content = html_content.replace(
        "// READY_SCRIPT_PLACEHOLDER",
        script_content,
        1,
    )

    return html_content


@app.get("/waves-preview", response_class=HTMLResponse)
async def get_waves_preview():
    """
    Возвращает HTML-страницу текущей ротации волн для скриншота.
    """
    waves_data = _read_waves_json()
    return render_waves_template(waves_data)

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
    
    # Валидация
    media_files = photos or []
    
    if len(media_files) > MAX_MEDIA_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Можно прикрепить не более {MAX_MEDIA_ATTACHMENTS} файлов"
        )
    
    normalized_media = []
    for upload in media_files:
        media_kind = detect_media_type(upload)
        if media_kind not in {'photo', 'video'}:
            raise HTTPException(
                status_code=400,
                detail="Разрешены только изображения и видео (MP4, MOV)."
            )
        normalized_media.append((upload, media_kind))
    
    # Формируем сообщение для группы
    message_text = f"""💬 <b>Новый отзыв/баг-репорт</b>

👤 <b>Пользователь:</b> {psn_id}

💬 <b>Описание:</b>
{description.strip()}
"""
    
    # Обрабатываем и отправляем медиафайлы
    try:
        if len(normalized_media) > 0:
            with temp_image_directory(prefix='feedback_') as temp_dir:
                media_payload = []
                
                for index, (upload, media_kind) in enumerate(normalized_media, start=1):
                    if media_kind == 'photo':
                        try:
                            upload.file.seek(0)
                        except Exception:
                            pass

                        photo_path = os.path.join(temp_dir, f'media_{index}.jpg')
                        image = Image.open(upload.file)
                        process_image_for_upload(image, photo_path)
                        media_payload.append({
                            "type": "photo",
                            "path": photo_path,
                        })

                        try:
                            upload.file.seek(0)
                        except Exception:
                            pass
                    else:
                        extension = guess_media_extension(upload, default='.mp4')
                        if not extension.startswith('.'):
                            extension = f'.{extension}'

                        video_path = os.path.join(temp_dir, f'media_{index}{extension}')
                        save_upload_file(upload, video_path)
                        media_payload.append({
                            "type": "video",
                            "path": video_path,
                        })
                
                # Отправляем уведомление в группу БЕЗ message_thread_id (в основную тему)
                try:
                    await send_media_to_telegram_group(
                        bot_token=BOT_TOKEN,
                        chat_id=TROPHY_GROUP_CHAT_ID,
                        media_items=media_payload,
                        message_text=message_text
                    )
                except Exception as e:
                    print(f"Ошибка отправки отзыва в группу: {e}")
                    # Не прерываем выполнение, но логируем ошибку
        else:
            # Если нет медиафайлов, отправляем просто текстовое сообщение
            try:
                await send_telegram_message(
                    bot_token=BOT_TOKEN,
                    chat_id=TROPHY_GROUP_CHAT_ID,
                    text=message_text
                )
            except Exception as e:
                print(f"Ошибка отправки отзыва в группу: {e}")
                # Не прерываем выполнение, но логируем ошибку
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обработки медиафайлов: {str(e)}"
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
        Словарь с уровнями по категориям: {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0, "glitch": 0}
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
    media_files = photos or []

    if len(media_files) == 0:
        raise HTTPException(
            status_code=400,
            detail="Необходимо прикрепить хотя бы один файл (изображение или видео)"
        )
    
    if len(media_files) > MAX_MEDIA_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Можно прикрепить не более {MAX_MEDIA_ATTACHMENTS} файлов"
        )
    
    normalized_media = []
    for upload in media_files:
        media_kind = detect_media_type(upload)
        if media_kind not in {'photo', 'video'}:
            raise HTTPException(
                status_code=400,
                detail="Разрешены только изображения и видео (MP4, MOV)."
            )
        normalized_media.append((upload, media_kind))
    
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
            media_payload = []
            
            for index, (upload, media_kind) in enumerate(normalized_media, start=1):
                if media_kind == 'photo':
                    try:
                        upload.file.seek(0)
                    except Exception:
                        pass

                    photo_path = os.path.join(temp_dir, f'media_{index}.jpg')
                    image = Image.open(upload.file)
                    process_image_for_upload(image, photo_path)
                    media_payload.append({
                        "type": "photo",
                        "path": photo_path,
                    })

                    try:
                        upload.file.seek(0)
                    except Exception:
                        pass
                else:
                    extension = guess_media_extension(upload, default='.mp4')
                    if not extension.startswith('.'):
                        extension = f'.{extension}'

                    video_path = os.path.join(temp_dir, f'media_{index}{extension}')
                    save_upload_file(upload, video_path)
                    media_payload.append({
                        "type": "video",
                        "path": video_path,
                    })
            
            # Отправляем уведомление в группу с message_thread_id (в отдельную тему)
            try:
                await send_media_to_telegram_group(
                    bot_token=BOT_TOKEN,
                    chat_id=TROPHY_GROUP_CHAT_ID,
                    media_items=media_payload,
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


@app.delete("/api/users/{user_id}")
async def delete_user_data_endpoint(
    user_id: int,
    authorization: Optional[str] = Header(None),
):
    """
    Удаляет все данные пользователя (профиль, билды, трофеи).
    Вызывается ботом при выходе пользователя из группы.
    """
    if not verify_bot_authorization(authorization):
        raise HTTPException(status_code=401, detail="Неавторизованный запрос")

    try:
        success = delete_user_all_data(DB_PATH, user_id)
        if not success:
            raise HTTPException(status_code=404, detail="Пользователь не найден")
        return {"status": "ok", "user_id": user_id}
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при удалении данных пользователя: {error}",
        )


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
    
    # Загружаем конфиг для получения информации о категории
    try:
        config = load_mastery_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки конфига: {str(e)}")
    
    # Находим категорию в конфиге
    category = find_category_by_key(config, category_key)
    if not category:
        raise HTTPException(status_code=400, detail=f"Категория {category_key} не найдена в конфиге")
    
    # Обновляем уровень в БД (записываем current_level + 1)
    new_level = current_level + 1
    success = set_mastery(DB_PATH, user_id, category_key, new_level)
    if not success:
        raise HTTPException(status_code=500, detail="Ошибка обновления уровня в БД")
    
    # Проверяем, достиг ли пользователь максимального уровня, и если да - начисляем трофей
    max_levels = category.get('maxLevels', 0)
    if new_level >= max_levels and max_levels > 0:
        # Пользователь достиг максимального уровня - начисляем трофей
        add_trophy(DB_PATH, user_id, category_key)
    
    # Получаем информацию о пользователе
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(status_code=404, detail="Профиль пользователя не найден")
    
    psn_id = user_profile.get('psn_id', '')
    username = user_profile.get('real_name', '')
    avatar_url = user_profile.get('avatar_url', '')

    # Находим уровень в конфиге
    level_data = None
    for level in category.get('levels', []):
        if level.get('level') == next_level:
            level_data = level
            break
    
    category_name = category.get('name', category_key)
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
    
    # Логируем событие повышения уровня мастерства
    try:
        log_recent_event(
            DB_PATH,
            event_type='mastery_upgrade',
            user_id=user_id,
            psn_id=psn_id,
            avatar_url=avatar_url,
            payload={
                'category_key': category_key,
                'category_name': category_name,
                'level': new_level,
                'level_name': level_name,
                'moderator': moderator_username,
            }
        )
    except Exception as log_error:
        print(f"Не удалось логировать событие мастерства: {log_error}")
    
    return {
        "status": "ok",
        "success": True,
        "category_name": category_name,
        "level_name": level_name,
        "psn_id": psn_id,
        "username": username,
        "user_id": user_id
    }


@app.post("/api/trophy.approve")
async def approve_trophy_application(
    user_id: int = Form(...),
    trophy_key: str = Form(...),
    moderator_username: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    """
    Одобряет заявку на получение трофея.
    Вызывается ботом при нажатии кнопки "Одобрить".
    """
    # Проверка авторизации бота
    if not verify_bot_authorization(authorization):
        raise HTTPException(status_code=401, detail="Неавторизованный запрос")
    
    # Загружаем конфиг трофеев
    try:
        config = load_trophy_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки конфига: {str(e)}")
    
    # Находим трофей в конфиге
    trophy = find_trophy_by_key(config, trophy_key)
    if not trophy:
        raise HTTPException(status_code=400, detail=f"Трофей {trophy_key} не найден в конфиге")
    
    trophy_name = trophy.get('name', trophy_key)
    
    # Проверяем, не получен ли уже трофей
    user_trophies_data = get_trophies(DB_PATH, user_id)
    user_trophies = set(user_trophies_data.get('trophies', []))
    if trophy_key in user_trophies:
        raise HTTPException(
            status_code=400,
            detail="Этот трофей уже получен пользователем"
        )
    
    # Добавляем трофей
    success = add_trophy(DB_PATH, user_id, trophy_key)
    if not success:
        raise HTTPException(status_code=500, detail="Ошибка добавления трофея в БД")
    
    # Получаем информацию о пользователе
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(status_code=404, detail="Профиль пользователя не найден")
    
    psn_id = user_profile.get('psn_id', '')
    username = user_profile.get('real_name', '')
    avatar_url = user_profile.get('avatar_url', '')
    
    # Отправляем уведомление пользователю в личку
    try:
        user_notification = f"""✅ <b>Ваша заявка на получение трофея была одобрена!</b>

🏅 <b>Трофей:</b> {trophy_name}

Теперь этот трофей доступен в вашей коллекции на странице "Награды"."""
        
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
        "trophy_name": trophy_name,
        "psn_id": psn_id,
        "username": username,
        "user_id": user_id
    }


@app.get("/api/events.recent")
async def get_recent_events_feed(
    limit: int = Query(3, ge=1, le=10),
    user_id: int = Depends(get_current_user)
):
    """
    Возвращает последние события наград/мастерства для отображения на главной странице.
    """
    raw_events = get_recent_events(DB_PATH, limit)

    def build_event_view(event: Dict[str, Any]) -> Dict[str, Any]:
        event_type = event.get('event_type')
        payload = event.get('payload') or {}
        psn_id = event.get('psn_id') or 'Игрок'

        headline = ''
        details = ''
        icon_key = ''

        if event_type == 'mastery_upgrade':
            category_name = payload.get('category_name') or payload.get('category_key') or 'Мастерство'
            level_name = payload.get('level_name') or f"Уровень {payload.get('level')}" if payload.get('level') else ''
            headline = f"{psn_id} повысил(а) уровень в категории «{category_name}»"
            details = level_name or 'Новый уровень подтверждён модераторами'
            icon_key = payload.get('category_key') or 'mastery'
        elif event_type == 'trophy_award':
            trophy_name = payload.get('trophy_name') or payload.get('trophy_key') or 'Трофей'
            headline = f"{psn_id} получил(а) трофей «{trophy_name}»"
            details = 'Добавлен в коллекцию'
            icon_key = payload.get('trophy_key') or 'trophy'
        else:
            headline = f"{psn_id} получил(а) новую награду"
            details = ''
            icon_key = 'reward'

        return {
            "event_id": event.get('event_id'),
            "event_type": event_type,
            "user_id": event.get('user_id'),
            "psn_id": event.get('psn_id'),
            "avatar_url": event.get('avatar_url'),
            "created_at": event.get('created_at'),
            "icon_key": icon_key,
            "headline": headline,
            "details": details,
            "payload": payload,
        }

    events = [build_event_view(evt) for evt in raw_events]
    return {"events": events}


@app.get("/api/comments.recent")
async def get_recent_comments_feed(
    limit: int = Query(3, ge=1, le=10),
    user_id: int = Depends(get_current_user)
):
    """
    Возвращает последние комментарии к билдам.
    """
    raw_comments = get_recent_comments(DB_PATH, limit)

    def build_comment_view(comment: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "comment_id": comment.get("comment_id"),
            "build_id": comment.get("build_id"),
            "build_name": comment.get("build_name"),
            "build_class": comment.get("build_class"),
            "user_id": comment.get("user_id"),
            "psn_id": comment.get("psn_id"),
            "avatar_url": comment.get("avatar_url"),
            "comment_text": comment.get("comment_text"),
            "created_at": comment.get("created_at"),
        }

    comments = [build_comment_view(c) for c in raw_comments]
    return {"comments": comments}


@app.post("/api/trophy.reject")
async def reject_trophy_application(
    user_id: int = Form(...),
    trophy_key: str = Form(...),
    reason: str = Form(...),
    moderator_username: str = Form(...),
    authorization: Optional[str] = Header(None)
):
    """
    Отклоняет заявку на получение трофея.
    Вызывается ботом после получения причины отклонения от модератора.
    """
    # Проверка авторизации бота
    if not verify_bot_authorization(authorization):
        raise HTTPException(status_code=401, detail="Неавторизованный запрос")
    
    # Получаем информацию о пользователе
    user_profile = get_user(DB_PATH, user_id)
    if not user_profile:
        raise HTTPException(status_code=404, detail="Профиль пользователя не найден")
    
    # Загружаем конфиг для получения названия
    try:
        config = load_trophy_config()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки конфига: {str(e)}")
    
    # Находим трофей в конфиге
    trophy = find_trophy_by_key(config, trophy_key)
    trophy_name = trophy.get('name', trophy_key) if trophy else trophy_key
    
    # Отправляем уведомление пользователю в личку
    try:
        user_notification = f"""❌ <b>К сожалению, ваша заявка на получение трофея была отклонена.</b>

🏅 <b>Трофей:</b> {trophy_name}

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
        "trophy_name": trophy_name
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


# ========== API ЭНДПОИНТЫ ДЛЯ ТРОФЕЕВ ==========

@app.get("/api/trophies.get")
async def get_trophies_endpoint(
    target_user_id: Optional[int] = Query(default=None, description="ID пользователя, для которого нужно получить трофеи"),
    user_id: int = Depends(get_current_user)
):
    """
    Получает трофеи текущего пользователя.
    
    Args:
        user_id: ID пользователя (из dependency)
    
    Returns:
        JSON с данными трофеев: {
            "trophies": List[str],  # Список всех трофеев
            "active_trophies": List[str]  # Список активных трофеев
        }
    """
    try:
        target_id = target_user_id or user_id
        trophies_data = get_trophies(DB_PATH, target_id)
        return {
            "status": "ok",
            "trophies": trophies_data.get('trophies', []),
            "active_trophies": trophies_data.get('active_trophies', [])
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения трофеев: {str(e)}"
        )


@app.get("/api/trophies.list")
async def get_trophies_list(user_id: int = Depends(get_current_user)):
    """
    Получает список всех доступных трофеев из конфига.
    
    Args:
        user_id: ID пользователя (из dependency, для проверки авторизации)
    
    Returns:
        JSON со списком всех трофеев из конфига
    """
    try:
        config = load_trophy_config()
        trophies_list = config.get('trophies', [])
        
        # Получаем трофеи пользователя для отметки полученных
        user_trophies_data = get_trophies(DB_PATH, user_id)
        user_trophies = set(user_trophies_data.get('trophies', []))
        
        # Отмечаем какие трофеи получены
        for trophy in trophies_list:
            trophy_key = trophy.get('key')
            trophy['obtained'] = trophy_key in user_trophies if trophy_key else False
        
        return {
            "status": "ok",
            "trophies": trophies_list
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка получения списка трофеев: {str(e)}"
        )


@app.post("/api/trophy.submit")
async def submit_trophy_application(
    user_id: int = Depends(get_current_user),
    trophy_key: str = Form(...),
    comment: Optional[str] = Form(default=None),
    photos: Optional[List[UploadFile]] = File(default=None)
):
    """
    Отправляет заявку на получение трофея в админскую группу.
    """
    # Получаем профиль пользователя для получения psn_id
    user_profile, psn_id = get_user_with_psn(DB_PATH, user_id)
    
    # Загружаем конфиг трофеев
    try:
        config = load_trophy_config()
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка загрузки конфига трофеев: {str(e)}"
        )
    
    # Находим трофей в конфиге
    trophy = find_trophy_by_key(config, trophy_key)
    
    if not trophy:
        raise HTTPException(
            status_code=400,
            detail=f"Трофей {trophy_key} не найден в конфиге"
        )
    
    # Проверяем, не получен ли уже трофей
    user_trophies_data = get_trophies(DB_PATH, user_id)
    user_trophies = set(user_trophies_data.get('trophies', []))
    if trophy_key in user_trophies:
        raise HTTPException(
            status_code=400,
            detail="Этот трофей уже получен"
        )
    
    # Валидация
    media_files = photos or []

    if len(media_files) == 0:
        raise HTTPException(
            status_code=400,
            detail="Необходимо прикрепить хотя бы один файл (изображение или видео)"
        )
    
    if len(media_files) > MAX_MEDIA_ATTACHMENTS:
        raise HTTPException(
            status_code=400,
            detail=f"Можно прикрепить не более {MAX_MEDIA_ATTACHMENTS} файлов"
        )
    
    normalized_media = []
    for upload in media_files:
        media_kind = detect_media_type(upload)
        if media_kind not in {'photo', 'video'}:
            raise HTTPException(
                status_code=400,
                detail="Разрешены только изображения и видео (MP4, MOV)."
            )
        normalized_media.append((upload, media_kind))
    
    # Формируем сообщение для группы
    trophy_name = trophy.get('name', trophy_key)
    trophy_description = trophy.get('description', '')
    trophy_proof = trophy.get('proof', '')
    
    comment_text = comment.strip() if comment and comment.strip() else "Без комментария"
    
    message_text = f"""🏆 <b>Заявка на получение трофея</b>

👤 <b>PSN ID:</b> {psn_id}
🏅 <b>Трофей:</b> {trophy_name}
📝 <b>Описание:</b>
{trophy_description}

📸 <b>Требуемые доказательства:</b>
{trophy_proof}

💬 <b>Комментарий:</b> {comment_text}"""
    
    # Создаем inline кнопки
    reply_markup = {
        "inline_keyboard": [
            [
                {
                    "text": "Одобрить",
                    "callback_data": f"approve_trophy:{user_id}:{trophy_key}"
                },
                {
                    "text": "Отклонить",
                    "callback_data": f"reject_trophy:{user_id}:{trophy_key}"
                }
            ]
        ]
    }
    
    # Обрабатываем и отправляем фотографии
    try:
        with temp_image_directory(prefix='trophy_app_') as temp_dir:
            media_payload = []
            
            for index, (upload, media_kind) in enumerate(normalized_media, start=1):
                if media_kind == 'photo':
                    try:
                        upload.file.seek(0)
                    except Exception:
                        pass

                    photo_path = os.path.join(temp_dir, f'media_{index}.jpg')
                    image = Image.open(upload.file)
                    process_image_for_upload(image, photo_path)
                    media_payload.append({
                        "type": "photo",
                        "path": photo_path,
                    })

                    try:
                        upload.file.seek(0)
                    except Exception:
                        pass
                else:
                    extension = guess_media_extension(upload, default='.mp4')
                    if not extension.startswith('.'):
                        extension = f'.{extension}'

                    video_path = os.path.join(temp_dir, f'media_{index}{extension}')
                    save_upload_file(upload, video_path)
                    media_payload.append({
                        "type": "video",
                        "path": video_path,
                    })
            
            # Отправляем уведомление в группу с message_thread_id (в отдельную тему)
            try:
                await send_media_to_telegram_group(
                    bot_token=BOT_TOKEN,
                    chat_id=TROPHY_GROUP_CHAT_ID,
                    media_items=media_payload,
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


@app.post("/api/trophies.updateActive")
async def update_active_trophies_endpoint(
    user_id: int = Depends(get_current_user),
    active_trophies: List[str] = Form(default=[])
):
    """
    Обновляет список активных трофеев пользователя (максимум 8).
    
    Args:
        user_id: ID пользователя (из dependency)
        active_trophies: Список активных трофеев (максимум 8)
    
    Returns:
        JSON с результатом операции
    """
    try:
        # Валидация: максимум 8 трофеев
        if len(active_trophies) > 8:
            raise HTTPException(
                status_code=400,
                detail="Можно выбрать максимум 8 активных трофеев"
            )
        
        # Обновляем активные трофеи
        success = update_active_trophies(DB_PATH, user_id, active_trophies)
        
        if not success:
            raise HTTPException(
                status_code=500,
                detail="Ошибка обновления активных трофеев"
            )
        
        return {
            "status": "ok",
            "message": "Активные трофеи успешно обновлены"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка обновления активных трофеев: {str(e)}"
        )


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
    trophies_data = get_trophies(DB_PATH, user_id)
    
    # Загружаем конфиг мастерства
    try:
        mastery_config = load_mastery_config()
    except Exception as e:
        print(f"Ошибка загрузки конфига мастерства: {e}")
        mastery_config = None

    try:
        trophy_config = load_trophy_config()
    except Exception as e:
        print(f"Ошибка загрузки конфига трофеев: {e}")
        trophy_config = None
    
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
        "mastery_config": mastery_config,
        "trophies": trophies_data
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
    
    # Генерируем визуальное представление мастерства
    mastery_tiles_html: list[str] = []
    categories_by_key: dict[str, Any] = {}
    if mastery_config and isinstance(mastery_config, dict):
        categories_by_key = {
            cat.get('key'): cat for cat in mastery_config.get('categories', []) if isinstance(cat, dict)
        }

    category_order = ['solo', 'hellmode', 'raid', 'speedrun', 'glitch']
    if mastery_levels:
        for extra_key in mastery_levels.keys():
            if extra_key not in category_order:
                category_order.append(extra_key)

    for category_key in category_order:
        category = categories_by_key.get(category_key, {})
        max_levels = category.get('maxLevels', 0) or 0
        current_level = mastery_levels.get(category_key, 0) if mastery_levels else 0

        classes: list[str] = ["mastery-tile"]
        progress_ratio = 0.0

        if max_levels > 0:
            progress_ratio = min(max(current_level / max_levels, 0.0), 1.0)
            if current_level >= max_levels:
                classes.append("maxed")
                progress_ratio = 1.0
            elif current_level > 0:
                classes.append("partial")
        elif current_level > 0:
            progress_ratio = 1.0
            classes.append("maxed")

        if current_level <= 0:
            classes.append("locked")

        icon_path = f"{ASSETS_PREFIX}/mastery/{category_key}/icon.svg"
        tile_inner = (
            f'<div class="mastery-ring" data-progress="{progress_ratio:.4f}" style="--progress: {progress_ratio:.4f};"></div>'
            f'<div class="mastery-icon" style="background-image: url(\'{icon_path}\');"></div>'
        )
        mastery_tiles_html.append(
            f'<div class="{' '.join(classes)}">{tile_inner}</div>'
        )

    mastery_tiles_html = [tile for tile in mastery_tiles_html if tile]
    if not mastery_tiles_html:
        mastery_tiles_html.append('<div class="mastery-empty">—</div>')

    mastery_grid_placeholder = '<div id="mastery-grid" class="mastery-grid"></div>'
    mastery_grid_html = ''.join(mastery_tiles_html)
    html_content = html_content.replace(
        mastery_grid_placeholder,
        f'<div id="mastery-grid" class="mastery-grid">{mastery_grid_html}</div>'
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
    
    trophies_list = trophies_data.get('trophies', []) if trophies_data else []
    mastery_trophy_keys = {'solo', 'hellmode', 'raid', 'speedrun', 'glitch'}
    filtered_trophies = [key for key in trophies_list if key not in mastery_trophy_keys]

    trophy_tiles: list[str] = []
    all_trophies: list[dict] = []
    if trophy_config and isinstance(trophy_config, dict):
        all_trophies = trophy_config.get('trophies', []) or []

    earned_set = set(filtered_trophies)

    for trophy in all_trophies:
        key = trophy.get('key')
        if not key:
            continue
        trophy_name = trophy.get('name', key)
        icon_path = f"{ASSETS_PREFIX}/trophies/{key}.svg"
        classes = ["trophy-card"]
        if key not in earned_set:
            classes.append("trophy-card--locked")
        trophy_tiles.append(
            f'<div class="{' '.join(classes)}"><img src="{icon_path}" alt="{html.escape(str(trophy_name))}" /></div>'
        )

    if not trophy_tiles:
        trophy_tiles.append('<div class="mastery-empty">—</div>')

    trophy_grid_placeholder = '<div id="v_trophies" class="value lines">—</div>'
    trophy_grid_html = ''.join(trophy_tiles)
    html_content = html_content.replace(
        trophy_grid_placeholder,
        f'<div id="trophy-grid" class="trophy-grid">{trophy_grid_html}</div>'
    )

    # Добавляем скрипт для сигнала готовности (данные уже заполнены)
    script_replacement = """
        <script>
            // Данные уже заполнены в HTML, просто сигнализируем готовность
            (function() {
                const readyEl = document.getElementById('trophy-grid');
                if (readyEl) {
                    readyEl.setAttribute('data-ready', 'true');
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
                viewport={"width": 375, "height": 1600},
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


async def screenshot_waves(base_url: str = "http://localhost:8000") -> bytes:
    """
    Создает скриншот страницы волн через Playwright.
    """
    base = base_url.rstrip("/") or "http://localhost:8000"
    url = f"{base}/waves-preview"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        try:
            context = await browser.new_context(
                viewport={"width": 375, "height": 812},
                device_scale_factor=2,
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15"
            )

            page = await context.new_page()

            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)

                try:
                    await page.wait_for_function(
                        """
                        () => {
                            const readyEl = document.getElementById('waves-ready');
                            return readyEl && readyEl.getAttribute('data-ready') === 'true';
                        }
                        """,
                        timeout=10000
                    )
                    await page.wait_for_timeout(300)
                except Exception as wait_exc:
                    print(f"Warning: Timeout waiting for waves ready marker: {wait_exc}")
                    await page.wait_for_timeout(1500)

                content_height = await page.evaluate(
                    """
                    () => {
                        const main = document.querySelector('main.container');
                        if (!main) {
                            return Math.ceil(
                                document.documentElement.scrollHeight
                                || document.body.scrollHeight
                                || 1200
                            );
                        }
                        const rect = main.getBoundingClientRect();
                        return Math.ceil(rect.bottom + 24);
                    }
                    """
                )

                if not isinstance(content_height, (int, float)):
                    content_height = 1200
                content_height = int(max(640, min(content_height, 2000)))

                await page.set_viewport_size({"width": 375, "height": content_height})

                screenshot_bytes = await page.screenshot(type="png")
                return screenshot_bytes

            finally:
                await page.close()
                await context.close()

        finally:
            await browser.close()


async def send_photo_to_telegram(
    chat_id: str,
    photo_buffer: bytes,
    caption: str = "",
    message_thread_id: Optional[int] = None,
) -> dict:
    """
    Отправляет фото в Telegram через Bot API.
    """
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    form = aiohttp.FormData()
    form.add_field("chat_id", chat_id)
    form.add_field("caption", caption)
    form.add_field("parse_mode", "HTML")
    if message_thread_id is not None:
        form.add_field("message_thread_id", str(message_thread_id))
    form.add_field(
        "photo",
        io.BytesIO(photo_buffer),
        filename="screenshot.png",
        content_type="image/png",
    )

    timeout = aiohttp.ClientTimeout(total=20, connect=5)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, data=form) as response:
            if response.status >= 400:
                text = await response.text()
                raise HTTPException(
                    status_code=response.status,
                    detail=f"Telegram API error: {text}",
                )
            return await response.json()


@app.post("/api/send_profile/{user_id}")
async def send_profile_screenshot(
    user_id: int,
    chat_id: str = Query(..., description="ID чата для отправки фото"),
    message_thread_id: Optional[int] = Query(None, description="ID темы (если есть)"),
    base_url: Optional[str] = Query(None, description="Базовый URL сервера для скриншота"),
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
        internal_base_url = base_url or os.getenv("SCREENSHOT_BASE_URL", "http://localhost:8000")
        
        # Проверяем существование профиля
        profile = get_user(DB_PATH, user_id)
        if not profile:
            raise HTTPException(status_code=404, detail="Профиль не найден")
        
        # Создаем скриншот
        screenshot_bytes = await screenshot_profile(user_id, internal_base_url)
        
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


@app.post("/api/send_waves")
async def send_waves_screenshot(
    chat_id: str = Query(..., description="ID чата для отправки фото"),
    message_thread_id: Optional[int] = Query(None, description="ID темы (если есть)"),
    base_url: Optional[str] = Query(None, description="Базовый URL сервера для скриншота"),
):
    """
    Создает скриншот текущей ротации волн и отправляет его в Telegram.
    """
    try:
        waves_data = _read_waves_json()

        internal_base_url = base_url or os.getenv("SCREENSHOT_BASE_URL", "http://localhost:8000")
        screenshot_bytes = await screenshot_waves(internal_base_url)

        caption_parts: List[str] = []
        map_name = waves_data.get("map")
        if map_name:
            caption_parts.append(f"🗺 <b>{html.escape(str(map_name))}</b>")

        week_caption = _format_week_title(waves_data.get("week"), waves_data.get("absolute_week"))
        if week_caption and week_caption != "Волны":
            caption_parts.append(f"📅 {html.escape(week_caption)}")

        caption = "\n".join(caption_parts) if caption_parts else "🌊 Текущая ротация волн"

        result = await send_photo_to_telegram(
            chat_id=chat_id,
            photo_buffer=screenshot_bytes,
            caption=caption,
            message_thread_id=message_thread_id
        )

        return {
            "status": "ok",
            "message": "Скриншот волн успешно отправлен",
            "telegram_result": result
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"Ошибка при создании и отправке скриншота волн: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при создании скриншота волн: {str(e)}"
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
