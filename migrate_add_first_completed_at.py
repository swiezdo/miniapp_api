#!/usr/bin/env python3
"""
Миграция: добавление поля first_completed_at в таблицу quests_done.

Это поле хранит Unix timestamp первого завершения всех еженедельных заданий,
используется для сортировки героев недели.
"""

import os
import sys
import sqlite3
import time
from dotenv import load_dotenv

load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def migrate():
    """Выполняет миграцию: добавляет колонку first_completed_at."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существует ли уже колонка
        cursor.execute("PRAGMA table_info(quests_done)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'first_completed_at' in columns:
            print("Колонка first_completed_at уже существует. Миграция не требуется.")
            conn.close()
            return True
        
        # Добавляем колонку
        print("Добавление колонки first_completed_at...")
        cursor.execute('''
            ALTER TABLE quests_done ADD COLUMN first_completed_at INTEGER
        ''')
        
        # Устанавливаем текущее время для существующих героев (all_completed > 0)
        current_time = int(time.time())
        cursor.execute('''
            UPDATE quests_done 
            SET first_completed_at = ?
            WHERE all_completed > 0
        ''', (current_time,))
        
        updated_count = cursor.rowcount
        
        conn.commit()
        conn.close()
        
        print(f"Миграция завершена успешно.")
        print(f"Обновлено записей с all_completed > 0: {updated_count}")
        return True
        
    except sqlite3.Error as e:
        print(f"Ошибка миграции: {e}")
        return False


if __name__ == "__main__":
    if migrate():
        print("Миграция выполнена успешно!")
        sys.exit(0)
    else:
        print("Миграция завершилась с ошибкой!")
        sys.exit(1)

