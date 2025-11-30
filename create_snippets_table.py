#!/usr/bin/env python3
# create_snippets_table.py
# Миграционный скрипт для создания таблицы snippets

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_snippets_table():
    """
    Создает таблицу snippets для хранения сниппетов пользователей.
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
            WHERE type='table' AND name='snippets'
        """)
        
        if cursor.fetchone():
            print("Таблица snippets уже существует.")
            return
        
        print("Создаем таблицу snippets...")
        
        # Создаем таблицу snippets
        cursor.execute("""
            CREATE TABLE snippets (
                snippet_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                trigger TEXT NOT NULL UNIQUE,
                message TEXT NOT NULL,
                media TEXT,
                media_type TEXT,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        # Создаем индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX idx_snippets_user_id ON snippets(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX idx_snippets_trigger ON snippets(trigger)
        """)
        
        print("Таблица snippets создана с индексами.")
        
        conn.commit()
        print("Миграция успешно завершена!")
        
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
    print("Запуск миграции таблицы snippets...")
    create_snippets_table()

