#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Одноразовый скрипт для создания таблицы birthdays и миграции данных из users.
Запускать один раз для создания таблицы и заполнения начальными данными.
"""

import os
import sqlite3
import sys
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Получаем путь к БД из переменных окружения
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_birthdays_table():
    """
    Создает таблицу birthdays и заполняет её данными из users.
    """
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли уже таблица birthdays
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='birthdays'
        """)
        
        if cursor.fetchone():
            print("Таблица birthdays уже существует. Пропускаем создание.")
        else:
            # Создаем таблицу birthdays
            cursor.execute("""
                CREATE TABLE birthdays (
                    user_id INTEGER PRIMARY KEY,
                    psn_id TEXT,
                    birthday TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            """)
            print("Таблица birthdays успешно создана.")
        
        # Получаем всех пользователей из таблицы users
        cursor.execute("""
            SELECT user_id, psn_id FROM users
        """)
        
        users = cursor.fetchall()
        print(f"Найдено пользователей: {len(users)}")
        
        # Для каждого пользователя создаем запись в birthdays
        inserted_count = 0
        skipped_count = 0
        
        for user_id, psn_id in users:
            # Проверяем, существует ли уже запись для этого пользователя
            cursor.execute("""
                SELECT user_id FROM birthdays WHERE user_id = ?
            """, (user_id,))
            
            if cursor.fetchone():
                skipped_count += 1
                continue
            
            # Создаем запись с user_id и psn_id, birthday оставляем NULL
            cursor.execute("""
                INSERT INTO birthdays (user_id, psn_id, birthday)
                VALUES (?, ?, NULL)
            """, (user_id, psn_id or ''))
            inserted_count += 1
        
        conn.commit()
        
        print(f"Миграция завершена:")
        print(f"  - Создано записей: {inserted_count}")
        print(f"  - Пропущено (уже существовали): {skipped_count}")
        print(f"  - Всего пользователей: {len(users)}")
        
    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        if conn:
            conn.rollback()
        sys.exit(1)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    print("Запуск миграции таблицы birthdays...")
    create_birthdays_table()
    print("Миграция успешно завершена!")

