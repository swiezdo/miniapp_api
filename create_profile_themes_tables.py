#!/usr/bin/env python3
# create_profile_themes_tables.py
# Одноразовый скрипт для создания всех таблиц, связанных с темами профиля

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_profile_themes_tables():
    """
    Создает все необходимые таблицы для системы тем профиля:
    - profile_themes - каталог доступных тем
    - user_profile_themes - купленные темы пользователей
    - Добавляет поле active_theme_key в таблицу users (если его еще нет)
    """
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 1. Создаем таблицу profile_themes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='profile_themes'
        """)
        
        if cursor.fetchone():
            print("Таблица profile_themes уже существует.")
        else:
            print("Создаем таблицу profile_themes...")
            cursor.execute("""
                CREATE TABLE profile_themes (
                    theme_key TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    price INTEGER NOT NULL DEFAULT 0,
                    css_file TEXT NOT NULL,
                    preview_colors TEXT,
                    is_default BOOLEAN NOT NULL DEFAULT 0,
                    created_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            print("Таблица profile_themes создана.")
        
        # 2. Создаем таблицу user_profile_themes
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='user_profile_themes'
        """)
        
        if cursor.fetchone():
            print("Таблица user_profile_themes уже существует.")
        else:
            print("Создаем таблицу user_profile_themes...")
            cursor.execute("""
                CREATE TABLE user_profile_themes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    theme_key TEXT NOT NULL,
                    purchased_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (user_id) REFERENCES users(user_id),
                    FOREIGN KEY (theme_key) REFERENCES profile_themes(theme_key),
                    UNIQUE(user_id, theme_key)
                )
            """)
            
            # Создаем индексы для быстрого поиска
            cursor.execute("""
                CREATE INDEX idx_user_profile_themes_user ON user_profile_themes(user_id)
            """)
            cursor.execute("""
                CREATE INDEX idx_user_profile_themes_theme ON user_profile_themes(theme_key)
            """)
            print("Таблица user_profile_themes создана.")
        
        # 3. Добавляем поле active_theme_key в таблицу users (если его еще нет)
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'active_theme_key' not in columns:
            print("Добавляем поле active_theme_key в таблицу users...")
            cursor.execute("""
                ALTER TABLE users ADD COLUMN active_theme_key TEXT
            """)
            print("Поле active_theme_key добавлено в таблицу users.")
        else:
            print("Поле active_theme_key уже существует в таблице users.")
        
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
    print("Запуск миграции таблиц для тем профиля...")
    create_profile_themes_tables()

