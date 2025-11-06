# db.py
# Модуль для работы с SQLite базой данных

import sqlite3
import json
import time
import os
import shutil
import traceback
from contextlib import contextmanager
from typing import Dict, Optional, Any, List

# Константы
MASTERY_CATEGORIES = ["solo", "hellmode", "raid", "speedrun"]
BUILD_UPDATE_FIELDS = {"name", "class", "tags", "description", "photo_1", "photo_2"}


# Вспомогательные функции
@contextmanager
def db_connection(db_path: str, init_if_missing: bool = False):
    """
    Context manager для работы с подключением к БД.
    
    Args:
        db_path: Путь к файлу базы данных
        init_if_missing: Инициализировать БД если её нет
    
    Yields:
        cursor: Курсор для выполнения запросов
    """
    if not os.path.exists(db_path):
        if init_if_missing:
            init_db(db_path)
        else:
            yield None
            return
    
    conn = None
    cursor = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        print(f"Ошибка БД: {e}")
        traceback.print_exc()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


def parse_comma_separated_list(text: Optional[str]) -> List[str]:
    """
    Парсит строку с элементами через запятую в список.
    
    Args:
        text: Строка с элементами через запятую или None
    
    Returns:
        Список строк с удаленными пробелами
    """
    if not text:
        return []
    return [item.strip() for item in text.split(',') if item.strip()]


def join_comma_separated_list(items: List[str]) -> str:
    """
    Объединяет список строк в строку через запятую.
    
    Args:
        items: Список строк
    
    Returns:
        Строка с элементами через запятую
    """
    return ','.join(items)


def _build_dict_from_row(row: tuple, include_stats: bool = False) -> Dict[str, Any]:
    """
    Формирует словарь билда из результата SQL запроса.
    
    Args:
        row: Кортеж с данными из БД
        include_stats: Включать ли статистику (comments_count, likes_count, dislikes_count)
    
    Returns:
        Словарь с данными билда
    """
    build = {
        'build_id': row[0],
        'user_id': row[1],
        'author': row[2],
        'name': row[3],
        'class': row[4],
        'tags': parse_comma_separated_list(row[5]),
        'description': row[6],
        'photo_1': row[7],
        'photo_2': row[8],
        'created_at': row[9],
        'is_public': row[10]
    }
    
    if include_stats:
        build['comments_count'] = row[11] or 0
        build['likes_count'] = row[12] or 0
        build['dislikes_count'] = row[13] or 0
    
    return build


def _get_reaction_stats(cursor: sqlite3.Cursor, build_id: int) -> tuple:
    """
    Получает статистику реакций для билда.
    
    Args:
        cursor: Курсор БД
        build_id: ID билда
    
    Returns:
        Кортеж (likes_count, dislikes_count)
    """
    cursor.execute('''
        SELECT 
            SUM(CASE WHEN reaction_type = 'like' THEN 1 ELSE 0 END) as likes_count,
            SUM(CASE WHEN reaction_type = 'dislike' THEN 1 ELSE 0 END) as dislikes_count
        FROM build_reactions
        WHERE build_id = ?
    ''', (build_id,))
    
    stats = cursor.fetchone()
    return (stats[0] or 0, stats[1] or 0)


def init_db(db_path: str) -> None:
    """
    Инициализирует базу данных и создает необходимые таблицы.
    Использует CREATE TABLE IF NOT EXISTS, поэтому безопасна для существующих БД.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
    """
    # Создаем директорию если её нет
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    try:
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
                avatar_url TEXT
            )
        ''')
        
        # Добавляем avatar_url если его нет (для старых БД)
        try:
            cursor.execute("PRAGMA table_info(users)")
            columns_info = cursor.fetchall()
            column_names = [c[1] for c in columns_info]
            if 'avatar_url' not in column_names:
                cursor.execute('ALTER TABLE users ADD COLUMN avatar_url TEXT')
        except sqlite3.Error:
            pass
        
        # Создаем индексы для users
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_users_user_id ON users(user_id)
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
        
        # Создаем таблицу comments
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                build_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                comment_text TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )
        ''')
        
        # Создаем индексы для comments
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_comments_build_id ON comments(build_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_comments_user_id ON comments(user_id)
        ''')
        
        # Создаем таблицу build_reactions для лайков/дизлайков
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS build_reactions (
                reaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                build_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reaction_type TEXT NOT NULL CHECK(reaction_type IN ('like', 'dislike')),
                created_at INTEGER NOT NULL,
                FOREIGN KEY(build_id) REFERENCES builds(build_id),
                UNIQUE(build_id, user_id)
            )
        ''')
        
        # Создаем индексы для build_reactions
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_reactions_build_id ON build_reactions(build_id)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_reactions_user_id ON build_reactions(user_id)
        ''')
        
        conn.commit()
        conn.close()
        
    except sqlite3.Error as e:
        print(f"Ошибка инициализации БД: {e}")
        traceback.print_exc()
        raise


def get_user(db_path: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает профиль пользователя по user_id.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
    
    Returns:
        Словарь с данными профиля или None если пользователь не найден
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT user_id, real_name, psn_id, platforms, modes, goals, difficulties, avatar_url
                FROM users WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Преобразуем в словарь
            profile = {
                'user_id': row[0],
                'real_name': row[1],
                'psn_id': row[2],
                'platforms': parse_comma_separated_list(row[3]),
                'modes': parse_comma_separated_list(row[4]),
                'goals': parse_comma_separated_list(row[5]),
                'difficulties': parse_comma_separated_list(row[6]),
                'avatar_url': row[7]
            }
            
            return profile
    except sqlite3.Error as e:
        print(f"Ошибка получения пользователя: {e}")
        return None


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
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Преобразуем списки в строки через запятую
            platforms_str = join_comma_separated_list(profile_data.get('platforms', []))
            modes_str = join_comma_separated_list(profile_data.get('modes', []))
            goals_str = join_comma_separated_list(profile_data.get('goals', []))
            difficulties_str = join_comma_separated_list(profile_data.get('difficulties', []))
            
            # Проверяем существует ли пользователь
            cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
            user_exists = cursor.fetchone() is not None
            
            # Проверяем существует ли запись в mastery
            cursor.execute('SELECT user_id FROM mastery WHERE user_id = ?', (user_id,))
            mastery_exists = cursor.fetchone() is not None

            # Получаем avatar_url только если оно явно передано
            avatar_url = profile_data.get('avatar_url')
            
            if user_exists:
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
                
                # Убеждаемся что запись в mastery существует (создаём если её нет)
                if not mastery_exists:
                    cursor.execute('''
                        INSERT INTO mastery (user_id, solo, hellmode, raid, speedrun)
                        VALUES (?, 0, 0, 0, 0)
                    ''', (user_id,))
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
                
                # Автоматически создаём запись в mastery для нового пользователя (только если её нет)
                if not mastery_exists:
                    cursor.execute('''
                        INSERT INTO mastery (user_id, solo, hellmode, raid, speedrun)
                        VALUES (?, 0, 0, 0, 0)
                    ''', (user_id,))
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка сохранения пользователя: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка удаления пользователя: {e}")
        traceback.print_exc()
        return False


def delete_user_all_data(db_path: str, user_id: int) -> bool:
    """
    Удаляет все данные пользователя из всех таблиц базы данных и файлы на сервере.
    
    Порядок удаления:
    1. Получает список build_id всех билдов пользователя
    2. Удаляет все comments под билдами пользователя (комментарии всех участников)
    3. Удаляет все build_reactions под билдами пользователя (реакции всех участников)
    4. Удаляет build_reactions пользователя (реакции самого пользователя)
    5. Удаляет comments пользователя (комментарии самого пользователя)
    6. Удаляет builds (билды пользователя)
    7. Удаляет папки билдов на сервере
    8. Удаляет mastery (уровни мастерства)
    9. Удаляет users (профиль пользователя)
    10. Удаляет папку пользователя на сервере
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
    
    Returns:
        True при успешном удалении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # 1. Получаем список build_id всех билдов пользователя
            cursor.execute('SELECT build_id FROM builds WHERE user_id = ?', (user_id,))
            build_ids = [row[0] for row in cursor.fetchall()]
            
            # 2. Удаляем все comments под билдами пользователя (комментарии всех участников)
            if build_ids:
                # Используем IN для удаления всех комментариев под билдами пользователя
                placeholders = ','.join('?' * len(build_ids))
                cursor.execute(f'DELETE FROM comments WHERE build_id IN ({placeholders})', build_ids)
            
            # 3. Удаляем все build_reactions под билдами пользователя (реакции всех участников)
            if build_ids:
                # Используем IN для удаления всех реакций под билдами пользователя
                placeholders = ','.join('?' * len(build_ids))
                cursor.execute(f'DELETE FROM build_reactions WHERE build_id IN ({placeholders})', build_ids)
            
            # 4. Удаляем build_reactions пользователя (реакции самого пользователя)
            cursor.execute('DELETE FROM build_reactions WHERE user_id = ?', (user_id,))
            
            # 5. Удаляем comments пользователя (комментарии самого пользователя)
            cursor.execute('DELETE FROM comments WHERE user_id = ?', (user_id,))
            
            # 6. Удаляем builds (билды пользователя)
            cursor.execute('DELETE FROM builds WHERE user_id = ?', (user_id,))
            
            # 7. Удаляем папки билдов на сервере
            base_dir = os.path.dirname(db_path)
            for build_id in build_ids:
                build_dir = os.path.join(base_dir, 'builds', str(build_id))
                if os.path.exists(build_dir):
                    try:
                        shutil.rmtree(build_dir)
                    except OSError as e:
                        print(f"Ошибка удаления папки билда {build_id}: {e}")
            
            # 8. Удаляем mastery (уровни мастерства)
            cursor.execute('DELETE FROM mastery WHERE user_id = ?', (user_id,))
            
            # 9. Удаляем users (профиль пользователя)
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            
            # 10. Удаляем папку пользователя на сервере
            base_dir = os.path.dirname(db_path)
            user_dir = os.path.join(base_dir, 'users', str(user_id))
            if os.path.exists(user_dir):
                try:
                    shutil.rmtree(user_dir)
                except OSError as e:
                    print(f"Ошибка удаления папки пользователя {user_id}: {e}")
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка удаления всех данных пользователя: {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"Ошибка при удалении файлов пользователя {user_id}: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return 0
            
            cursor.execute('SELECT COUNT(*) FROM users')
            count = cursor.fetchone()[0]
            return count
        
    except sqlite3.Error:
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
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return None
            
            current_time = int(time.time())
            tags_str = join_comma_separated_list(build_data.get('tags', []))
            
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
            
            return cursor.lastrowid
        
    except sqlite3.Error as e:
        print(f"Ошибка создания билда: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT build_id, user_id, author, name, class, tags, description, 
                       photo_1, photo_2, created_at, is_public
                FROM builds WHERE build_id = ?
            ''', (build_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            return _build_dict_from_row(row, include_stats=False)
        
    except sqlite3.Error as e:
        print(f"Ошибка получения билда: {e}")
        traceback.print_exc()
        return None


def get_user_builds(db_path: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Получает все билды пользователя со статистикой комментариев и реакций.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Список словарей с данными билдов (включая comments_count, likes_count, dislikes_count)
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            # Получаем билды с LEFT JOIN для статистики комментариев и реакций
            cursor.execute('''
                SELECT 
                    b.build_id, b.user_id, b.author, b.name, b.class, b.tags, b.description, 
                    b.photo_1, b.photo_2, b.created_at, b.is_public,
                    COUNT(DISTINCT c.comment_id) as comments_count,
                    SUM(CASE WHEN r.reaction_type = 'like' THEN 1 ELSE 0 END) as likes_count,
                    SUM(CASE WHEN r.reaction_type = 'dislike' THEN 1 ELSE 0 END) as dislikes_count
                FROM builds b
                LEFT JOIN comments c ON b.build_id = c.build_id
                LEFT JOIN build_reactions r ON b.build_id = r.build_id
                WHERE b.user_id = ?
                GROUP BY b.build_id, b.user_id, b.author, b.name, b.class, b.tags, b.description, 
                         b.photo_1, b.photo_2, b.created_at, b.is_public
                ORDER BY b.created_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            
            builds = []
            for row in rows:
                builds.append(_build_dict_from_row(row, include_stats=True))
            
            return builds
        
    except sqlite3.Error as e:
        print(f"Ошибка получения билдов пользователя: {e}")
        traceback.print_exc()
        return []


def get_public_builds(db_path: str) -> List[Dict[str, Any]]:
    """
    Получает все публичные билды со статистикой комментариев и реакций.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Список словарей с данными публичных билдов (включая comments_count, likes_count, dislikes_count)
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            # Получаем билды с LEFT JOIN для статистики комментариев и реакций
            cursor.execute('''
                SELECT 
                    b.build_id, b.user_id, b.author, b.name, b.class, b.tags, b.description, 
                    b.photo_1, b.photo_2, b.created_at, b.is_public,
                    COUNT(DISTINCT c.comment_id) as comments_count,
                    SUM(CASE WHEN r.reaction_type = 'like' THEN 1 ELSE 0 END) as likes_count,
                    SUM(CASE WHEN r.reaction_type = 'dislike' THEN 1 ELSE 0 END) as dislikes_count
                FROM builds b
                LEFT JOIN comments c ON b.build_id = c.build_id
                LEFT JOIN build_reactions r ON b.build_id = r.build_id
                WHERE b.is_public = 1
                GROUP BY b.build_id, b.user_id, b.author, b.name, b.class, b.tags, b.description, 
                         b.photo_1, b.photo_2, b.created_at, b.is_public
                ORDER BY b.created_at DESC
            ''')
            
            rows = cursor.fetchall()
            
            builds = []
            for row in rows:
                builds.append(_build_dict_from_row(row, include_stats=True))
            
            return builds
        
    except sqlite3.Error as e:
        print(f"Ошибка получения публичных билдов: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
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
                builds = []
                for row in rows:
                    builds.append(_build_dict_from_row(row, include_stats=False))
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
                
                # Фильтруем результаты на стороне Python
                query_lower = query.lower().strip()
                builds_with_priority = []
                
                for row in rows:
                    build = _build_dict_from_row(row, include_stats=False)
                    build['description'] = build.get('description') or ''
                    
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
        
    except sqlite3.Error as e:
        print(f"Ошибка поиска билдов: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('''
                UPDATE builds 
                SET is_public = ?
                WHERE build_id = ? AND user_id = ?
            ''', (is_public, build_id, user_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления видимости билда: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Проверяем, что билд существует и принадлежит пользователю
            cursor.execute('SELECT build_id FROM builds WHERE build_id = ? AND user_id = ?', (build_id, user_id))
            if not cursor.fetchone():
                return False
            
            # Подготавливаем данные для обновления
            # Используем whitelist для безопасности
            update_fields = []
            update_values = []
            
            # Маппинг полей для безопасного обновления
            field_mapping = {
                'name': 'name',
                'class': 'class',
                'tags': 'tags',
                'description': 'description',
                'photo_1': 'photo_1',
                'photo_2': 'photo_2'
            }
            
            for key, db_field in field_mapping.items():
                if key in build_data and key in BUILD_UPDATE_FIELDS:
                    if key == 'tags':
                        # Для тегов преобразуем список в строку
                        tags_str = join_comma_separated_list(build_data.get('tags', []))
                        update_fields.append(f'{db_field} = ?')
                        update_values.append(tags_str)
                    else:
                        update_fields.append(f'{db_field} = ?')
                        update_values.append(build_data.get(key, ''))
            
            if not update_fields:
                return False
            
            # Добавляем build_id и user_id в конец для WHERE
            update_values.extend([build_id, user_id])
            
            # Безопасное построение SQL с использованием whitelist
            sql = f'''
                UPDATE builds 
                SET {', '.join(update_fields)}
                WHERE build_id = ? AND user_id = ?
            '''
            
            cursor.execute(sql, update_values)
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления билда: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('''
                DELETE FROM builds 
                WHERE build_id = ? AND user_id = ?
            ''', (build_id, user_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка удаления билда: {e}")
        traceback.print_exc()
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
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
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
        
    except sqlite3.Error as e:
        print(f"Ошибка получения списка пользователей: {e}")
        traceback.print_exc()
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
    default_mastery = {cat: 0 for cat in MASTERY_CATEGORIES}
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return default_mastery
            
            cursor.execute('''
                SELECT solo, hellmode, raid, speedrun
                FROM mastery WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return default_mastery
            
            return {
                "solo": row[0],
                "hellmode": row[1],
                "raid": row[2],
                "speedrun": row[3]
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка получения уровней мастерства: {e}")
        traceback.print_exc()
        return default_mastery


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
        if category not in MASTERY_CATEGORIES:
            return False
        
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Проверяем существование записи
            cursor.execute('SELECT user_id FROM mastery WHERE user_id = ?', (user_id,))
            exists = cursor.fetchone() is not None
            
            # Используем безопасный маппинг категорий
            category_mapping = {
                'solo': 'solo',
                'hellmode': 'hellmode',
                'raid': 'raid',
                'speedrun': 'speedrun'
            }
            
            db_field = category_mapping.get(category)
            if not db_field:
                return False
            
            if exists:
                # Обновляем существующую запись
                # Используем безопасный подход - обновляем все поля, но только нужное меняем
                # Получаем текущие значения
                cursor.execute('SELECT solo, hellmode, raid, speedrun FROM mastery WHERE user_id = ?', (user_id,))
                current_row = cursor.fetchone()
                current_values = {
                    'solo': current_row[0],
                    'hellmode': current_row[1],
                    'raid': current_row[2],
                    'speedrun': current_row[3]
                }
                # Обновляем только нужное поле
                current_values[db_field] = level
                cursor.execute('''
                    UPDATE mastery 
                    SET solo = ?, hellmode = ?, raid = ?, speedrun = ?
                    WHERE user_id = ?
                ''', (
                    current_values['solo'],
                    current_values['hellmode'],
                    current_values['raid'],
                    current_values['speedrun'],
                    user_id
                ))
            else:
                # Создаём новую запись с нужным уровнем
                # Используем INSERT с явным указанием всех полей
                mastery_values = {cat: level if cat == category else 0 for cat in MASTERY_CATEGORIES}
                cursor.execute('''
                    INSERT INTO mastery (user_id, solo, hellmode, raid, speedrun)
                    VALUES (?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    mastery_values['solo'],
                    mastery_values['hellmode'],
                    mastery_values['raid'],
                    mastery_values['speedrun']
                ))
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка сохранения уровня мастерства: {e}")
        traceback.print_exc()
        return False


def create_comment(db_path: str, build_id: int, user_id: int, comment_text: str) -> Optional[int]:
    """
    Создает новый комментарий к билду.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда, к которому добавляется комментарий
        user_id: ID пользователя, который оставляет комментарий
        comment_text: Текст комментария (максимум 500 символов)
    
    Returns:
        comment_id созданного комментария или None при ошибке
    """
    try:
        # Валидация длины комментария
        if len(comment_text.strip()) == 0:
            return None
        if len(comment_text) > 500:
            comment_text = comment_text[:500]
        
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return None
            
            current_time = int(time.time())
            
            cursor.execute('''
                INSERT INTO comments 
                (build_id, user_id, comment_text, created_at)
                VALUES (?, ?, ?, ?)
            ''', (
                build_id,
                user_id,
                comment_text.strip(),
                current_time
            ))
            
            return cursor.lastrowid
        
    except sqlite3.Error as e:
        print(f"Ошибка создания комментария: {e}")
        traceback.print_exc()
        return None


def get_build_comments(db_path: str, build_id: int) -> List[Dict[str, Any]]:
    """
    Получает все комментарии для билда с информацией об авторах.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
    
    Returns:
        Список словарей с данными комментариев (comment_id, build_id, user_id, 
        real_name автора, comment_text, created_at), отсортированные по дате создания (старые сначала)
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            cursor.execute('''
                SELECT c.comment_id, c.build_id, c.user_id, u.psn_id, u.avatar_url,
                       c.comment_text, c.created_at
                FROM comments c
                LEFT JOIN users u ON c.user_id = u.user_id
                WHERE c.build_id = ?
                ORDER BY c.created_at ASC
            ''', (build_id,))
            
            rows = cursor.fetchall()
            
            comments = []
            for row in rows:
                comments.append({
                    'comment_id': row[0],
                    'build_id': row[1],
                    'user_id': row[2],
                    'author': row[3] or 'Неизвестный пользователь',
                    'avatar_url': row[4],
                    'comment_text': row[5],
                    'created_at': row[6]
                })
            
            return comments
        
    except sqlite3.Error as e:
        print(f"Ошибка получения комментариев: {e}")
        traceback.print_exc()
        return []


def toggle_reaction(db_path: str, build_id: int, user_id: int, reaction_type: str) -> Dict[str, Any]:
    """
    Переключает реакцию пользователя на билд.
    
    Логика:
    - Если реакции нет - создает новую
    - Если реакция того же типа - удаляет её
    - Если реакция противоположного типа - заменяет на новый тип
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
        user_id: ID пользователя
        reaction_type: Тип реакции ('like' или 'dislike')
    
    Returns:
        Словарь с обновленной статистикой: {
            'likes_count': int,
            'dislikes_count': int,
            'current_user_reaction': str | None  # 'like', 'dislike' или None
        }
    """
    try:
        if reaction_type not in ('like', 'dislike'):
            raise ValueError("reaction_type должен быть 'like' или 'dislike'")
        
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                raise sqlite3.Error("Не удалось подключиться к БД")
            
            # Проверяем существующую реакцию
            cursor.execute('''
                SELECT reaction_type FROM build_reactions
                WHERE build_id = ? AND user_id = ?
            ''', (build_id, user_id))
            
            existing = cursor.fetchone()
            current_time = int(time.time())
            
            if existing:
                existing_type = existing[0]
                if existing_type == reaction_type:
                    # Та же реакция - удаляем
                    cursor.execute('''
                        DELETE FROM build_reactions
                        WHERE build_id = ? AND user_id = ?
                    ''', (build_id, user_id))
                    final_reaction = None
                else:
                    # Противоположная реакция - заменяем
                    cursor.execute('''
                        UPDATE build_reactions
                        SET reaction_type = ?, created_at = ?
                        WHERE build_id = ? AND user_id = ?
                    ''', (reaction_type, current_time, build_id, user_id))
                    final_reaction = reaction_type
            else:
                # Нет реакции - создаем новую
                cursor.execute('''
                    INSERT INTO build_reactions (build_id, user_id, reaction_type, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (build_id, user_id, reaction_type, current_time))
                final_reaction = reaction_type
            
            # Получаем обновленную статистику
            likes_count, dislikes_count = _get_reaction_stats(cursor, build_id)
            
            return {
                'likes_count': likes_count,
                'dislikes_count': dislikes_count,
                'current_user_reaction': final_reaction
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка переключения реакции: {e}")
        traceback.print_exc()
        raise


def get_reactions(db_path: str, build_id: int, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Получает статистику реакций для билда и текущую реакцию пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
        user_id: ID пользователя (опционально, для получения его реакции)
    
    Returns:
        Словарь с данными: {
            'likes_count': int,
            'dislikes_count': int,
            'current_user_reaction': str | None  # 'like', 'dislike' или None
        }
    """
    default_result = {
        'likes_count': 0,
        'dislikes_count': 0,
        'current_user_reaction': None
    }
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return default_result
            
            # Получаем статистику
            likes_count, dislikes_count = _get_reaction_stats(cursor, build_id)
            
            # Получаем реакцию пользователя, если передан user_id
            current_user_reaction = None
            if user_id is not None:
                cursor.execute('''
                    SELECT reaction_type FROM build_reactions
                    WHERE build_id = ? AND user_id = ?
                ''', (build_id, user_id))
                
                user_reaction = cursor.fetchone()
                if user_reaction:
                    current_user_reaction = user_reaction[0]
            
            return {
                'likes_count': likes_count,
                'dislikes_count': dislikes_count,
                'current_user_reaction': current_user_reaction
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка получения реакций: {e}")
        traceback.print_exc()
        return default_result


def update_avatar_url(db_path: str, user_id: int, avatar_url: str) -> bool:
    """
    Обновляет avatar_url для пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        avatar_url: URL аватарки
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('''
                UPDATE users SET avatar_url = ? WHERE user_id = ?
            ''', (avatar_url, user_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления avatar_url: {e}")
        traceback.print_exc()
        return False


def update_build_photos(db_path: str, build_id: int, photo_1_url: str, photo_2_url: str) -> bool:
    """
    Обновляет пути к фотографиям билда.
    
    Args:
        db_path: Путь к файлу базы данных
        build_id: ID билда
        photo_1_url: URL первого фото
        photo_2_url: URL второго фото
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('''
                UPDATE builds SET photo_1 = ?, photo_2 = ? WHERE build_id = ?
            ''', (photo_1_url, photo_2_url, build_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления фото билда: {e}")
        traceback.print_exc()
        return False
        