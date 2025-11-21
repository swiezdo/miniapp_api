#!/usr/bin/env python3
# update_rotation_week.py
# Скрипт для автоматического обновления недели ротации каждую пятницу в 18:00 МСК

import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Добавляем путь к модулю db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_current_rotation_week, update_rotation_week, get_rotation_week_info

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")

def should_update_week() -> bool:
    """
    Проверяет, нужно ли обновлять неделю.
    Обновление происходит каждую пятницу в 18:00 МСК (UTC+3).
    
    Returns:
        True если нужно обновить неделю, иначе False
    """
    # Текущее время в UTC
    now_utc = datetime.now(timezone.utc)
    
    # Московское время (UTC+3)
    moscow_tz = timezone(timedelta(hours=3))
    now_moscow = now_utc.astimezone(moscow_tz)
    
    # Проверяем, что сегодня пятница (weekday() = 4)
    if now_moscow.weekday() != 4:  # 4 = пятница
        return False
    
    # Проверяем, что время 18:00 или позже
    if now_moscow.hour < 18:
        return False
    
    # Получаем последнее время обновления из БД
    week_info = get_rotation_week_info(DB_PATH)
    if not week_info:
        # Если не удалось получить информацию, все равно обновляем
        return True
    
    last_updated_timestamp = week_info['last_updated']
    last_updated = datetime.fromtimestamp(last_updated_timestamp, tz=timezone.utc)
    last_updated_moscow = last_updated.astimezone(moscow_tz)
    
    # Проверяем, что с последнего обновления прошла хотя бы одна пятница 18:00
    # Если последнее обновление было раньше сегодняшней пятницы 18:00, обновляем
    friday_18 = now_moscow.replace(hour=18, minute=0, second=0, microsecond=0)
    
    if last_updated_moscow < friday_18:
        return True
    
    return False


def main():
    """
    Главная функция скрипта.
    """
    try:
        # Получаем текущую неделю
        current_week = get_current_rotation_week(DB_PATH)
        
        if current_week is None:
            print("Ошибка: не удалось получить текущую неделю из БД")
            sys.exit(1)
        
        print(f"Текущая неделя: {current_week}")
        
        # Проверяем, нужно ли обновлять
        if should_update_week():
            print("Обновление недели ротации...")
            if update_rotation_week(DB_PATH):
                new_week = get_current_rotation_week(DB_PATH)
                print(f"Неделя успешно обновлена. Новая неделя: {new_week}")
            else:
                print("Ошибка: не удалось обновить неделю")
                sys.exit(1)
        else:
            print("Обновление не требуется")
    
    except Exception as e:
        print(f"Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

