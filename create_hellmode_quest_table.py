#!/usr/bin/env python3
# create_hellmode_quest_table.py
# Одноразовый скрипт для создания таблицы hellmode_quest

import os
import sqlite3
import sys
from dotenv import load_dotenv

load_dotenv()
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def create_hellmode_quest_table():
    """
    Создает таблицу hellmode_quest для хранения текущего задания HellMode.
    Таблица хранит только одну запись.
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
        
        if cursor.fetchone():
            print("Таблица hellmode_quest уже существует.")
            # Проверяем структуру таблицы
            cursor.execute("PRAGMA table_info(hellmode_quest)")
            columns = [col[1] for col in cursor.fetchall()]
            
            # Проверяем, нужно ли обновить структуру
            needs_update = False
            if 'id' in columns or 'map' in columns or 'map_name' not in columns:
                needs_update = True
            
            if needs_update:
                print("Обнаружена старая структура. Пересоздаем таблицу...")
                # Сохраняем данные если есть (старая структура)
                old_data = None
                if 'map' in columns:
                    cursor.execute("SELECT map, emote, class, gear, reward FROM hellmode_quest LIMIT 1")
                    old_data = cursor.fetchone()
                
                # Удаляем старую таблицу
                cursor.execute("DROP TABLE hellmode_quest")
                
                # Создаем новую таблицу с правильной структурой
                cursor.execute("""
                    CREATE TABLE hellmode_quest (
                        map_slug TEXT NOT NULL,
                        map_name TEXT NOT NULL,
                        emote TEXT NOT NULL,
                        class TEXT NOT NULL,
                        gear TEXT NOT NULL,
                        reward INTEGER NOT NULL
                    )
                """)
                print("Таблица пересоздана с новой структурой.")
                
                # Восстанавливаем данные если были
                if old_data and old_data[0]:  # Проверяем что map не пустой
                    # Старая структура: map, emote, class, gear, reward
                    # Новая структура: map_slug, map_name, emote, class, gear, reward
                    # map_name будет пустым, так как в старой структуре его не было
                    cursor.execute("""
                        INSERT INTO hellmode_quest (map_slug, map_name, emote, class, gear, reward)
                        VALUES (?, '', ?, ?, ?, ?)
                    """, (old_data[0], old_data[1], old_data[2], old_data[3], old_data[4]))
                    print("Данные восстановлены (map_name будет пустым для старых записей).")
                else:
                    # Создаем начальную запись с пустыми значениями
                    cursor.execute("""
                        INSERT INTO hellmode_quest (map_slug, map_name, emote, class, gear, reward)
                        VALUES ('', '', '', '', '', 0)
                    """)
                    print("Начальная запись создана.")
        else:
            # Создаем таблицу
            cursor.execute("""
                CREATE TABLE hellmode_quest (
                    map_slug TEXT NOT NULL,
                    map_name TEXT NOT NULL,
                    emote TEXT NOT NULL,
                    class TEXT NOT NULL,
                    gear TEXT NOT NULL,
                    reward INTEGER NOT NULL
                )
            """)
            print("Таблица hellmode_quest успешно создана.")
            
            # Создаем начальную запись с пустыми значениями
            cursor.execute("""
                INSERT INTO hellmode_quest (map_slug, map_name, emote, class, gear, reward)
                VALUES ('', '', '', '', '', 0)
            """)
            print("Начальная запись создана.")
        
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
    create_hellmode_quest_table()

