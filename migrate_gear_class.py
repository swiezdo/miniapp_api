#!/usr/bin/env python3
# migrate_gear_class.py
# Миграция для добавления поля class в таблицу gear для сохранения класса легендарных оберегов

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
        # Проверяем структуру таблицы gear
        print("Проверка структуры таблицы gear...")
        cursor.execute("PRAGMA table_info(gear)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'class' not in columns:
            print("Добавление поля class в gear...")
            cursor.execute('ALTER TABLE gear ADD COLUMN class TEXT')
            print("✓ Поле class добавлено в gear")
        else:
            print("✓ Поле class уже существует в gear")
        
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

