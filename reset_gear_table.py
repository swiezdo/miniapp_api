#!/usr/bin/env python3
# reset_gear_table.py
# Скрипт для очистки таблицы gear и сброса автоинкремента

import os
import sys
import sqlite3
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def reset_gear_table(db_path: str) -> bool:
    """
    Очищает таблицу gear и сбрасывает автоинкремент.
    
    Args:
        db_path: Путь к файлу базы данных
        
    Returns:
        True если успешно, иначе False
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Удаляем все записи
        cursor.execute('DELETE FROM gear')
        
        # Сбрасываем автоинкремент (в SQLite это делается через удаление и пересоздание таблицы)
        # Но проще использовать SQLite команду для сброса последовательности
        cursor.execute('DELETE FROM sqlite_sequence WHERE name="gear"')
        
        conn.commit()
        conn.close()
        
        print(f"✅ Таблица gear очищена и автоинкремент сброшен в {db_path}")
        return True
        
    except sqlite3.Error as e:
        print(f"❌ Ошибка очистки таблицы gear: {e}")
        return False
    except Exception as e:
        print(f"❌ Неожиданная ошибка: {e}")
        return False


def main():
    """
    Главная функция скрипта.
    """
    try:
        print(f"Очистка таблицы gear в базе данных: {DB_PATH}")
        if reset_gear_table(DB_PATH):
            print("Очистка завершена успешно")
            sys.exit(0)
        else:
            print("Ошибка при очистке таблицы")
            sys.exit(1)
    
    except Exception as e:
        print(f"Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()



