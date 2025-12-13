# user_utils.py
# Утилиты для работы с пользователями

from fastapi import HTTPException
from typing import Dict, Tuple, Optional
from db import get_user


def get_user_with_psn(DB_PATH: str, user_id: int) -> Tuple[Dict, str]:
    """
    Получает профиль пользователя с проверкой PSN ID.
    
    Args:
        DB_PATH: Путь к базе данных
        user_id: ID пользователя
    
    Returns:
        Кортеж (user_profile, psn_id)
    
    Raises:
        HTTPException: Если профиль не найден или PSN ID не указан
    """
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
    
    return user_profile, psn_id


def format_profile_response(profile: Optional[Dict], user_id: int) -> Dict:
    """
    Форматирует ответ профиля пользователя.
    
    Убирает служебные поля из ответа и возвращает стандартизированный формат.
    
    Args:
        profile: Словарь с данными профиля из БД
        user_id: ID пользователя
    
    Returns:
        Словарь с данными профиля для ответа API
    """
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Профиль не найден"
        )
    
    return {
        "user_id": user_id,
        "real_name": profile.get("real_name", ""),
        "psn_id": profile.get("psn_id", ""),
        "platforms": profile.get("platforms", []),
        "modes": profile.get("modes", []),
        "goals": profile.get("goals", []),
        "difficulties": profile.get("difficulties", []),
        "birthday": profile.get("birthday"),
        "avatar_url": profile.get("avatar_url"),
        "balance": profile.get("balance", 0),
        "purified": profile.get("purified", 0),
        "active_theme_key": profile.get("active_theme_key", "default")
    }

