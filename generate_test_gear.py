#!/usr/bin/env python3
# generate_test_gear.py
# Скрипт для генерации тестовых предметов снаряжения

import os
import sys
import json
import random
import re
from pathlib import Path
from dotenv import load_dotenv

# Добавляем путь к модулю db
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import create_gear_item

# Загружаем переменные окружения
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "/root/miniapp_api/app.db")
GEAR_JSON_PATH = os.path.join(os.path.dirname(__file__), '..', 'tsushimaru_app', 'docs', 'assets', 'data', 'gear.json')


def parse_property(prop_string):
    """Парсит свойство из формата 'Название|[min, max]|unit' (unit может быть пустым)"""
    if not prop_string or not isinstance(prop_string, str):
        return None
    
    # Unit может быть пустым, поэтому используем .* вместо .+
    match = re.match(r'^(.+?)\|\[([\d.]+),\s*([\d.]+)\]\|(.*)$', prop_string)
    if not match:
        return None
    
    name = match.group(1).strip()
    min_str = match.group(2)
    max_str = match.group(3)
    min_val = float(min_str)
    max_val = float(max_str)
    unit = match.group(4).strip()  # Может быть пустой строкой
    
    # Определяем, есть ли десятичные знаки в исходных строках диапазона
    has_decimals = '.' in min_str or '.' in max_str
    
    return {
        'name': name,
        'range': [min_val, max_val],
        'unit': unit,
        'has_decimals': has_decimals
    }


def generate_property_value(min_val, max_val, use_max=False, has_decimals=False):
    """Генерирует значение свойства"""
    if use_max:
        return max_val
    
    if has_decimals:
        random_val = random.uniform(min_val, max_val)
        return round(random_val * 10) / 10
    else:
        return random.randint(int(min_val), int(max_val))


def format_property_value(value, unit):
    """Форматирует значение с единицей"""
    if not unit or unit == '':
        return str(value)
    # Добавляем пробел перед единицей (например, "3.8 сек." вместо "3.8сек.")
    return f"{value} {unit}"


def weighted_random(options):
    """Генерирует случайное значение с заданными вероятностями"""
    total = sum(opt['probability'] for opt in options)
    random_val = random.random() * total
    
    current = 0
    for option in options:
        current += option['probability']
        if random_val <= current:
            return option['value']
    
    return options[-1]['value']


def generate_gear_item(item, category, gear_data):
    """Генерирует снаряжение с рандомными свойствами"""
    # Находим словари свойств
    properties_dict = None
    cursed_perks = None
    legendary_charm_props = None
    
    for section in gear_data:
        if '_properties' in section:
            properties_dict = section['_properties']
        if 'cursed_gear_perks' in section:
            cursed_perks = section['cursed_gear_perks']
        if 'legendary_charm_class_props' in section:
            legendary_charm_props = section['legendary_charm_class_props']
    
    if not properties_dict:
        return None
    
    is_legendary = item.get('isLegendary') == 1
    result = {
        'key': item['key'],
        'name': item['name'],
        'type': None,
        'ki': None,
        'prop1': None,
        'prop1_value': None,
        'prop2': None,
        'prop2_value': None,
        'perk1': None,
        'perk2': None
    }
    
    # Подготовка списков
    prop1_list = list(item.get('prop1', []))
    prop2_list = list(item.get('prop2', []))
    perk_list = list(item.get('perk', []))
    
    # Для легендарных оберегов добавляем свойства класса
    if is_legendary and category == 'charm' and legendary_charm_props:
        classes = list(legendary_charm_props.keys())
        selected_class = random.choice(classes)
        class_props = legendary_charm_props[selected_class]
        
        if class_props.get('prop1'):
            prop1_list.extend(class_props['prop1'])
        if class_props.get('prop2'):
            prop2_list.extend(class_props['prop2'])
        if class_props.get('perk'):
            perk_list.extend(class_props['perk'])
    
    if is_legendary:
        # ЛЕГЕНДАРНЫЕ ПРЕДМЕТЫ
        result['type'] = 'legendary'
        
        # Рандомим ki: 80, 110 или 120 (70% вероятность 120)
        result['ki'] = weighted_random([
            {'value': 80, 'probability': 0.15},
            {'value': 110, 'probability': 0.15},
            {'value': 120, 'probability': 0.70}
        ])
        
        # Рандомим prop1 (максимальное значение)
        # ВАЖНО: prop1 обязателен для легендарных предметов
        if prop1_list:
            prop1_key = random.choice(prop1_list)
            prop1_data = parse_property(prop1_key)
            if prop1_data:
                result['prop1'] = prop1_data['name']
                max_value = generate_property_value(prop1_data['range'][0], prop1_data['range'][1], True, prop1_data.get('has_decimals', False))
                result['prop1_value'] = format_property_value(max_value, prop1_data['unit'])
        
        # Рандомим prop2 (исключая prop1, максимальное значение)
        if prop2_list and result['prop1']:
            # Исключаем prop1 из списка prop2
            prop1_key = None
            for p in prop1_list:
                parsed = parse_property(p)
                if parsed and parsed['name'] == result['prop1']:
                    prop1_key = p
                    break
            
            filtered_prop2_list = [p for p in prop2_list if p != prop1_key] if prop1_key else prop2_list
            
            if filtered_prop2_list:
                prop2_key = random.choice(filtered_prop2_list)
                prop2_data = parse_property(prop2_key)
                if prop2_data:
                    result['prop2'] = prop2_data['name']
                    max_value = generate_property_value(prop2_data['range'][0], prop2_data['range'][1], True, prop2_data.get('has_decimals', False))
                    result['prop2_value'] = format_property_value(max_value, prop2_data['unit'])
        
        # Рандомим perk1
        if perk_list:
            result['perk1'] = random.choice(perk_list)
        
        # Рандомим perk2 если ki = 120
        if result['ki'] == 120 and len(perk_list) > 1:
            available_perks = [p for p in perk_list if p != result['perk1']]
            if available_perks:
                result['perk2'] = random.choice(available_perks)
    
    else:
        # НЕЛЕГЕНДАРНЫЕ ПРЕДМЕТЫ
        # Рандомим type: uncommon (30%), rare (30%), epic (30%), cursed (10%)
        result['type'] = weighted_random([
            {'value': 'uncommon', 'probability': 0.30},
            {'value': 'rare', 'probability': 0.30},
            {'value': 'epic', 'probability': 0.30},
            {'value': 'cursed', 'probability': 0.10}
        ])
        
        # Рандомим ki в зависимости от type
        if result['type'] == 'uncommon':
            result['ki'] = weighted_random([
                {'value': 35, 'probability': 0.25},
                {'value': 80, 'probability': 0.75}
            ])
        elif result['type'] == 'rare':
            result['ki'] = weighted_random([
                {'value': 35, 'probability': 0.15},
                {'value': 80, 'probability': 0.15},
                {'value': 105, 'probability': 0.70}
            ])
        elif result['type'] == 'epic':
            result['ki'] = weighted_random([
                {'value': 80, 'probability': 0.10},
                {'value': 105, 'probability': 0.10},
                {'value': 110, 'probability': 0.10},
                {'value': 120, 'probability': 0.70}
            ])
        elif result['type'] == 'cursed':
            result['ki'] = random.randint(20, 100)
        
        # Рандомим prop1 (30% шанс на максимум, для cursed - 15%)
        if prop1_list:
            max_chance = 0.15 if result['type'] == 'cursed' else 0.30
            use_max = random.random() < max_chance
            prop1_key = random.choice(prop1_list)
            prop1_data = parse_property(prop1_key)
            if prop1_data:
                result['prop1'] = prop1_data['name']
                value = generate_property_value(prop1_data['range'][0], prop1_data['range'][1], use_max, prop1_data.get('has_decimals', False))
                result['prop1_value'] = format_property_value(value, prop1_data['unit'])
        
        # Рандомим prop2 только для epic (30% шанс на максимум)
        # ВАЖНО: для epic prop2 обязателен
        if result['type'] == 'epic' and prop2_list and result['prop1']:
            # Исключаем из prop2_list ТОЛЬКО тот элемент, который совпадает с выбранным prop1
            # Ищем полную строку prop1Key в prop1_list по имени
            prop1_key = None
            for p in prop1_list:
                parsed = parse_property(p)
                if parsed and parsed['name'] == result['prop1']:
                    prop1_key = p  # Это полная строка вида "Урон в ближнем бою|[5, 12]|%"
                    break
            
            # Исключаем из prop2_list ТОЛЬКО найденный prop1_key (если он там есть)
            if prop1_key:
                filtered_prop2_list = [p for p in prop2_list if p != prop1_key]
            else:
                # Если prop1_key не найден, используем весь prop2_list
                filtered_prop2_list = prop2_list
            
            # Для epic prop2 обязателен, поэтому если после фильтрации список пуст, используем весь prop2_list
            # (это может произойти только если prop2_list содержал только один элемент, и это был prop1_key)
            if not filtered_prop2_list:
                filtered_prop2_list = prop2_list
            
            # Генерируем prop2
            if filtered_prop2_list:
                max_chance = 0.15 if result['type'] == 'cursed' else 0.30
                use_max = random.random() < max_chance
                prop2_key = random.choice(filtered_prop2_list)
                prop2_data = parse_property(prop2_key)
                if prop2_data:
                    result['prop2'] = prop2_data['name']
                    value = generate_property_value(prop2_data['range'][0], prop2_data['range'][1], use_max, prop2_data.get('has_decimals', False))
                    result['prop2_value'] = format_property_value(value, prop2_data['unit'])
        
        # Рандомим perk
        if result['type'] == 'cursed':
            # cursed: только из cursed_gear_perks
            if cursed_perks and item['key'] in cursed_perks and cursed_perks[item['key']]:
                result['perk1'] = random.choice(cursed_perks[item['key']])
                result['perk2'] = None
        elif result['type'] == 'uncommon':
            # uncommon: 1 perk из обычного списка
            if perk_list:
                result['perk1'] = random.choice(perk_list)
                result['perk2'] = None
        elif result['type'] in ['rare', 'epic']:
            # rare/epic: если ki = 120 то 2 перка, иначе 1
            if perk_list:
                result['perk1'] = random.choice(perk_list)
                if result['ki'] == 120 and len(perk_list) > 1:
                    available_perks = [p for p in perk_list if p != result['perk1']]
                    if available_perks:
                        result['perk2'] = random.choice(available_perks)
                else:
                    result['perk2'] = None
    
    return result


def main():
    """Главная функция скрипта"""
    try:
        # Загружаем данные из gear.json
        print(f"Загрузка данных из {GEAR_JSON_PATH}...")
        with open(GEAR_JSON_PATH, 'r', encoding='utf-8') as f:
            gear_data = json.load(f)
        
        # Находим все категории и предметы
        categories = []
        for section in gear_data:
            if 'category' in section:
                categories.append({
                    'category': section['category'],
                    'items': section.get('items', [])
                })
        
        if not categories:
            print("❌ Не найдено категорий в gear.json")
            sys.exit(1)
        
        # Выбираем случайные предметы из разных категорий
        selected_items = []
        for _ in range(15):
            category_data = random.choice(categories)
            if category_data['items']:
                item = random.choice(category_data['items'])
                selected_items.append({
                    'item': item,
                    'category': category_data['category']
                })
        
        print(f"\nГенерация 15 случайных предметов...")
        
        # Генерируем предметы и записываем в БД
        test_user_id = 1  # Тестовый user_id
        
        for i, selected in enumerate(selected_items, 1):
            item = selected['item']
            category = selected['category']
            
            print(f"\n{i}. {item['name']} ({category})")
            
            # Генерируем предмет
            gear_item = generate_gear_item(item, category, gear_data)
            
            if not gear_item:
                print(f"   ❌ Ошибка генерации предмета")
                continue
            
            print(f"   Тип: {gear_item['type']}, KI: {gear_item['ki']}")
            print(f"   Prop1: {gear_item['prop1']} = {gear_item['prop1_value']}")
            if gear_item['prop2']:
                print(f"   Prop2: {gear_item['prop2']} = {gear_item['prop2_value']}")
            print(f"   Perk1: {gear_item['perk1']}")
            if gear_item['perk2']:
                print(f"   Perk2: {gear_item['perk2']}")
            
            # Записываем в БД
            gear_id = create_gear_item(DB_PATH, test_user_id, gear_item)
            
            if gear_id:
                print(f"   ✅ Записано в БД с ID: {gear_id}")
            else:
                print(f"   ❌ Ошибка записи в БД")
        
        print(f"\n✅ Генерация завершена!")
        
    except FileNotFoundError:
        print(f"❌ Файл {GEAR_JSON_PATH} не найден")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка парсинга JSON: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

