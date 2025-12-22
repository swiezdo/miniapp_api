#!/usr/bin/env python3
# migrate_contest_table.py
# Миграция для создания таблицы contest_participants для хранения участников конкурса

import os
import sys
import sqlite3

# Пытаемся загрузить из .env вручную
DB_PATH = "/root/miniapp_api/app.db"
if os.path.exists("/root/miniapp_api/.env"):
    with open("/root/miniapp_api/.env", "r") as f:
        for line in f:
            if line.startswith("DB_PATH="):
                DB_PATH = line.split("=", 1)[1].strip().strip('"').strip("'")
                break


def migrate():
    """Выполняет миграцию базы данных."""
    if not os.path.exists(DB_PATH):
        print(f"База данных не найдена: {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Проверяем существование таблицы
        print("Проверка существования таблицы contest_participants...")
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='contest_participants'
        """)
        
        if cursor.fetchone():
            print("✓ Таблица contest_participants уже существует")
        else:
            print("Создание таблицы contest_participants...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contest_participants (
                    user_id INTEGER PRIMARY KEY,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            print("✓ Таблица contest_participants создана")
        
        conn.commit()
        print("\n✓ Миграция успешно завершена!")
        return True
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = migrate()
    sys.exit(0 if success else 1)



