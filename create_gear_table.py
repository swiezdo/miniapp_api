#!/usr/bin/env python3
# create_gear_table.py
# Скрипт для создания таблицы gear в базе данных

import os
import sys
import sqlite3
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_gear_table(db_path: str) -> bool:
    """
    Создает таблицу gear в базе данных.
    
    Args:
        db_path: Путь к файлу базы данных
        
    Returns:
        True если успешно, иначе False
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Создаем таблицу gear
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gear (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL,
                ki INTEGER NOT NULL,
                key TEXT NOT NULL,
                name TEXT NOT NULL,
                prop1 TEXT,
                prop1_value TEXT,
                prop2 TEXT,
                prop2_value TEXT,
                perk1 TEXT,
                perk2 TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Создаем индекс для быстрого поиска по user_id
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_gear_user_id ON gear(user_id)
        ''')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Таблица gear успешно создана в {db_path}")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Ошибка создания таблицы gear: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False


def main():
    """
    Главная функция скрипта.
    """
    try:
        print(f"Создание таблицы gear в базе данных: {DB_PATH}")
        if create_gear_table(DB_PATH):
            print("Миграция завершена успешно")
            sys.exit(0)
        else:
            print("Ошибка при выполнении миграции")
            sys.exit(1)
    
    except Exception as e:
        print(f"Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()



