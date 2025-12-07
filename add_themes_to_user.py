#!/usr/bin/env python3
"""
Скрипт для добавления всех тем как купленных для пользователя
"""
import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")
USER_ID = 1053983438

def add_themes_to_user():
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Получаем все темы кроме default
        cursor.execute("""
            SELECT theme_key FROM profile_themes 
            WHERE is_default = 0
        """)
        themes = cursor.fetchall()
        
        print(f"Найдено тем для добавления: {len(themes)}")
        
        added_count = 0
        skipped_count = 0
        
        for (theme_key,) in themes:
            # Проверяем, не куплена ли уже тема
            cursor.execute("""
                SELECT id FROM user_profile_themes 
                WHERE user_id = ? AND theme_key = ?
            """, (USER_ID, theme_key))
            
            if cursor.fetchone():
                print(f"Тема {theme_key} уже куплена, пропускаем")
                skipped_count += 1
                continue
            
            # Добавляем тему
            cursor.execute("""
                INSERT INTO user_profile_themes (user_id, theme_key, purchased_at)
                VALUES (?, ?, strftime('%s', 'now'))
            """, (USER_ID, theme_key))
            
            print(f"Добавлена тема: {theme_key}")
            added_count += 1
        
        conn.commit()
        print(f"\nГотово! Добавлено тем: {added_count}, пропущено: {skipped_count}")
        
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
    print(f"Добавление тем для пользователя {USER_ID}...")
    add_themes_to_user()

