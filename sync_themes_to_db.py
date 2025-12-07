#!/usr/bin/env python3
# sync_themes_to_db.py
# Синхронизирует темы из themes.json в базу данных

import os
import json
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")
THEMES_JSON_PATH = os.path.join(os.path.dirname(__file__), 'themes.json')


def sync_themes_to_db():
    """
    Синхронизирует темы из JSON файла в базу данных.
    """
    if not os.path.exists(DB_PATH):
        print(f"Ошибка: База данных не найдена по пути {DB_PATH}")
        sys.exit(1)
    
    if not os.path.exists(THEMES_JSON_PATH):
        print(f"Ошибка: Файл themes.json не найден по пути {THEMES_JSON_PATH}")
        sys.exit(1)
    
    # Загружаем темы из JSON
    try:
        with open(THEMES_JSON_PATH, 'r', encoding='utf-8') as f:
            themes = json.load(f)
    except Exception as e:
        print(f"Ошибка чтения themes.json: {e}")
        sys.exit(1)
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for theme in themes:
            theme_key = theme.get('key')
            name = theme.get('name', theme_key)
            price = theme.get('price', 0)
            css_file = theme.get('css_file', f'themes/{theme_key}.css')
            preview_colors = json.dumps(theme.get('colors', []))
            is_default = 1 if theme.get('is_default', False) else 0
            
            # Проверяем, существует ли тема
            cursor.execute('''
                SELECT theme_key FROM profile_themes WHERE theme_key = ?
            ''', (theme_key,))
            
            if cursor.fetchone():
                # Обновляем существующую тему
                print(f"Обновляем тему: {theme_key}")
                cursor.execute('''
                    UPDATE profile_themes 
                    SET name = ?, price = ?, css_file = ?, preview_colors = ?, is_default = ?
                    WHERE theme_key = ?
                ''', (name, price, css_file, preview_colors, is_default, theme_key))
            else:
                # Добавляем новую тему
                print(f"Добавляем тему: {theme_key}")
                cursor.execute('''
                    INSERT INTO profile_themes (theme_key, name, price, css_file, preview_colors, is_default, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, strftime('%s', 'now'))
                ''', (theme_key, name, price, css_file, preview_colors, is_default))
        
        conn.commit()
        print(f"Синхронизация завершена! Обработано тем: {len(themes)}")
        
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
    print("Запуск синхронизации тем из JSON в БД...")
    sync_themes_to_db()

