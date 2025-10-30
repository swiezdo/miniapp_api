#!/usr/bin/env python3
"""
Одноразовый скрипт миграции: копирует всех пользователей из users в mastery.
Создаёт записи в таблице mastery для всех существующих пользователей с нулевыми уровнями.
"""

import sqlite3
import os

# Путь к БД - можно указать напрямую или через переменную окружения
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")

def migrate_users_to_mastery():
    """
    Мигрирует всех пользователей из таблицы users в таблицу mastery.
    """
    if not os.path.exists(DB_PATH):
        print(f"❌ База данных не найдена: {DB_PATH}")
        return False
    
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Получаем всех пользователей
        cursor.execute('SELECT user_id FROM users')
        existing_users = cursor.fetchall()
        
        if not existing_users:
            print("ℹ️  Пользователей для миграции не найдено")
            conn.close()
            return True
        
        print(f"📋 Найдено пользователей: {len(existing_users)}")
        
        migrated_count = 0
        skipped_count = 0
        
        for (user_id,) in existing_users:
            # Проверяем, есть ли уже запись в mastery
            cursor.execute('SELECT user_id FROM mastery WHERE user_id = ?', (user_id,))
            if not cursor.fetchone():
                # Создаём запись с нулевыми уровнями
                cursor.execute('''
                    INSERT INTO mastery (user_id, solo, hellmode, raid, speedrun)
                    VALUES (?, 0, 0, 0, 0)
                ''', (user_id,))
                migrated_count += 1
                print(f"✅ Создана запись mastery для user_id: {user_id}")
            else:
                skipped_count += 1
                print(f"⏭️  Запись mastery уже существует для user_id: {user_id}")
        
        conn.commit()
        conn.close()
        
        print(f"\n📊 Результаты миграции:")
        print(f"   ✅ Создано записей: {migrated_count}")
        print(f"   ⏭️  Пропущено (уже существуют): {skipped_count}")
        print(f"   📝 Всего обработано: {len(existing_users)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Ошибка миграции: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🚀 Запуск миграции пользователей в таблицу mastery...")
    print(f"📁 База данных: {DB_PATH}\n")
    
    success = migrate_users_to_mastery()
    
    if success:
        print("\n✅ Миграция завершена успешно!")
    else:
        print("\n❌ Миграция завершена с ошибками!")
        exit(1)

