# trophy_config.py
# Модуль для загрузки конфига трофеев (используется и в API и в боте)

import os
import json
from typing import Dict, Any, Optional


def load_trophy_config() -> Dict[str, Any]:
    """
    Загружает конфиг трофеев из JSON файла.
    Путь к файлу определяется относительно директории приложения или фронтенда.
    """
    config_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'tsushimaru_app', 'docs', 'trophies.json'),
        '/root/tsushimaru_app/docs/trophies.json',
        os.path.join(os.path.dirname(__file__), 'trophies.json'),
        './trophies.json'
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки конфига из {path}: {e}")
                continue
    
    raise Exception("Не удалось загрузить конфиг трофеев")


def find_trophy_by_key(config: Dict[str, Any], trophy_key: str) -> Optional[Dict[str, Any]]:
    """
    Находит трофей по ключу в конфиге.
    
    Args:
        config: Загруженный конфиг трофеев
        trophy_key: Ключ трофея для поиска
    
    Returns:
        Словарь с данными трофея или None если не найден
    """
    trophies = config.get('trophies', [])
    for trophy in trophies:
        if trophy.get('key') == trophy_key:
            return trophy
    return None

