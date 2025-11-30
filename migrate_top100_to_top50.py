#!/usr/bin/env python3
# migrate_top100_to_top50.py
# Миграционный скрипт для переименования таблицы top100_current_prize в top50_current_prize

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def migrate_top100_to_top50():
    """
    Переименовывает таблицу top100_current_prize в top50_current_prize.
    Переносит данные из старой таблицы в новую.
    """
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли старая таблица
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='top100_current_prize'
        """)
        
        if not cursor.fetchone():
            print("Таблица top100_current_prize не найдена. Миграция не требуется.")
            return
        
        # Проверяем, существует ли уже новая таблица
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='top50_current_prize'
        """)
        
        if cursor.fetchone():
            print("Таблица top50_current_prize уже существует. Миграция уже выполнена.")
            return
        
        print("Начинаем миграцию top100_current_prize → top50_current_prize...")
        
        # Получаем данные из старой таблицы
        cursor.execute('SELECT value FROM top100_current_prize LIMIT 1')
        row = cursor.fetchone()
        old_value = row[0] if row else None
        
        # Создаем новую таблицу
        cursor.execute("""
            CREATE TABLE top50_current_prize (
                value INTEGER NOT NULL
            )
        """)
        
        print("Таблица top50_current_prize создана.")
        
        # Переносим данные
        if old_value is not None:
            cursor.execute('INSERT INTO top50_current_prize (value) VALUES (?)', (old_value,))
            print(f"Данные перенесены: value = {old_value}")
        else:
            # Если данных нет, создаем запись с значением по умолчанию
            cursor.execute('INSERT INTO top50_current_prize (value) VALUES (?)', (0,))
            print("Создана запись со значением по умолчанию: value = 0")
        
        conn.commit()
        print("Миграция успешно завершена!")
        print("ВНИМАНИЕ: Старая таблица top100_current_prize все еще существует.")
        print("Вы можете удалить её вручную после проверки работы новой таблицы.")
        
    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        import traceback
        traceback.print_exc()
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Запуск миграции таблицы top100_current_prize → top50_current_prize...")
    migrate_top100_to_top50()






