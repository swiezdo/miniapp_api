#!/usr/bin/env python3
# generate_additional_quest_only.py
# Скрипт для генерации ТОЛЬКО дополнительного задания HellMode (не трогает еженедельное)

import os
import sys
import json
import random
from typing import Optional

# Добавляем путь к модулю db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_current_hellmode_quest, update_hellmode_quest, get_additional_hellmode_quest

# Пытаемся загрузить из .env вручную
DB_PATH = "/root/miniapp_api/app.db"
if os.path.exists("/root/miniapp_api/.env"):
    with open("/root/miniapp_api/.env", "r") as f:
        for line in f:
            if line.startswith("DB_PATH="):
                DB_PATH = line.split("=", 1)[1].strip().strip('"').strip("'")
                break

QUESTS_JSON_PATH = "/root/tsushimaru_app/docs/assets/data/quests.json"
MAX_ATTEMPTS = 10
BASE_REWARD = 350  # Базовая награда за задание


def load_quests_config() -> dict:
    """
    Загружает конфигурацию заданий из JSON файла.
    """
    if not os.path.exists(QUESTS_JSON_PATH):
        raise FileNotFoundError(f"Файл конфигурации не найден: {QUESTS_JSON_PATH}")
    
    with open(QUESTS_JSON_PATH, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    if 'hellmode' not in config:
        raise KeyError("Отсутствует секция 'hellmode' в конфигурации")
    
    hellmode = config['hellmode']
    
    required_fields = ['map', 'emote', 'class', 'gear']
    for field in required_fields:
        if field not in hellmode:
            raise KeyError(f"Отсутствует поле '{field}' в секции 'hellmode'")
    
    return hellmode


def generate_random_quest(hellmode_config: dict) -> dict:
    """
    Генерирует случайное задание из конфигурации.
    """
    map_item = random.choice(hellmode_config['map'])
    emote_item = random.choice(hellmode_config['emote'])
    class_item = random.choice(hellmode_config['class'])
    gear_item = random.choice(hellmode_config['gear'])
    
    map_slug = map_item['slug']
    map_name = map_item['name']
    emote_slug = emote_item['slug']
    emote_name = emote_item['name']
    class_slug = class_item['slug']
    class_name = class_item['name']
    gear_slug = gear_item['slug']
    gear_name = gear_item['name']
    
    map_bonus = map_item.get('bonus', 0)
    class_bonus = class_item.get('bonus', 0)
    gear_bonus = gear_item.get('bonus', 0)
    
    reward = BASE_REWARD + map_bonus + class_bonus + gear_bonus
    
    return {
        'map_slug': map_slug,
        'map_name': map_name,
        'emote_slug': emote_slug,
        'emote_name': emote_name,
        'class_slug': class_slug,
        'class_name': class_name,
        'gear_slug': gear_slug,
        'gear_name': gear_name,
        'reward': reward
    }


def has_duplicates(new_quest: dict, *current_quests: Optional[dict]) -> bool:
    """
    Проверяет, есть ли повторения между новым заданием и текущими заданиями.
    """
    if not current_quests:
        return False
    
    fields_to_check = ['map_slug', 'emote_slug', 'class_slug', 'gear_slug']
    
    for current_quest in current_quests:
        if not current_quest:
            continue
        
        for field in fields_to_check:
            if new_quest[field] == current_quest[field]:
                return True
    
    return False


def main():
    """
    Главная функция скрипта - генерирует ТОЛЬКО дополнительное задание.
    """
    try:
        print("Загрузка конфигурации заданий...")
        hellmode_config = load_quests_config()
        print("Конфигурация успешно загружена.")
        
        # Получаем текущие задания (НЕ изменяем еженедельное!)
        current_weekly_quest = get_current_hellmode_quest(DB_PATH, quest_id=1)
        current_additional_quest = get_additional_hellmode_quest(DB_PATH)
        
        if current_weekly_quest:
            print(f"\nТекущее еженедельное задание (НЕ ИЗМЕНЯЕТСЯ):")
            print(f"  Карта: {current_weekly_quest.get('map_name', '')} ({current_weekly_quest['map_slug']})")
            print(f"  Эмоция: {current_weekly_quest.get('emote_name', '')} ({current_weekly_quest['emote_slug']})")
            print(f"  Класс: {current_weekly_quest.get('class_name', '')} ({current_weekly_quest['class_slug']})")
            print(f"  Снаряжение: {current_weekly_quest.get('gear_name', '')} ({current_weekly_quest['gear_slug']})")
            print(f"  Награда: {current_weekly_quest['reward']}")
        else:
            print("\n⚠️  ВНИМАНИЕ: Еженедельное задание не найдено!")
        
        if current_additional_quest:
            print(f"\nТекущее дополнительное задание:")
            print(f"  Карта: {current_additional_quest.get('map_name', '')} ({current_additional_quest['map_slug']})")
            print(f"  Эмоция: {current_additional_quest.get('emote_name', '')} ({current_additional_quest['emote_slug']})")
            print(f"  Класс: {current_additional_quest.get('class_name', '')} ({current_additional_quest['class_slug']})")
            print(f"  Снаряжение: {current_additional_quest.get('gear_name', '')} ({current_additional_quest['gear_slug']})")
            print(f"  Награда: {current_additional_quest['reward']}")
        else:
            print("\nТекущее дополнительное задание отсутствует (будет создано новое).")
        
        # Генерируем ТОЛЬКО дополнительное задание с проверкой на повторения
        print("\nГенерация дополнительного задания...")
        new_additional_quest = None
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            generated = generate_random_quest(hellmode_config)
            
            # Проверяем, что оно не совпадает с еженедельным и текущим дополнительным
            if not has_duplicates(generated, current_weekly_quest, current_additional_quest):
                new_additional_quest = generated
                print(f"Дополнительное задание сгенерировано с попытки {attempt}.")
                break
            else:
                print(f"Попытка {attempt}: обнаружены повторения, перерандомивание...")
        
        # Если после всех попыток есть повторения - принимаем последний результат
        if not new_additional_quest:
            print(f"Внимание: после {MAX_ATTEMPTS} попыток все еще есть повторения.")
            print("Принимается последний сгенерированный вариант.")
            new_additional_quest = generate_random_quest(hellmode_config)
        
        print(f"\nНовое дополнительное задание:")
        print(f"  Карта: {new_additional_quest['map_name']} ({new_additional_quest['map_slug']})")
        print(f"  Эмоция: {new_additional_quest['emote_name']} ({new_additional_quest['emote_slug']})")
        print(f"  Класс: {new_additional_quest['class_name']} ({new_additional_quest['class_slug']})")
        print(f"  Снаряжение: {new_additional_quest['gear_name']} ({new_additional_quest['gear_slug']})")
        print(f"  Награда: {new_additional_quest['reward']}")
        
        # Сохраняем ТОЛЬКО дополнительное задание в БД (id=2)
        print("\nСохранение дополнительного задания в базу данных...")
        if update_hellmode_quest(
            DB_PATH,
            new_additional_quest['map_slug'],
            new_additional_quest['map_name'],
            new_additional_quest['emote_slug'],
            new_additional_quest['emote_name'],
            new_additional_quest['class_slug'],
            new_additional_quest['class_name'],
            new_additional_quest['gear_slug'],
            new_additional_quest['gear_name'],
            new_additional_quest['reward'],
            quest_id=2
        ):
            print("✓ Дополнительное задание успешно сохранено!")
            print("✓ Еженедельное задание НЕ ИЗМЕНЕНО")
        else:
            print("✗ Ошибка: не удалось сохранить дополнительное задание в базу данных")
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

