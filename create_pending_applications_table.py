#!/usr/bin/env python3
# create_pending_applications_table.py
# Миграционный скрипт для создания таблицы pending_applications

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_pending_applications_table():
    """
    Создает таблицу pending_applications для отслеживания ожидающих заявок.
    """
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='pending_applications'
        """)
        
        if cursor.fetchone():
            print("Таблица pending_applications уже существует.")
            return
        
        print("Создаем таблицу pending_applications...")
        
        # Создаем таблицу pending_applications
        cursor.execute("""
            CREATE TABLE pending_applications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                application_type TEXT NOT NULL,
                target_key TEXT NOT NULL,
                target_level INTEGER,
                created_at INTEGER NOT NULL,
                UNIQUE(user_id, application_type, target_key, target_level)
            )
        """)
        
        # Создаем индекс для быстрого поиска по user_id
        cursor.execute("""
            CREATE INDEX idx_pending_applications_user_id 
            ON pending_applications(user_id)
        """)
        
        conn.commit()
        print("Таблица pending_applications успешно создана!")
        
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
    print("Запуск миграции таблицы pending_applications...")
    create_pending_applications_table()

