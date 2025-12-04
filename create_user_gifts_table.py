#!/usr/bin/env python3
# create_user_gifts_table.py
# Миграционный скрипт для создания таблицы user_gifts

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_user_gifts_table():
    """
    Создает таблицу user_gifts для хранения подарков пользователей.
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
            WHERE type='table' AND name='user_gifts'
        """)
        
        if cursor.fetchone():
            print("Таблица user_gifts уже существует.")
            return
        
        print("Создаем таблицу user_gifts...")
        
        # Создаем таблицу user_gifts
        cursor.execute("""
            CREATE TABLE user_gifts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id INTEGER NOT NULL,
                sender_id INTEGER NOT NULL,
                gift_key TEXT NOT NULL,
                created_at INTEGER DEFAULT (strftime('%s', 'now')),
                FOREIGN KEY (recipient_id) REFERENCES users(user_id),
                FOREIGN KEY (sender_id) REFERENCES users(user_id)
            )
        """)
        
        # Создаем индексы для быстрого поиска
        cursor.execute("""
            CREATE INDEX idx_user_gifts_recipient ON user_gifts(recipient_id)
        """)
        cursor.execute("""
            CREATE INDEX idx_user_gifts_sender ON user_gifts(sender_id)
        """)
        
        print("Таблица user_gifts создана.")
        
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
    print("Запуск миграции таблицы user_gifts...")
    create_user_gifts_table()

