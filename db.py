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
    
    # Создаем таблицу users (без колонки trophies, с avatar_url)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            real_name TEXT,
            psn_id TEXT,
            platforms TEXT,
            modes TEXT,
            goals TEXT,
            difficulties TEXT,
            avatar_url TEXT
        )
    ''')
    
    # Создаем индекс для быстрого поиска
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)
    ''')
    
    # Чистим возможные остатки старой схемы, если они есть
    # 1) Удаляем таблицу trophies, если существует
    cursor.execute('DROP TABLE IF EXISTS trophies')
    # 2) Удаляем индекс idx_trophies_name, если существует (на случай старых версий SQLite, где DROP TABLE не удалил индекс)
    try:
        cursor.execute('DROP INDEX IF EXISTS idx_trophies_name')
    except Exception:
        pass
    # 3) Миграция: удалить trophies и добавить avatar_url
    try:
        cursor.execute("PRAGMA table_info(users)")
        columns_info = cursor.fetchall()
        column_names = [c[1] for c in columns_info]
        
        needs_migration = False
        migration_fields = []
        
        # Собираем список полей для миграции
        if 'user_id' in column_names:
            migration_fields.append('user_id INTEGER PRIMARY KEY')
        if 'real_name' in column_names:
            migration_fields.append('real_name TEXT')
        if 'psn_id' in column_names:
            migration_fields.append('psn_id TEXT')
        if 'platforms' in column_names:
            migration_fields.append('platforms TEXT')
        if 'modes' in column_names:
            migration_fields.append('modes TEXT')
        if 'goals' in column_names:
            migration_fields.append('goals TEXT')
        if 'difficulties' in column_names:
            migration_fields.append('difficulties TEXT')
        
        # Добавляем avatar_url если его нет
        if 'avatar_url' not in column_names:
            migration_fields.append('avatar_url TEXT')
            needs_migration = True
        
        # Убираем trophies если он есть
        if 'trophies' in column_names:
            needs_migration = True
        
        if needs_migration:
            # Пересоздаем таблицу users с новой структурой
            cursor.execute(f'''
                CREATE TABLE IF NOT EXISTS users_new (
                    {', '.join(migration_fields)}
                )
            ''')
            
            # Копируем данные (исключаем trophies, добавляем avatar_url)
            fields_to_copy = [f for f in ['user_id', 'real_name', 'psn_id', 'platforms', 'modes', 'goals', 'difficulties'] if f in column_names]
            cursor.execute(f'''
                INSERT INTO users_new ({', '.join(fields_to_copy)})
                SELECT {', '.join(fields_to_copy)} FROM users
            ''')
            
            # Переименовываем таблицы
            cursor.execute('DROP TABLE users')
            cursor.execute('ALTER TABLE users_new RENAME TO users')
            # Восстанавливаем индекс по user_id
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)')
        elif 'avatar_url' not in column_names:
            # Если миграция не нужна, но avatar_url нет - добавляем колонку напрямую
            cursor.execute('ALTER TABLE users ADD COLUMN avatar_url TEXT')
    except Exception:
        pass
    
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
    
    # Создаем таблицу mastery
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mastery (
            user_id INTEGER PRIMARY KEY,
            solo INTEGER NOT NULL DEFAULT 0,
            hellmode INTEGER NOT NULL DEFAULT 0,
            raid INTEGER NOT NULL DEFAULT 0,
            speedrun INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(user_id)
        )
    ''')
    
    # Создаем индекс для mastery
    cursor.execute('''
        CREATE INDEX IF NOT EXISTS idx_mastery_user_id ON mastery(user_id)
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
        SELECT user_id, real_name, psn_id, platforms, modes, goals, difficulties, avatar_url
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
        'avatar_url': row[7]
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
        
        # Проверяем существует ли пользователь
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None

        # Получаем avatar_url только если оно явно передано
        avatar_url = profile_data.get('avatar_url')
        
        if exists:
            # UPDATE существующего пользователя
            if avatar_url is not None:
                # Обновляем с avatar_url
                cursor.execute('''
                    UPDATE users 
                    SET real_name = ?, psn_id = ?, platforms = ?, modes = ?, 
                        goals = ?, difficulties = ?, avatar_url = ?
                    WHERE user_id = ?
                ''', (
                    profile_data.get('real_name', ''),
                    profile_data.get('psn_id', ''),
                    platforms_str,
                    modes_str,
                    goals_str,
                    difficulties_str,
                    avatar_url,
                    user_id
                ))
            else:
                # Обновляем без avatar_url (сохраняем старое значение)
                cursor.execute('''
                    UPDATE users 
                    SET real_name = ?, psn_id = ?, platforms = ?, modes = ?, 
                        goals = ?, difficulties = ?
                    WHERE user_id = ?
                ''', (
                    profile_data.get('real_name', ''),
                    profile_data.get('psn_id', ''),
                    platforms_str,
                    modes_str,
                    goals_str,
                    difficulties_str,
                    user_id
                ))
        else:
            # INSERT нового пользователя
            cursor.execute('''
                INSERT INTO users 
                (user_id, real_name, psn_id, platforms, modes, goals, difficulties, avatar_url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                profile_data.get('real_name', ''),
                profile_data.get('psn_id', ''),
                platforms_str,
                modes_str,
                goals_str,
                difficulties_str,
                avatar_url
            ))
            
            # Автоматически создаём запись в mastery для нового пользователя
            cursor.execute('''
                INSERT INTO mastery (user_id, solo, hellmode, raid, speedrun)
                VALUES (?, 0, 0, 0, 0)
            ''', (user_id,))
        
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


def search_builds(db_path: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Ищет публичные билды по названию, описанию, тегам, классу, автору или ID.
    
    Args:
        db_path: Путь к файлу базы данных
        query: Поисковый запрос (текст или число для поиска по ID)
        limit: Максимальное количество результатов
    
    Returns:
        Список словарей с данными билдов (только публичные, is_public = 1)
    """
    try:
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, является ли запрос числом (поиск по ID)
        try:
            build_id = int(query.strip())
            # Если это число, ищем по ID
            cursor.execute('''
                SELECT build_id, user_id, author, name, class, tags, description, 
                       photo_1, photo_2, created_at, is_public
                FROM builds 
                WHERE build_id = ? AND is_public = 1
                LIMIT ?
            ''', (build_id, limit))
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
        except ValueError:
            # Если не число, ищем по текстовым полям
            # Получаем ВСЕ публичные билды и фильтруем на стороне Python
            # Это гарантирует корректную работу с кириллицей
            cursor.execute('''
                SELECT build_id, user_id, author, name, class, tags, description, 
                       photo_1, photo_2, created_at, is_public
                FROM builds 
                WHERE is_public = 1
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            conn.close()
            
            # Фильтруем результаты на стороне Python
            query_lower = query.lower().strip()
            builds_with_priority = []
            
            for row in rows:
                build = {
                    'build_id': row[0],
                    'user_id': row[1],
                    'author': row[2],
                    'name': row[3],
                    'class': row[4],
                    'tags': [t.strip() for t in row[5].split(',') if t.strip()] if row[5] else [],
                    'description': row[6] or '',
                    'photo_1': row[7],
                    'photo_2': row[8],
                    'created_at': row[9],
                    'is_public': row[10]
                }
                
                # Проверяем совпадения без учета регистра
                name_lower = build['name'].lower()
                class_lower = build['class'].lower()
                author_lower = build['author'].lower()
                description_lower = build['description'].lower()
                tags_lower = ', '.join([t.lower() for t in build['tags']])
                
                # Определяем приоритет совпадения
                priority = None
                if query_lower in name_lower:
                    priority = 1
                elif query_lower in class_lower:
                    priority = 2
                elif query_lower in tags_lower:
                    priority = 3
                elif query_lower in author_lower:
                    priority = 4
                elif query_lower in description_lower:
                    priority = 5
                
                # Если есть совпадение, добавляем в список
                if priority is not None:
                    build['_priority'] = priority
                    builds_with_priority.append(build)
            
            # Сортируем по приоритету и дате создания
            builds_with_priority.sort(key=lambda x: (x['_priority'], -x['created_at']))
            
            # Берем только нужное количество
            builds = [b for b in builds_with_priority[:limit]]
            
            # Удаляем временное поле _priority
            for build in builds:
                if '_priority' in build:
                    del build['_priority']
            
            return builds
        
    except Exception as e:
        print(f"Ошибка поиска билдов: {e}")
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


def update_build(db_path: str, build_id: int, user_id: int, build_data: Dict[str, Any]) -> bool:
    """
    Обновляет существующий билд.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
        user_id: ID пользователя (для проверки прав)
        build_data: Словарь с данными билда (name, class, tags, description, photo_1, photo_2)
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        if not os.path.exists(db_path):
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, что билд существует и принадлежит пользователю
        cursor.execute('SELECT build_id FROM builds WHERE build_id = ? AND user_id = ?', (build_id, user_id))
        if not cursor.fetchone():
            conn.close()
            return False
        
        # Подготавливаем данные для обновления
        tags_str = ','.join(build_data.get('tags', []))
        
        # Обновляем только переданные поля (если photo не переданы, они остаются старыми)
        update_fields = []
        update_values = []
        
        if 'name' in build_data:
            update_fields.append('name = ?')
            update_values.append(build_data['name'])
        
        if 'class' in build_data:
            update_fields.append('class = ?')
            update_values.append(build_data['class'])
        
        if 'tags' in build_data:
            update_fields.append('tags = ?')
            update_values.append(tags_str)
        
        if 'description' in build_data:
            update_fields.append('description = ?')
            update_values.append(build_data.get('description', ''))
        
        if 'photo_1' in build_data:
            update_fields.append('photo_1 = ?')
            update_values.append(build_data['photo_1'])
        
        if 'photo_2' in build_data:
            update_fields.append('photo_2 = ?')
            update_values.append(build_data['photo_2'])
        
        if not update_fields:
            conn.close()
            return False
        
        # Добавляем build_id и user_id в конец для WHERE
        update_values.extend([build_id, user_id])
        
        sql = f'''
            UPDATE builds 
            SET {', '.join(update_fields)}
            WHERE build_id = ? AND user_id = ?
        '''
        
        cursor.execute(sql, update_values)
        success = cursor.rowcount > 0
        conn.commit()
        conn.close()
        
        return success
        
    except Exception as e:
        print(f"Ошибка обновления билда: {e}")
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


# Удалены функции работы с трофеями и поле users.trophies


def get_all_users(db_path: str) -> List[Dict[str, Any]]:
    """
    Получает список всех пользователей из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Список словарей с данными пользователей (user_id, psn_id, avatar_url и mastery уровни)
    """
    try:
        if not os.path.exists(db_path):
            return []
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT u.user_id, u.psn_id, u.avatar_url,
                   COALESCE(m.solo, 0) as solo,
                   COALESCE(m.hellmode, 0) as hellmode,
                   COALESCE(m.raid, 0) as raid,
                   COALESCE(m.speedrun, 0) as speedrun
            FROM users u
            LEFT JOIN mastery m ON u.user_id = m.user_id
            WHERE u.psn_id IS NOT NULL AND u.psn_id != ''
            ORDER BY u.psn_id COLLATE NOCASE
        ''')
        
        rows = cursor.fetchall()
        conn.close()
        
        users = []
        for row in rows:
            users.append({
                'user_id': row[0],
                'psn_id': row[1],
                'avatar_url': row[2],
                'mastery': {
                    'solo': row[3],
                    'hellmode': row[4],
                    'raid': row[5],
                    'speedrun': row[6]
                }
            })
        
        return users
        
    except Exception as e:
        print(f"Ошибка получения списка пользователей: {e}")
        return []


def get_mastery(db_path: str, user_id: int) -> Dict[str, int]:
    """
    Получает уровни мастерства пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Словарь с уровнями: {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0}
        Если записи нет, возвращает все нули
    """
    try:
        if not os.path.exists(db_path):
            return {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0}
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT solo, hellmode, raid, speedrun
            FROM mastery WHERE user_id = ?
        ''', (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0}
        
        return {
            "solo": row[0],
            "hellmode": row[1],
            "raid": row[2],
            "speedrun": row[3]
        }
        
    except Exception as e:
        print(f"Ошибка получения уровней мастерства: {e}")
        return {"solo": 0, "hellmode": 0, "raid": 0, "speedrun": 0}


def set_mastery(db_path: str, user_id: int, category: str, level: int) -> bool:
    """
    Устанавливает уровень мастерства для категории пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        category: Категория (solo, hellmode, raid, speedrun)
        level: Уровень (0-5)
    
    Returns:
        True при успешном сохранении, иначе False
    """
    try:
        if not os.path.exists(db_path):
            init_db(db_path)
        
        if category not in ["solo", "hellmode", "raid", "speedrun"]:
            return False
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем существование записи
        cursor.execute('SELECT user_id FROM mastery WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None
        
        if exists:
            # Обновляем существующую запись
            cursor.execute(f'''
                UPDATE mastery 
                SET {category} = ?
                WHERE user_id = ?
            ''', (level, user_id))
        else:
            # Создаём новую запись
            cursor.execute('''
                INSERT INTO mastery (user_id, solo, hellmode, raid, speedrun)
                VALUES (?, 0, 0, 0, 0)
            ''', (user_id,))
            # Обновляем нужное поле
            cursor.execute(f'''
                UPDATE mastery 
                SET {category} = ?
                WHERE user_id = ?
            ''', (level, user_id))
        
        conn.commit()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"Ошибка сохранения уровня мастерства: {e}")
        return False
        