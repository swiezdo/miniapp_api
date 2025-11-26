#!/usr/bin/env python3
# create_top100_prize_table.py
# Скрипт для создания таблицы top100_current_prize с начальным значением 300

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_top100_prize_table():
    """
    Создает таблицу top100_current_prize с одним полем value INTEGER
    и вставляет начальное значение 300.
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
            WHERE type='table' AND name='top100_current_prize'
        """)
        
        if cursor.fetchone():
            print("Таблица top100_current_prize уже существует")
            return
        
        print("Создание таблицы top100_current_prize...")
        
        # Создаем таблицу
        cursor.execute("""
            CREATE TABLE top100_current_prize (
                value INTEGER NOT NULL
            )
        """)
        
        # Вставляем начальное значение 300
        cursor.execute("""
            INSERT INTO top100_current_prize (value)
            VALUES (?)
        """, (300,))
        
        conn.commit()
        print("Таблица top100_current_prize успешно создана с начальным значением 300")
    
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
    print("Запуск создания таблицы top100_current_prize...")
    create_top100_prize_table()

