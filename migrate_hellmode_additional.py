#!/usr/bin/env python3
# migrate_hellmode_additional.py
# Миграция для добавления поддержки дополнительного задания HellMode и валюты purified

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
        # 1. Добавляем поле id в hellmode_quest, если его нет
        print("Проверка структуры таблицы hellmode_quest...")
        cursor.execute("PRAGMA table_info(hellmode_quest)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'id' not in columns:
            print("Добавление поля id в hellmode_quest...")
            # Создаем новую таблицу с id
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS hellmode_quest_new (
                    id INTEGER PRIMARY KEY,
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
            ''')
            
            # Переносим существующее задание с id=1 (еженедельное)
            cursor.execute('''
                INSERT INTO hellmode_quest_new 
                (id, map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward)
                SELECT 1, map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward
                FROM hellmode_quest
                LIMIT 1
            ''')
            
            # Удаляем старую таблицу и переименовываем новую
            cursor.execute('DROP TABLE hellmode_quest')
            cursor.execute('ALTER TABLE hellmode_quest_new RENAME TO hellmode_quest')
            print("✓ Поле id добавлено в hellmode_quest")
        else:
            print("✓ Поле id уже существует в hellmode_quest")
        
        # Проверяем, есть ли запись с id=1, если нет - создаем пустую
        cursor.execute('SELECT COUNT(*) FROM hellmode_quest WHERE id = 1')
        if cursor.fetchone()[0] == 0:
            print("Создание записи для еженедельного задания (id=1)...")
            cursor.execute('''
                INSERT INTO hellmode_quest 
                (id, map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward)
                VALUES (1, '', '', '', '', '', '', '', '', 0)
            ''')
        
        # 2. Добавляем поле purified в users
        print("Проверка поля purified в users...")
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'purified' not in columns:
            print("Добавление поля purified в users...")
            cursor.execute('ALTER TABLE users ADD COLUMN purified INTEGER DEFAULT 0')
            print("✓ Поле purified добавлено в users")
        else:
            print("✓ Поле purified уже существует в users")
        
        # 3. Добавляем поле additional_hellmode в quests_done
        print("Проверка поля additional_hellmode в quests_done...")
        cursor.execute("PRAGMA table_info(quests_done)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'additional_hellmode' not in columns:
            print("Добавление поля additional_hellmode в quests_done...")
            cursor.execute('ALTER TABLE quests_done ADD COLUMN additional_hellmode INTEGER DEFAULT 0')
            print("✓ Поле additional_hellmode добавлено в quests_done")
        else:
            print("✓ Поле additional_hellmode уже существует в quests_done")
        
        # 4. Обновляем valid_types в pending_applications (если нужно)
        # Это делается в коде, не требует миграции БД
        
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

