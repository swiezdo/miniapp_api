#!/usr/bin/env python3
# migrate_trophies.py
# Миграционный скрипт для заполнения трофеев существующих пользователей

import os
import sys

# Добавляем текущую директорию в путь для импорта модулей
sys.path.insert(0, os.path.dirname(__file__))

from db import init_db, get_all_users, get_mastery, add_trophy, init_user_trophies
from mastery_config import load_mastery_config

# Получаем путь к БД из переменной окружения или используем значение по умолчанию
DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")

def migrate_trophies():
    """
    Мигрирует трофеи для всех существующих пользователей.
    Для каждого пользователя проверяет уровни мастерства и добавляет трофеи
    за достигнутые максимальные уровни.
    """
    print("Начинаем миграцию трофеев...")
    print(f"Путь к БД: {DB_PATH}")
    
    # Инициализируем БД (создаем таблицы если их нет)
    init_db(DB_PATH)
    
    # Загружаем конфиг мастерства
    try:
        config = load_mastery_config()
        print("Конфиг мастерства загружен успешно")
    except Exception as e:
        print(f"Ошибка загрузки конфига мастерства: {e}")
        return False
    
    # Создаем словарь максимальных уровней по категориям
    max_levels_map = {}
    for category in config.get('categories', []):
        category_key = category.get('key')
        max_levels = category.get('maxLevels', 0)
        if category_key:
            max_levels_map[category_key] = max_levels
            print(f"Категория {category_key}: максимальный уровень = {max_levels}")
    
    # Получаем всех пользователей
    users = get_all_users(DB_PATH)
    print(f"\nНайдено пользователей: {len(users)}")
    
    # Статистика миграции
    stats = {
        'total_users': len(users),
        'users_with_trophies': 0,
        'trophies_added': 0,
        'errors': 0
    }
    
    # Обрабатываем каждого пользователя
    for user in users:
        user_id = user.get('user_id')
        psn_id = user.get('psn_id', '')
        mastery = user.get('mastery', {})
        
        if not user_id:
            continue
        
        print(f"\nОбрабатываем пользователя {user_id} (PSN: {psn_id})...")
        
        # Убеждаемся что запись в trophies существует
        try:
            # Инициализируем запись трофеев если её нет
            init_user_trophies(DB_PATH, user_id, psn_id)
        except Exception as e:
            print(f"  Ошибка инициализации трофеев: {e}")
            stats['errors'] += 1
            continue
        
        # Проверяем каждую категорию мастерства
        trophies_added_for_user = 0
        categories_order = ['solo', 'hellmode', 'raid', 'speedrun']
        
        for category_key in categories_order:
            if category_key not in max_levels_map:
                continue
            
            max_level = max_levels_map[category_key]
            current_level = mastery.get(category_key, 0)
            
            if current_level >= max_level and max_level > 0:
                # Пользователь достиг максимального уровня - добавляем трофей
                try:
                    success = add_trophy(DB_PATH, user_id, category_key)
                    if success:
                        print(f"  ✓ Добавлен трофей: {category_key}")
                        trophies_added_for_user += 1
                        stats['trophies_added'] += 1
                    else:
                        # Возможно трофей уже есть - это нормально
                        print(f"  - Трофей {category_key} уже существует или не был добавлен")
                except Exception as e:
                    print(f"  ✗ Ошибка добавления трофея {category_key}: {e}")
                    stats['errors'] += 1
        
        if trophies_added_for_user > 0:
            stats['users_with_trophies'] += 1
    
    # Выводим статистику
    print("\n" + "="*50)
    print("МИГРАЦИЯ ЗАВЕРШЕНА")
    print("="*50)
    print(f"Всего пользователей: {stats['total_users']}")
    print(f"Пользователей с трофеями: {stats['users_with_trophies']}")
    print(f"Трофеев добавлено: {stats['trophies_added']}")
    print(f"Ошибок: {stats['errors']}")
    print("="*50)
    
    return True


if __name__ == "__main__":
    try:
        success = migrate_trophies()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nМиграция прервана пользователем")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nКритическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

