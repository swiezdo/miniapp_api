#!/usr/bin/env python3
# quest_generator.py
# Скрипт для автоматической генерации заданий HellMode каждую субботу в 9:00 МСК

import os
import sys
import json
import random
from datetime import datetime, timezone, timedelta
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
    
    required_fields = ['map', 'emote', 'class', 'gear']
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
    emote_name = emote_item['name']
    class_slug = class_item['slug']
    class_name = class_item['name']
    gear_slug = gear_item['slug']
    gear_name = gear_item['name']
    
    # Рассчитываем награду
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
    
    Args:
        new_quest: Новое задание
        *current_quests: Текущие задания (может быть несколько, None игнорируются)
    
    Returns:
        True если есть повторения, иначе False
    """
    if not current_quests:
        return False
    
    # Проверяем каждое поле (кроме reward)
    fields_to_check = ['map_slug', 'emote_slug', 'class_slug', 'gear_slug']
    
    for current_quest in current_quests:
        if not current_quest:
            continue
        
        for field in fields_to_check:
            # Поля в БД теперь имеют те же названия
            if new_quest[field] == current_quest[field]:
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
    
    # Получаем текущие задания из БД
    current_weekly_quest = get_current_hellmode_quest(DB_PATH, quest_id=1)
    current_additional_quest = get_current_hellmode_quest(DB_PATH, quest_id=2)
    
    # Если хотя бы одно задание отсутствует или пустое - генерируем
    if not current_weekly_quest or not current_additional_quest:
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
        
        # Получаем текущие задания
        current_weekly_quest = get_current_hellmode_quest(DB_PATH, quest_id=1)
        current_additional_quest = get_additional_hellmode_quest(DB_PATH)
        
        if current_weekly_quest:
            print(f"Текущее еженедельное задание:")
            map_name = current_weekly_quest.get('map_name', '')
            if map_name:
                print(f"  Карта: {map_name} ({current_weekly_quest['map_slug']})")
            else:
                print(f"  Карта: {current_weekly_quest['map_slug']}")
            print(f"  Эмоция: {current_weekly_quest.get('emote_name', '')} ({current_weekly_quest['emote_slug']})")
            print(f"  Класс: {current_weekly_quest.get('class_name', '')} ({current_weekly_quest['class_slug']})")
            print(f"  Снаряжение: {current_weekly_quest.get('gear_name', '')} ({current_weekly_quest['gear_slug']})")
            print(f"  Награда: {current_weekly_quest['reward']}")
        else:
            print("Текущее еженедельное задание отсутствует (будет создано новое).")
        
        if current_additional_quest:
            print(f"\nТекущее дополнительное задание:")
            map_name = current_additional_quest.get('map_name', '')
            if map_name:
                print(f"  Карта: {map_name} ({current_additional_quest['map_slug']})")
            else:
                print(f"  Карта: {current_additional_quest['map_slug']}")
            print(f"  Эмоция: {current_additional_quest.get('emote_name', '')} ({current_additional_quest['emote_slug']})")
            print(f"  Класс: {current_additional_quest.get('class_name', '')} ({current_additional_quest['class_slug']})")
            print(f"  Снаряжение: {current_additional_quest.get('gear_name', '')} ({current_additional_quest['gear_slug']})")
            print(f"  Награда: {current_additional_quest['reward']}")
        else:
            print("\nТекущее дополнительное задание отсутствует (будет создано новое).")
        
        # Генерируем еженедельное задание с проверкой на повторения
        print("\nГенерация еженедельного задания...")
        new_weekly_quest = None
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            generated = generate_random_quest(hellmode_config)
            
            if not has_duplicates(generated, current_weekly_quest, current_additional_quest):
                new_weekly_quest = generated
                print(f"Еженедельное задание сгенерировано с попытки {attempt}.")
                break
            else:
                print(f"Попытка {attempt}: обнаружены повторения, перерандомивание...")
        
        # Если после всех попыток есть повторения - принимаем последний результат
        if not new_weekly_quest:
            print(f"Внимание: после {MAX_ATTEMPTS} попыток все еще есть повторения.")
            print("Принимается последний сгенерированный вариант.")
            new_weekly_quest = generate_random_quest(hellmode_config)
        
        # Генерируем дополнительное задание с проверкой на повторения
        print("\nГенерация дополнительного задания...")
        new_additional_quest = None
        
        for attempt in range(1, MAX_ATTEMPTS + 1):
            generated = generate_random_quest(hellmode_config)
            
            # Проверяем, что оно не совпадает с еженедельным и текущими заданиями
            if not has_duplicates(generated, new_weekly_quest, current_weekly_quest, current_additional_quest):
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
        
        print(f"\nНовое еженедельное задание:")
        print(f"  Карта: {new_weekly_quest['map_name']} ({new_weekly_quest['map_slug']})")
        print(f"  Эмоция: {new_weekly_quest['emote_name']} ({new_weekly_quest['emote_slug']})")
        print(f"  Класс: {new_weekly_quest['class_name']} ({new_weekly_quest['class_slug']})")
        print(f"  Снаряжение: {new_weekly_quest['gear_name']} ({new_weekly_quest['gear_slug']})")
        print(f"  Награда: {new_weekly_quest['reward']}")
        
        print(f"\nНовое дополнительное задание:")
        print(f"  Карта: {new_additional_quest['map_name']} ({new_additional_quest['map_slug']})")
        print(f"  Эмоция: {new_additional_quest['emote_name']} ({new_additional_quest['emote_slug']})")
        print(f"  Класс: {new_additional_quest['class_name']} ({new_additional_quest['class_slug']})")
        print(f"  Снаряжение: {new_additional_quest['gear_name']} ({new_additional_quest['gear_slug']})")
        print(f"  Награда: {new_additional_quest['reward']}")
        
        # Сохраняем еженедельное задание в БД
        print("\nСохранение еженедельного задания в базу данных...")
        try:
            result = update_hellmode_quest(
                DB_PATH,
                new_weekly_quest['map_slug'],
                new_weekly_quest['map_name'],
                new_weekly_quest['emote_slug'],
                new_weekly_quest['emote_name'],
                new_weekly_quest['class_slug'],
                new_weekly_quest['class_name'],
                new_weekly_quest['gear_slug'],
                new_weekly_quest['gear_name'],
                new_weekly_quest['reward'],
                quest_id=1
            )
            if result:
                print("Еженедельное задание успешно сохранено!")
                # Проверяем, что данные действительно сохранились
                saved_quest = get_current_hellmode_quest(DB_PATH, quest_id=1)
                if saved_quest and saved_quest.get('map_slug') == new_weekly_quest['map_slug']:
                    print("✓ Проверка: еженедельное задание подтверждено в БД")
                else:
                    print("⚠ ВНИМАНИЕ: задание не найдено в БД после сохранения!")
                    sys.exit(1)
            else:
                print("Ошибка: не удалось сохранить еженедельное задание в базу данных")
                sys.exit(1)
        except Exception as e:
            print(f"Критическая ошибка при сохранении еженедельного задания: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        # Сохраняем дополнительное задание в БД
        print("Сохранение дополнительного задания в базу данных...")
        try:
            result = update_hellmode_quest(
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
            )
            if result:
                print("Дополнительное задание успешно сохранено!")
                # Проверяем, что данные действительно сохранились
                saved_quest = get_additional_hellmode_quest(DB_PATH)
                if saved_quest and saved_quest.get('map_slug') == new_additional_quest['map_slug']:
                    print("✓ Проверка: дополнительное задание подтверждено в БД")
                else:
                    print("⚠ ВНИМАНИЕ: задание не найдено в БД после сохранения!")
                    sys.exit(1)
            else:
                print("Ошибка: не удалось сохранить дополнительное задание в базу данных")
                sys.exit(1)
        except Exception as e:
            print(f"Критическая ошибка при сохранении дополнительного задания: {e}")
            import traceback
            traceback.print_exc()
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

