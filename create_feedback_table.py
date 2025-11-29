#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Одноразовый скрипт для создания таблицы feedback_messages
Использование: python3 create_feedback_table.py
"""

import os
import sqlite3

# Путь к базе данных (по умолчанию)
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_feedback_table():
    """Создает таблицу feedback_messages для хранения связи между message_id и user_id"""
    
    if not os.path.exists(DB_PATH):
        print(f"База данных не найдена: {DB_PATH}")
        print("Создайте базу данных сначала или проверьте путь DB_PATH")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='feedback_messages'
        """)
        
        if cursor.fetchone():
            print("Таблица feedback_messages уже существует")
            conn.close()
            return True
        
        # Создаем таблицу
        cursor.execute("""
            CREATE TABLE feedback_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                group_message_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(group_message_id)
            )
        """)
        
        # Создаем индекс для быстрого поиска по group_message_id
        cursor.execute("""
            CREATE INDEX idx_feedback_messages_group_message_id 
            ON feedback_messages(group_message_id)
        """)
        
        conn.commit()
        conn.close()
        
        print("Таблица feedback_messages успешно создана")
        return True
        
    except sqlite3.Error as e:
        print(f"Ошибка при создании таблицы: {e}")
        return False
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        return False


if __name__ == "__main__":
    print("Создание таблицы feedback_messages...")
    success = create_feedback_table()
    if success:
        print("Готово!")
    else:
        print("Ошибка при создании таблицы")
        exit(1)

