#!/usr/bin/env python3
# update_top100_prize.py
# Скрипт для автоматического обновления приза Top100 каждый день в 9:00 МСК

import os
import sys
from dotenv import load_dotenv

# Добавляем путь к модулю db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_top100_current_prize, update_top100_current_prize

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")


def get_next_prize_value(current_value: int) -> int:
    """
    Определяет следующее значение приза на основе текущего.
    
    Логика обновления:
    - 0 → 60
    - 60 → 120
    - 120 → 180
    - 180 → 240
    - 240 → 300
    - 300 → 350
    - 350 → 0
    
    Args:
        current_value: Текущее значение приза
    
    Returns:
        Следующее значение приза
    """
    mapping = {
        0: 60,
        60: 120,
        120: 180,
        180: 240,
        240: 300,
        300: 350,
        350: 0
    }
    
    return mapping.get(current_value, 0)


def main():
    """
    Главная функция скрипта.
    """
    try:
        # Получаем текущее значение приза
        current_value = get_top100_current_prize(DB_PATH)
        
        if current_value is None:
            print("Ошибка: не удалось получить текущее значение приза Top100 из БД")
            sys.exit(1)
        
        print(f"Текущее значение приза: {current_value}")
        
        # Определяем следующее значение
        next_value = get_next_prize_value(current_value)
        print(f"Обновление приза Top100: {current_value} → {next_value}")
        
        # Обновляем значение в БД
        if update_top100_current_prize(DB_PATH, next_value):
            print(f"Приз Top100 успешно обновлен. Новое значение: {next_value}")
        else:
            print("Ошибка: не удалось обновить приз Top100")
            sys.exit(1)
    
    except Exception as e:
        print(f"Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

