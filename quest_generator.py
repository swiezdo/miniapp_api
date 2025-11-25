#!/usr/bin/env python3
# quest_generator.py
# Скрипт для автоматической генерации заданий HellMode каждую субботу в 9:00 МСК

import os
import sys
import json
import random
from datetime import datetime, timezone, timedelta
from typing import Optional
from dotenv import load_dotenv

# Добавляем путь к модулю db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_current_hellmode_quest, update_hellmode_quest

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")
QUESTS_JSON_PATH = "/root/tsushimaru_app/docs/assets/data/quests.json"
MAX_ATTEMPTS = 10


def load_quests_config() -> dict:
    """
    Загружает конфигурацию заданий из JSON файла.
    
    Returns:
        Словарь с конфигурацией заданий
    
    Raises:
        FileNotFoundError: Если файл не найден
        json.JSONDecodeError: Если файл содержит невалидный JSON
        KeyError: Если отсутствуют необходимые поля
    """
    if not os.path.exists(QUESTS_JSON_PATH):
        raise FileNotFoundError(f"Файл конфигурации не найден: {QUESTS_JSON_PATH}")
    
    with open(QUESTS_JSON_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # Проверяем наличие необходимых полей
    if 'hellmode' not in config:
        raise KeyError("Отсутствует секция 'hellmode' в конфигурации")
    
    hellmode = config['hellmode']
    
    required_fields = ['baseReward', 'map', 'emote', 'class', 'gear']
    for field in required_fields:
        if field not in hellmode:
            raise KeyError(f"Отсутствует поле '{field}' в секции 'hellmode'")
    
    return hellmode


def generate_random_quest(hellmode_config: dict) -> dict:
    """
    Генерирует случайное задание из конфигурации.
    
    Args:
        hellmode_config: Конфигурация заданий HellMode
    
    Returns:
        Словарь с полями: map_slug, emote_slug, class_slug, gear_slug, reward
    """
    # Выбираем случайные элементы
    map_item = random.choice(hellmode_config['map'])
    emote_item = random.choice(hellmode_config['emote'])
    class_item = random.choice(hellmode_config['class'])
    gear_item = random.choice(hellmode_config['gear'])
    
    # Извлекаем slug'и и названия
    map_slug = map_item['slug']
    map_name = map_item['name']
    emote_slug = emote_item['slug']
    class_slug = class_item['slug']
    gear_slug = gear_item['slug']
    
    # Рассчитываем награду
    base_reward = hellmode_config['baseReward']
    map_bonus = map_item['bonus']
    class_bonus = class_item['bonus']
    gear_bonus = gear_item['bonus']
    
    reward = base_reward + map_bonus + class_bonus + gear_bonus
    
    return {
        'map_slug': map_slug,
        'map_name': map_name,
        'emote_slug': emote_slug,
        'class_slug': class_slug,
        'gear_slug': gear_slug,
        'reward': reward
    }


def has_duplicates(new_quest: dict, current_quest: Optional[dict]) -> bool:
    """
    Проверяет, есть ли повторения между новым и текущим заданием.
    
    Args:
        new_quest: Новое задание
        current_quest: Текущее задание (может быть None)
    
    Returns:
        True если есть повторения, иначе False
    """
    if not current_quest:
        return False
    
    # Проверяем каждое поле (кроме reward)
    fields_to_check = ['map_slug', 'emote_slug', 'class_slug', 'gear_slug']
    
    for field in fields_to_check:
        # Преобразуем имена полей для сравнения с БД
        if field == 'map_slug':
            db_field = 'map_slug'
        elif field == 'emote_slug':
            db_field = 'emote'
        elif field == 'class_slug':
            db_field = 'class'
        elif field == 'gear_slug':
            db_field = 'gear'
        else:
            db_field = field.replace('_slug', '')
        
        if new_quest[field] == current_quest[db_field]:
            return True
    
    return False


def should_generate_quest() -> bool:
    """
    Проверяет, нужно ли генерировать новое задание.
    Генерация происходит каждую субботу в 9:00 МСК (UTC+3).
    
    Returns:
        True если нужно сгенерировать задание, иначе False
    """
    # Текущее время в UTC
    now_utc = datetime.now(timezone.utc)
    
    # Московское время (UTC+3)
    moscow_tz = timezone(timedelta(hours=3))
    now_moscow = now_utc.astimezone(moscow_tz)
    
    # Проверяем, что сегодня суббота (weekday() = 5)
    if now_moscow.weekday() != 5:  # 5 = суббота
        return False
    
    # Проверяем, что время 9:00 или позже
    if now_moscow.hour < 9:
        return False
    
    # Получаем текущее задание из БД
    current_quest = get_current_hellmode_quest(DB_PATH)
    
    # Если задания нет или оно пустое - генерируем
    if not current_quest:
        return True
    
    # Проверяем, было ли уже обновление сегодня
    # Для простоты считаем, что если скрипт запущен в субботу после 9:00,
    # то нужно обновить (можно улучшить, добавив timestamp)
    return True


def main():
    """
    Главная функция скрипта.
    """
    try:
        print("Загрузка конфигурации заданий...")
        hellmode_config = load_quests_config()
        print("Конфигурация успешно загружена.")
        
        # Получаем текущее задание
        current_quest = get_current_hellmode_quest(DB_PATH)
        
        if current_quest:
            print(f"Текущее задание:")
            map_name = current_quest.get('map_name', '')
            if map_name:
                print(f"  Карта: {map_name} ({current_quest['map_slug']})")
            else:
                print(f"  Карта: {current_quest['map_slug']}")
            print(f"  Эмоция: {current_quest['emote']}")
            print(f"  Класс: {current_quest['class']}")
            print(f"  Снаряжение: {current_quest['gear']}")
            print(f"  Награда: {current_quest['reward']}")
        else:
            print("Текущее задание отсутствует (будет создано новое).")
        
        # Генерируем новое задание с проверкой на повторения
        print("\nГенерация нового задания...")
        new_quest = None
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            generated = generate_random_quest(hellmode_config)
            
            if not has_duplicates(generated, current_quest):
                new_quest = generated
                print(f"Задание сгенерировано с попытки {attempt}.")
                break
            else:
                print(f"Попытка {attempt}: обнаружены повторения, перерандомивание...")
        
        # Если после всех попыток есть повторения - принимаем последний результат
        if not new_quest:
            print(f"Внимание: после {MAX_ATTEMPTS} попыток все еще есть повторения.")
            print("Принимается последний сгенерированный вариант.")
            new_quest = generate_random_quest(hellmode_config)
        
        print(f"\nНовое задание:")
        print(f"  Карта: {new_quest['map_name']} ({new_quest['map_slug']})")
        print(f"  Эмоция: {new_quest['emote_slug']}")
        print(f"  Класс: {new_quest['class_slug']}")
        print(f"  Снаряжение: {new_quest['gear_slug']}")
        print(f"  Награда: {new_quest['reward']}")
        
        # Сохраняем в БД
        print("\nСохранение задания в базу данных...")
        if update_hellmode_quest(
            DB_PATH,
            new_quest['map_slug'],
            new_quest['map_name'],
            new_quest['emote_slug'],
            new_quest['class_slug'],
            new_quest['gear_slug'],
            new_quest['reward']
        ):
            print("Задание успешно сохранено!")
        else:
            print("Ошибка: не удалось сохранить задание в базу данных")
            sys.exit(1)
    
    except FileNotFoundError as e:
        print(f"Ошибка: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка парсинга JSON: {e}")
        sys.exit(1)
    except KeyError as e:
        print(f"Ошибка конфигурации: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

