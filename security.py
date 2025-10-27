# security.py
# Модуль для валидации Telegram WebApp initData

import hashlib
import hmac
import json
import urllib.parse
from typing import Dict, Optional


def validate_init_data(init_data_raw: str, bot_token: str) -> Optional[Dict]:
    """
    Валидирует Telegram WebApp initData по алгоритму HMAC-SHA256.
    
    Args:
        init_data_raw: Строка initData из window.Telegram.WebApp.initData
        bot_token: Токен бота (формат: "123456:ABC-DEF...")
    
    Returns:
        Словарь с распарсенными данными при успехе, иначе None
    """
    if not init_data_raw or not bot_token:
        return None
    
    try:
        # Парсим query string
        parsed_data = urllib.parse.parse_qs(init_data_raw)
        
        # Извлекаем hash и остальные данные
        if 'hash' not in parsed_data:
            return None
        
        received_hash = parsed_data['hash'][0]
        
        # Создаем строку для проверки (все поля кроме hash, отсортированные по ключу)
        data_check_string_parts = []
        
        for key in sorted(parsed_data.keys()):
            if key != 'hash':
                value = parsed_data[key][0]
                data_check_string_parts.append(f"{key}={value}")
        
        data_check_string = '\n'.join(data_check_string_parts)
        
        # Создаем секретный ключ из токена бота
        secret_key = hmac.new(
            "WebAppData".encode('utf-8'),
            bot_token.encode('utf-8'),
            hashlib.sha256
        ).digest()
        
        # Вычисляем HMAC-SHA256
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем хеши
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        
        # Преобразуем в обычный словарь для удобства
        result = {}
        for key, value_list in parsed_data.items():
            if key != 'hash':
                value = value_list[0]
                # Парсим JSON поля (user, receiver, chat)
                if key in ['user', 'receiver', 'chat']:
                    try:
                        result[key] = json.loads(value)
                    except json.JSONDecodeError:
                        result[key] = value
                else:
                    result[key] = value
        
        return result
        
    except Exception:
        return None


def get_user_id_from_init_data(init_data: Dict) -> Optional[int]:
    """
    Извлекает user_id из валидных данных initData.
    
    Args:
        init_data: Словарь с данными initData (результат validate_init_data)
    
    Returns:
        user_id (int) при успехе, иначе None
    """
    if not init_data or 'user' not in init_data:
        return None
    
    try:
        user_data = init_data['user']
        if isinstance(user_data, dict) and 'id' in user_data:
            return int(user_data['id'])
    except (ValueError, TypeError):
        pass
    
    return None


def is_init_data_valid(init_data_raw: str, bot_token: str) -> bool:
    """
    Простая проверка валидности initData без возврата данных.
    
    Args:
        init_data_raw: Строка initData из window.Telegram.WebApp.initData
        bot_token: Токен бота
    
    Returns:
        True если initData валиден, иначе False
    """
    return validate_init_data(init_data_raw, bot_token) is not None


# Тестирование (запускать только если файл запущен напрямую)
if __name__ == "__main__":
    # Пример тестирования
    test_bot_token = "123456:ABC-DEF1234567890"
    test_init_data = "query_id=AAHdF6I...&user=%7B%22id%22%3A123456789%2C%22first_name%22%3A%22Test%22%7D&auth_date=1697123456&hash=abc123..."
    
    print("Тестирование модуля security.py...")
    print(f"Bot token: {test_bot_token}")
    print(f"Init data: {test_init_data[:50]}...")
    
    result = validate_init_data(test_init_data, test_bot_token)
    if result:
        print("✅ InitData валиден!")
        print(f"Данные: {result}")
        user_id = get_user_id_from_init_data(result)
        print(f"User ID: {user_id}")
    else:
        print("❌ InitData невалиден")
