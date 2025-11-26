#!/usr/bin/env python3
# migrate_hellmode_quest_rename_fields.py
# Миграция для переименования полей и добавления полей с названиями

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def migrate_hellmode_quest_table():
    """
    Переименовывает поля emote, class, gear в emote_slug, class_slug, gear_slug
    и добавляет поля emote_name, class_name, gear_name.
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
            WHERE type='table' AND name='hellmode_quest'
        """)
        
        if not cursor.fetchone():
            print("Ошибка: Таблица hellmode_quest не найдена")
            sys.exit(1)
        
        # Получаем текущую структуру таблицы
        cursor.execute("PRAGMA table_info(hellmode_quest)")
        columns = {col[1]: col for col in cursor.fetchall()}
        
        # Проверяем, нужна ли миграция
        needs_migration = False
        
        # Проверяем старые названия полей
        if 'emote' in columns and 'emote_slug' not in columns:
            needs_migration = True
        if 'class' in columns and 'class_slug' not in columns:
            needs_migration = True
        if 'gear' in columns and 'gear_slug' not in columns:
            needs_migration = True
        
        # Проверяем наличие полей с названиями
        if 'emote_name' not in columns:
            needs_migration = True
        if 'class_name' not in columns:
            needs_migration = True
        if 'gear_name' not in columns:
            needs_migration = True
        
        if not needs_migration:
            print("Миграция не требуется. Таблица уже имеет правильную структуру.")
            return
        
        print("Начинаем миграцию...")
        
        # Сохраняем текущие данные
        cursor.execute("SELECT map_slug, map_name, emote, class, gear, reward FROM hellmode_quest LIMIT 1")
        old_row = cursor.fetchone()
        
        if old_row:
            map_slug, map_name, emote_slug, class_slug, gear_slug, reward = old_row
            print(f"Сохранены данные: map={map_slug}, emote={emote_slug}, class={class_slug}, gear={gear_slug}")
        else:
            map_slug, map_name, emote_slug, class_slug, gear_slug, reward = '', '', '', '', '', 0
            print("Таблица пуста, будут созданы пустые поля")
        
        # Создаем новую таблицу с правильной структурой
        cursor.execute("DROP TABLE hellmode_quest")
        
        cursor.execute("""
            CREATE TABLE hellmode_quest (
                map_slug TEXT NOT NULL,
                map_name TEXT NOT NULL,
                emote_slug TEXT NOT NULL,
                emote_name TEXT NOT NULL,
                class_slug TEXT NOT NULL,
                class_name TEXT NOT NULL,
                gear_slug TEXT NOT NULL,
                gear_name TEXT NOT NULL,
                reward INTEGER NOT NULL
            )
        """)
        
        print("Таблица пересоздана с новой структурой.")
        
        # Восстанавливаем данные (названия будут пустыми, их нужно будет заполнить через генератор)
        cursor.execute("""
            INSERT INTO hellmode_quest (
                map_slug, map_name, 
                emote_slug, emote_name,
                class_slug, class_name,
                gear_slug, gear_name,
                reward
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (map_slug, map_name, emote_slug, '', class_slug, '', gear_slug, '', reward))
        
        print("Данные восстановлены (поля с названиями будут пустыми и должны быть заполнены через генератор).")
        
        conn.commit()
        print("Миграция успешно завершена!")
        
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
    print("Запуск миграции таблицы hellmode_quest...")
    migrate_hellmode_quest_table()


