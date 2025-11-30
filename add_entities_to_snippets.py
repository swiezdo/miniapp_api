#!/usr/bin/env python3
# add_entities_to_snippets.py
# Миграционный скрипт для добавления поля entities_json в таблицу snippets

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def add_entities_column():
    """
    Добавляет поле entities_json в таблицу snippets.
    """
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли колонка
        cursor.execute("PRAGMA table_info(snippets)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'entities_json' in columns:
            print("Колонка entities_json уже существует.")
            return
        
        print("Добавляем колонку entities_json в таблицу snippets...")
        
        # Добавляем колонку
        cursor.execute("""
            ALTER TABLE snippets
            ADD COLUMN entities_json TEXT
        """)
        
        print("Колонка entities_json добавлена.")
        
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
    print("Запуск миграции добавления entities_json...")
    add_entities_column()

