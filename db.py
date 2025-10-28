# db.py
# Модуль для работы с SQLite базой данных

import sqlite3
import json
import time
import os
from typing import Dict, Optional, Any, List


def init_db(db_path: str) -> None:
    """
    Инициализирует базу данных и создает необходимые таблицы.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
    """
    # Создаем директорию если её нет
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Создаем таблицу users
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            real_name TEXT,
            psn_id TEXT,
            platforms TEXT,
            modes TEXT,
            goals TEXT,
            difficulties TEXT,
            trophies TEXT,
            updated_at INTEGER
        )
    ''')
    
    # Создаем индекс для быстрого поиска
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)
    ''')
    
    # Создаем таблицу trophies
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trophies (
            trophy_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trophy_name TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at INTEGER
        )
    ''')
    
    # Создаем индекс для быстрого поиска по названию трофея
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_trophies_name ON trophies(trophy_name)
    ''')
    
    # Создаем таблицу builds
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS builds (
            build_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            author TEXT NOT NULL,
            name TEXT NOT NULL,
            class TEXT NOT NULL,
            tags TEXT NOT NULL,
            description TEXT,
            photo_1 TEXT NOT NULL,
            photo_2 TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 0
        )
    ''')
    
    # Создаем индексы для builds
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_builds_user_id ON builds(user_id)
    ''')
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_builds_is_public ON builds(is_public)
    ''')
    
    conn.commit()
    conn.close()


def get_user(db_path: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает профиль пользователя по user_id.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
    
    Returns:
        Словарь с данными профиля или None если пользователь не найден
    """
    if not os.path.exists(db_path):
        return None
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, real_name, psn_id, platforms, modes, goals, difficulties, trophies, updated_at
        FROM users WHERE user_id = ?
    ''', (user_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return None
    
    # Преобразуем в словарь
    profile = {
        'user_id': row[0],
        'real_name': row[1],
        'psn_id': row[2],
        'platforms': [p.strip() for p in row[3].split(',') if p.strip()] if row[3] else [],
        'modes': [m.strip() for m in row[4].split(',') if m.strip()] if row[4] else [],
        'goals': [g.strip() for g in row[5].split(',') if g.strip()] if row[5] else [],
        'difficulties': [d.strip() for d in row[6].split(',') if d.strip()] if row[6] else [],
        'trophies': [t.strip() for t in row[7].split(',') if t.strip()] if row[7] else [],  # Массив названий трофеев
        'updated_at': row[8]
    }
    
    return profile


def upsert_user(db_path: str, user_id: int, profile_data: Dict[str, Any]) -> bool:
    """
    Сохраняет или обновляет профиль пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
        profile_data: Словарь с данными профиля
    
    Returns:
        True при успешном сохранении, иначе False
    """
    try:
        # Инициализируем БД если её нет
        if not os.path.exists(db_path):
            init_db(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Подготавливаем данные для сохранения
        current_time = int(time.time())
        
        # Преобразуем списки в строки через запятую
        platforms_str = ','.join(profile_data.get('platforms', []))
        modes_str = ','.join(profile_data.get('modes', []))
        goals_str = ','.join(profile_data.get('goals', []))
        difficulties_str = ','.join(profile_data.get('difficulties', []))
        # Трофеи сохраняем как строку через запятую
        trophies_list = profile_data.get('trophies', [])
        # Фильтруем пустые значения и сохраняем только непустые трофеи
        trophies_str = ','.join([t.strip() for t in trophies_list if t and t.strip()])
        
        # Проверяем существует ли пользователь
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None

        if exists:
            # UPDATE существующего пользователя БЕЗ поля trophies
            cursor.execute('''
                UPDATE users 
                SET real_name = ?, psn_id = ?, platforms = ?, modes = ?, 
                    goals = ?, difficulties = ?, updated_at = ?
                WHERE user_id = ?
            ''', (
                profile_data.get('real_name', ''),
                profile_data.get('psn_id', ''),
                platforms_str,
                modes_str,
                goals_str,
                difficulties_str,
                current_time,
                user_id
            ))
        else:
            # INSERT нового пользователя с пустым trophies
            cursor.execute('''
                INSERT INTO users 
                (user_id, real_name, psn_id, platforms, modes, goals, difficulties, trophies, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                profile_data.get('real_name', ''),
                profile_data.get('psn_id', ''),
                platforms_str,
                modes_str,
                goals_str,
                difficulties_str,
                trophies_str,
                current_time
            ))
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        return False


def delete_user(db_path: str, user_id: int) -> bool:
    """
    Удаляет профиль пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
    
    Returns:
        True при успешном удалении, иначе False
    """
    try:
        if not os.path.exists(db_path):
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        return False


def get_user_count(db_path: str) -> int:
    """
    Возвращает количество пользователей в базе данных.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Количество пользователей
    """
    try:
        if not os.path.exists(db_path):
            return 0
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM users')
        count = cursor.fetchone()[0]
        
        conn.close()
        
        return count
        
    except Exception:
        return 0


def create_build(db_path: str, build_data: Dict[str, Any]) -> Optional[int]:
    """
    Создает новый билд в базе данных.
    
    Args:
        db_path: Путь к файлу базы данных
        build_data: Словарь с данными билда (user_id, author, name, class, tags, description, photo_1, photo_2, is_public)
    
    Returns:
        build_id созданного билда или None при ошибке
    """
    try:
        if not os.path.exists(db_path):
            init_db(db_path)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        current_time = int(time.time())
        tags_str = ','.join(build_data.get('tags', []))
        
        cursor.execute('''
            INSERT INTO builds 
            (user_id, author, name, class, tags, description, photo_1, photo_2, created_at, is_public)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            build_data.get('user_id'),
            build_data.get('author', ''),
            build_data.get('name', ''),
            build_data.get('class', ''),
            tags_str,
            build_data.get('description', ''),
            build_data.get('photo_1', ''),
            build_data.get('photo_2', ''),
            current_time,
            build_data.get('is_public', 0)
        ))
        
        build_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return build_id
        
    except Exception as e:
        print(f"Ошибка создания билда: {e}")
        return None


def get_build(db_path: str, build_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает билд по build_id.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
    
    Returns:
        Словарь с данными билда или None если не найден
    """
    try:
        if not os.path.exists(db_path):
            return None
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT build_id, user_id, author, name, class, tags, description, 
                   photo_1, photo_2, created_at, is_public
            FROM builds WHERE build_id = ?
        ''', (build_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'build_id': row[0],
            'user_id': row[1],
            'author': row[2],
            'name': row[3],
            'class': row[4],
            'tags': [t.strip() for t in row[5].split(',') if t.strip()] if row[5] else [],
            'description': row[6],
            'photo_1': row[7],
            'photo_2': row[8],
            'created_at': row[9],
            'is_public': row[10]
        }
        
    except Exception as e:
        print(f"Ошибка получения билда: {e}")
        return None


def get_user_builds(db_path: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Получает все билды пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Список словарей с данными билдов
    """
    try:
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT build_id, user_id, author, name, class, tags, description, 
                   photo_1, photo_2, created_at, is_public
            FROM builds WHERE user_id = ?
            ORDER BY created_at DESC
        ''', (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        builds = []
        for row in rows:
            builds.append({
                'build_id': row[0],
                'user_id': row[1],
                'author': row[2],
                'name': row[3],
                'class': row[4],
                'tags': [t.strip() for t in row[5].split(',') if t.strip()] if row[5] else [],
                'description': row[6],
                'photo_1': row[7],
                'photo_2': row[8],
                'created_at': row[9],
                'is_public': row[10]
            })
        
        return builds
        
    except Exception as e:
        print(f"Ошибка получения билдов пользователя: {e}")
        return []


def get_public_builds(db_path: str) -> List[Dict[str, Any]]:
    """
    Получает все публичные билды.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Список словарей с данными публичных билдов
    """
    try:
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT build_id, user_id, author, name, class, tags, description, 
                   photo_1, photo_2, created_at, is_public
            FROM builds WHERE is_public = 1
            ORDER BY created_at DESC
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        builds = []
        for row in rows:
            builds.append({
                'build_id': row[0],
                'user_id': row[1],
                'author': row[2],
                'name': row[3],
                'class': row[4],
                'tags': [t.strip() for t in row[5].split(',') if t.strip()] if row[5] else [],
                'description': row[6],
                'photo_1': row[7],
                'photo_2': row[8],
                'created_at': row[9],
                'is_public': row[10]
            })
        
        return builds
        
    except Exception as e:
        print(f"Ошибка получения публичных билдов: {e}")
        return []


def update_build_visibility(db_path: str, build_id: int, user_id: int, is_public: int) -> bool:
    """
    Изменяет видимость билда (публичный/приватный).
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
        user_id: ID пользователя (для проверки прав)
        is_public: 1 для публичного, 0 для приватного
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        if not os.path.exists(db_path):
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE builds 
            SET is_public = ?
            WHERE build_id = ? AND user_id = ?
        ''', (is_public, build_id, user_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
        
    except Exception as e:
        print(f"Ошибка обновления видимости билда: {e}")
        return False


def delete_build(db_path: str, build_id: int, user_id: int) -> bool:
    """
    Удаляет билд из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
        user_id: ID пользователя (для проверки прав)
    
    Returns:
        True при успешном удалении, иначе False
    """
    try:
        if not os.path.exists(db_path):
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM builds 
            WHERE build_id = ? AND user_id = ?
        ''', (build_id, user_id))
        
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
        
    except Exception as e:
        print(f"Ошибка удаления билда: {e}")
        return False


def add_trophy_to_user(db_path: str, user_id: int, trophy_name: str) -> bool:
    """
    Добавляет трофей к списку трофеев пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
        trophy_name: Имя трофея с emoji для добавления (например, "Легенда Цусимы 🗡️")
    
    Returns:
        True при успешном добавлении, иначе False
    """
    try:
        if not os.path.exists(db_path):
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Получаем текущий список трофеев
        cursor.execute('SELECT trophies FROM users WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        
        if not row:
            conn.close()
            return False
        
        current_trophies = row[0] or ""
        
        # Обрабатываем случай когда в базе может быть '[]' как строка
        if current_trophies == '[]':
            current_trophies = ""
        
        # Разбиваем строку на список, добавляем новый трофей если его нет
        trophy_list = [t.strip() for t in current_trophies.split(',') if t.strip()]
        
        if trophy_name not in trophy_list:
            trophy_list.append(trophy_name)
            new_trophies = ','.join(trophy_list)
            
            # Обновляем поле trophies
            cursor.execute('''
                UPDATE users 
                SET trophies = ?, updated_at = ?
                WHERE user_id = ?
            ''', (new_trophies, int(time.time()), user_id))
            
            success = cursor.rowcount > 0
            conn.commit()
            conn.close()
            
            return success
        else:
            # Трофей уже есть
            conn.close()
            return True
            
    except Exception as e:
        print(f"Ошибка добавления трофея пользователю: {e}")
        return False


def get_all_users(db_path: str) -> List[Dict[str, Any]]:
    """
    Получает список всех пользователей из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Список словарей с данными пользователей (user_id и psn_id)
    """
    try:
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT user_id, psn_id 
            FROM users 
            WHERE psn_id IS NOT NULL AND psn_id != ''
            ORDER BY psn_id COLLATE NOCASE
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'user_id': row[0],
                'psn_id': row[1]
            })
        
        return users
        
    except Exception as e:
        print(f"Ошибка получения списка пользователей: {e}")
        return []


# Функции для работы с трофеями

def sync_trophies_from_json(db_path: str, json_path: str) -> None:
    """
    Синхронизирует трофеи из JSON файла с базой данных.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
        json_path: Путь к JSON файлу с трофеями
    """
    try:
        if not os.path.exists(json_path):
            print(f"JSON файл не найден: {json_path}")
            return
        
        # Читаем JSON файл
        with open(json_path, 'r', encoding='utf-8') as f:
            trophies_data = json.load(f)
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        current_time = int(time.time())
        
        for trophy_data in trophies_data:
            trophy_name = trophy_data.get('name', '')
            description = trophy_data.get('description', '')
            
            if not trophy_name:
                continue
            
            # Проверяем, существует ли трофей
            cursor.execute('SELECT trophy_id FROM trophies WHERE trophy_name = ?', (trophy_name,))
            existing = cursor.fetchone()
            
            if existing:
                # Обновляем описание существующего трофея
                cursor.execute('''
                    UPDATE trophies 
                    SET description = ? 
                    WHERE trophy_name = ?
                ''', (description, trophy_name))
                print(f"Обновлен трофей: {trophy_name}")
            else:
                # Добавляем новый трофей
                cursor.execute('''
                    INSERT INTO trophies (trophy_name, description, created_at)
                    VALUES (?, ?, ?)
                ''', (trophy_name, description, current_time))
                print(f"Добавлен новый трофей: {trophy_name}")
        
        # Удаляем трофеи, которых нет в JSON
        json_trophy_names = {trophy_data.get('name', '') for trophy_data in trophies_data if trophy_data.get('name')}
        cursor.execute('SELECT trophy_id, trophy_name FROM trophies')
        db_trophies = cursor.fetchall()
        
        for trophy_id, trophy_name in db_trophies:
            if trophy_name not in json_trophy_names:
                cursor.execute('DELETE FROM trophies WHERE trophy_id = ?', (trophy_id,))
                print(f"Удален трофей: {trophy_name}")
        
        conn.commit()
        conn.close()
        print("Синхронизация трофеев завершена")
        
    except Exception as e:
        print(f"Ошибка синхронизации трофеев: {e}")


def get_all_trophies(db_path: str) -> List[tuple]:
    """
    Получает все трофеи из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
        
    Returns:
        Список кортежей (trophy_id, trophy_name, description)
    """
    try:
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT trophy_id, trophy_name, description
            FROM trophies
            ORDER BY trophy_id
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        return rows
        
    except Exception as e:
        print(f"Ошибка получения трофеев: {e}")
        return []


def get_trophy_by_id(db_path: str, trophy_id: int) -> Optional[tuple]:
    """
    Получает трофей по ID.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
        trophy_id: ID трофея
        
    Returns:
        Кортеж (trophy_id, trophy_name, description) или None
    """
    try:
        if not os.path.exists(db_path):
            return None
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT trophy_id, trophy_name, description
            FROM trophies
            WHERE trophy_id = ?
        ''', (trophy_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row
        
    except Exception as e:
        print(f"Ошибка получения трофея по ID: {e}")
        return None


def get_trophy_by_name(db_path: str, trophy_name: str) -> Optional[tuple]:
    """
    Получает трофей по названию.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
        trophy_name: Название трофея
        
    Returns:
        Кортеж (trophy_id, trophy_name, description) или None
    """
    try:
        if not os.path.exists(db_path):
            return None
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT trophy_id, trophy_name, description
            FROM trophies
            WHERE trophy_name = ?
        ''', (trophy_name,))
        
        row = cursor.fetchone()
        conn.close()
        
        return row
        
    except Exception as e:
        print(f"Ошибка получения трофея по названию: {e}")
        return None


