# season_trophy_config.py
# Модуль для загрузки конфига сезонных трофеев

import os
import json
from typing import Dict, Any, Optional, List


def load_season_trophy_config() -> List[Dict[str, Any]]:
    """
    Загружает конфиг сезонных трофеев из JSON файла.
    Путь к файлу определяется относительно директории приложения или фронтенда.
    
    Returns:
        Список трофеев (массив объектов)
    """
    config_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'tsushimaru_app', 'docs', 'assets', 'data', 'season_trophy.json'),
        os.path.join(os.path.dirname(__file__), '..', 'tsushimaru_app', 'docs', 'season_trophy.json'),
        '/root/tsushimaru_app/docs/assets/data/season_trophy.json',
        '/root/tsushimaru_app/docs/season_trophy.json',
        os.path.join(os.path.dirname(__file__), 'season_trophy.json'),
        './season_trophy.json'
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Проверяем, что это массив
                    if isinstance(data, list):
                        return data
                    # Если это объект с ключом trophies, возвращаем его
                    if isinstance(data, dict) and 'trophies' in data:
                        return data['trophies']
                    return []
            except Exception as e:
                print(f"Ошибка загрузки конфига сезонных трофеев из {path}: {e}")
                continue
    
    return []


def find_season_trophy_by_key(trophy_key: str) -> Optional[Dict[str, Any]]:
    """
    Находит сезонный трофей по ключу в конфиге.
    
    Args:
        trophy_key: Ключ трофея для поиска
    
    Returns:
        Словарь с данными трофея или None если не найден
    """
    config = load_season_trophy_config()
    for trophy in config:
        if trophy.get('key') == trophy_key:
            return trophy
    return None




