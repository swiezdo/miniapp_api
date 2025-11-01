# mastery_config.py
# Модуль для загрузки конфига мастерства (используется и в API и в боте)

import os
import json
from typing import Dict, Any


def load_mastery_config() -> Dict[str, Any]:
    """
    Загружает конфиг мастерства из JSON файла.
    Путь к файлу определяется относительно директории приложения или фронтенда.
    """
    config_paths = [
        os.path.join(os.path.dirname(__file__), '..', 'tsushimaru_app', 'docs', 'mastery-config.json'),
        '/root/tsushimaru_app/docs/mastery-config.json',
        os.path.join(os.path.dirname(__file__), 'mastery-config.json'),
        './mastery-config.json'
    ]
    
    for path in config_paths:
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Ошибка загрузки конфига из {path}: {e}")
                continue
    
    raise Exception("Не удалось загрузить конфиг мастерства")

