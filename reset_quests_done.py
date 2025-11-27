#!/usr/bin/env python3
# reset_quests_done.py
# Скрипт для автоматического сброса выполненных заданий каждую субботу в 9:00 МСК

import os
import sys
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

# Добавляем путь к модулю db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import reset_weekly_quests
from typing import Optional

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")

# Для отслеживания времени последнего сброса создадим отдельную таблицу
def get_last_reset_time(db_path: str) -> Optional[float]:
    """
    Получает timestamp последнего сброса заданий.
    
    Returns:
        Timestamp последнего сброса или None
    """
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу если не существует
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quests_reset_log (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_reset_timestamp INTEGER
            )
        ''')
        
        cursor.execute('SELECT last_reset_timestamp FROM quests_reset_log WHERE id = 1')
        row = cursor.fetchone()
        
        conn.close()
        
        if row:
            return float(row[0])
        return None
        
    except Exception as e:
        print(f"Ошибка получения времени последнего сброса: {e}")
        return None


def set_last_reset_time(db_path: str, timestamp: float) -> bool:
    """
    Устанавливает timestamp последнего сброса заданий.
    
    Returns:
        True если успешно, иначе False
    """
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO quests_reset_log (id, last_reset_timestamp)
            VALUES (1, ?)
        ''', (int(timestamp),))
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        print(f"Ошибка установки времени последнего сброса: {e}")
        return False


def should_reset_quests() -> bool:
    """
    Проверяет, нужно ли сбрасывать задания.
    Сброс происходит каждую субботу в 9:00 МСК (UTC+3).
    
    Returns:
        True если нужно сбросить задания, иначе False
    """
    # Текущее время в UTC
    now_utc = datetime.now(timezone.utc)
    
    # Московское время (UTC+3)
    moscow_tz = timezone(timedelta(hours=3))
    now_moscow = now_utc.astimezone(moscow_tz)
    
    # Проверяем, что сегодня суббота (weekday() = 5)
    if now_moscow.weekday() != 5:  # 5 = суббота
        return False
    
    # Проверяем, что время 9:00 или позже
    if now_moscow.hour < 9:
        return False
    
    # Получаем последнее время сброса из БД
    last_reset_timestamp = get_last_reset_time(DB_PATH)
    if last_reset_timestamp is None:
        # Если не удалось получить информацию, все равно проверяем время
        # Если сейчас суббота 9:00 или позже, разрешаем сброс
        return True
    
    last_reset = datetime.fromtimestamp(last_reset_timestamp, tz=timezone.utc)
    last_reset_moscow = last_reset.astimezone(moscow_tz)
    
    # Проверяем, что с последнего сброса прошла хотя бы одна суббота 9:00
    # Если последнее обновление было раньше сегодняшней субботы 9:00, сбрасываем
    saturday_09 = now_moscow.replace(hour=9, minute=0, second=0, microsecond=0)
    
    if last_reset_moscow < saturday_09:
        return True
    
    return False


def main():
    """
    Главная функция скрипта.
    """
    try:
        # Проверяем, нужно ли сбрасывать
        if should_reset_quests():
            print("Сброс выполненных заданий...")
            if reset_weekly_quests(DB_PATH):
                # Устанавливаем время последнего сброса
                current_timestamp = datetime.now(timezone.utc).timestamp()
                set_last_reset_time(DB_PATH, current_timestamp)
                print("Задания успешно сброшены")
            else:
                print("Ошибка: не удалось сбросить задания")
                sys.exit(1)
        else:
            print("Сброс не требуется")
    
    except Exception as e:
        print(f"Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

