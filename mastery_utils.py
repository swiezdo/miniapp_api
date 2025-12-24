# mastery_utils.py
# Утилиты для работы с мастерством

from typing import List, Dict, Optional, Any
import json


def find_category_by_key(config: Dict[str, Any], category_key: str) -> Optional[Dict[str, Any]]:
    """
    Находит категорию в конфиге мастерства по ключу.
    
    Args:
        config: Конфиг мастерства (словарь с ключом 'categories')
        category_key: Ключ категории для поиска
    
    Returns:
        Словарь с данными категории или None если не найдена
    """
    if not config or not config.get('categories'):
        return None
    
    for cat in config.get('categories', []):
        if isinstance(cat, dict) and cat.get('key') == category_key:
            return cat
    
    return None


def parse_tags(tags: str) -> List[str]:
    """
    Парсит теги из строки.
    
    Поддерживает два формата:
    - JSON строка (массив): ["tag1", "tag2"]
    - Строка через запятую: "tag1, tag2"
    
    Args:
        tags: Строка с тегами
    
    Returns:
        Список тегов
    """
    if not tags:
        return []
    
    try:
        # Пытаемся распарсить как JSON
        if tags.startswith('[') and tags.endswith(']'):
            tags_list = json.loads(tags)
            if isinstance(tags_list, list):
                return [str(t).strip() for t in tags_list if t and str(t).strip()]
    except (json.JSONDecodeError, TypeError):
        pass
    
    # Если не удалось распарсить как JSON, пытаемся как строку через запятую
    try:
        tags_list = [t.strip() for t in tags.split(',') if t.strip()]
        return tags_list
    except Exception:
        return []

