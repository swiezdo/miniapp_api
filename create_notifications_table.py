#!/usr/bin/env python3
# create_notifications_table.py
# Миграционный скрипт для создания таблицы notifications и переноса данных из users

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_notifications_table():
    """
    Создает таблицу notifications и переносит данные из users.
    Для существующих пользователей все поля уведомлений устанавливаются в 0.
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
            WHERE type='table' AND name='notifications'
        """)
        
        if cursor.fetchone():
            print("Таблица notifications уже существует.")
            return
        
        print("Создаем таблицу notifications...")
        
        # Создаем таблицу notifications
        cursor.execute("""
            CREATE TABLE notifications (
                user_id INTEGER PRIMARY KEY,
                psn_id TEXT,
                [check] INTEGER DEFAULT 0,
                speedrun INTEGER DEFAULT 0,
                raid INTEGER DEFAULT 0,
                ghost INTEGER DEFAULT 0,
                hellmode INTEGER DEFAULT 0,
                story INTEGER DEFAULT 0,
                rivals INTEGER DEFAULT 0,
                trials INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        
        print("Таблица notifications создана.")
        
        # Переносим данные из users
        cursor.execute("""
            SELECT user_id, psn_id FROM users
        """)
        
        users = cursor.fetchall()
        print(f"Найдено {len(users)} пользователей для переноса.")
        
        # Вставляем данные для всех существующих пользователей с нулями в полях уведомлений
        for user_id, psn_id in users:
            cursor.execute("""
                INSERT INTO notifications (user_id, psn_id, [check], speedrun, raid, ghost, hellmode, story, rivals, trials)
                VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0)
            """, (user_id, psn_id or ''))
        
        print(f"Данные для {len(users)} пользователей перенесены. Все поля уведомлений установлены в 0.")
        
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
    print("Запуск миграции таблицы notifications...")
    create_notifications_table()

