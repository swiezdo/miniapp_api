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
from datetime import datetime, date

# Константы
MASTERY_CATEGORIES = ["solo", "hellmode", "raid", "speedrun", "glitch"]
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
    Инициализирует базу данных - создает директорию если её нет.
    База данных уже настроена, таблицы создавать не нужно.
    
    Args:
        db_path: Путь к файлу базы данных SQLite
    """
    # Создаем директорию если её нет
    os.makedirs(os.path.dirname(db_path), exist_ok=True)


def get_birthday(db_path: str, user_id: int) -> Optional[str]:
    """
    Получает день рождения пользователя по user_id.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
    
    Returns:
        Строка с днем рождения в формате "DD.MM.YYYY" или "DD.MM", или None
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT birthday FROM birthdays WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row or row[0] is None:
                return None
            
            return row[0]
    except sqlite3.Error as e:
        print(f"Ошибка получения дня рождения: {e}")
        return None


def get_upcoming_birthdays(db_path: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Получает список пользователей с ближайшими днями рождения.
    
    Args:
        db_path: Путь к файлу базы данных
        limit: Максимальное количество результатов
    
    Returns:
        Список словарей с данными пользователей:
        {
            'user_id': int,
            'psn_id': str,
            'avatar_url': str,
            'birthday': str,  # Формат "DD.MM.YYYY" или "DD.MM"
            'next_birthday_date': date  # Дата следующего дня рождения
        }
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            # Получаем всех пользователей с заполненным birthday
            cursor.execute('''
                SELECT b.user_id, b.psn_id, b.birthday, u.avatar_url
                FROM birthdays b
                LEFT JOIN users u ON b.user_id = u.user_id
                WHERE b.birthday IS NOT NULL AND b.birthday != ''
                ORDER BY b.user_id
            ''')
            
            rows = cursor.fetchall()
            
            if not rows:
                return []
            
            today = date.today()
            upcoming = []
            
            for row in rows:
                user_id, psn_id, birthday_str, avatar_url = row
                
                if not birthday_str:
                    continue
                
                # Парсим дату рождения
                parts = birthday_str.split('.')
                if len(parts) < 2:
                    continue
                
                try:
                    day = int(parts[0])
                    month = int(parts[1])
                    
                    # Вычисляем следующую дату дня рождения
                    # Пробуем текущий год
                    try:
                        next_birthday = date(today.year, month, day)
                        # Если день рождения уже прошел в этом году, берем следующий год
                        if next_birthday < today:
                            next_birthday = date(today.year + 1, month, day)
                    except ValueError:
                        # Если дата невалидна (например, 29 февраля), пропускаем
                        continue
                    
                    upcoming.append({
                        'user_id': user_id,
                        'psn_id': psn_id or '',
                        'avatar_url': avatar_url,
                        'birthday': birthday_str,
                        'next_birthday_date': next_birthday
                    })
                except (ValueError, IndexError):
                    continue
            
            # Сортируем по дате следующего дня рождения
            upcoming.sort(key=lambda x: x['next_birthday_date'])
            
            # Возвращаем первые limit записей
            return upcoming[:limit]
            
    except sqlite3.Error as e:
        print(f"Ошибка получения ближайших дней рождения: {e}")
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"Ошибка обработки дней рождения: {e}")
        traceback.print_exc()
        return []


def get_today_birthdays(db_path: str) -> List[Dict[str, Any]]:
    """
    Получает список именинников на сегодня.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Список словарей с данными именинников:
        {
            'user_id': int,
            'psn_id': str,
            'real_name': str
        }
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            today = date.today()
            today_day = today.day
            today_month = today.month
            
            # Получаем всех пользователей с заполненным birthday
            cursor.execute('''
                SELECT b.user_id, b.psn_id, b.birthday, u.real_name
                FROM birthdays b
                LEFT JOIN users u ON b.user_id = u.user_id
                WHERE b.birthday IS NOT NULL AND b.birthday != ''
            ''')
            
            rows = cursor.fetchall()
            
            if not rows:
                return []
            
            today_birthdays = []
            
            for row in rows:
                user_id, psn_id, birthday_str, real_name = row
                
                if not birthday_str:
                    continue
                
                # Парсим дату рождения (формат DD.MM или DD.MM.YYYY)
                parts = birthday_str.split('.')
                if len(parts) < 2:
                    continue
                
                try:
                    day = int(parts[0])
                    month = int(parts[1])
                    
                    # Проверяем, совпадает ли с сегодняшней датой
                    if day == today_day and month == today_month:
                        today_birthdays.append({
                            'user_id': user_id,
                            'psn_id': psn_id or '',
                            'real_name': real_name or ''
                        })
                except (ValueError, IndexError):
                    continue
            
            return today_birthdays
            
    except sqlite3.Error as e:
        print(f"Ошибка получения сегодняшних именинников: {e}")
        traceback.print_exc()
        return []
    except Exception as e:
        print(f"Ошибка обработки сегодняшних дней рождения: {e}")
        traceback.print_exc()
        return []


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
                SELECT user_id, real_name, psn_id, platforms, modes, goals, difficulties, avatar_url, balance
                FROM users WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return None
            
            # Получаем день рождения из таблицы birthdays
            birthday = get_birthday(db_path, user_id)
            
            # Преобразуем в словарь
            profile = {
                'user_id': row[0],
                'real_name': row[1],
                'psn_id': row[2],
                'platforms': parse_comma_separated_list(row[3]),
                'modes': parse_comma_separated_list(row[4]),
                'goals': parse_comma_separated_list(row[5]),
                'difficulties': parse_comma_separated_list(row[6]),
                'avatar_url': row[7],
                'birthday': birthday,
                'balance': row[8] if len(row) > 8 else 0
            }
            
            return profile
    except sqlite3.Error as e:
        print(f"Ошибка получения пользователя: {e}")
        return None


def update_user_balance(db_path: str, user_id: int, amount: int) -> bool:
    """
    Увеличивает баланс пользователя на указанную сумму.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя Telegram
        amount: Сумма для добавления к балансу
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('''
                UPDATE users SET balance = balance + ? WHERE user_id = ?
            ''', (amount, user_id))
            
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        print(f"Ошибка обновления баланса пользователя: {e}")
        traceback.print_exc()
        return False


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
            
            # Проверяем существует ли запись в trophies
            cursor.execute('SELECT user_id FROM trophies WHERE user_id = ?', (user_id,))
            trophies_exists = cursor.fetchone() is not None

            # Проверяем существует ли запись в birthdays
            cursor.execute('SELECT user_id FROM birthdays WHERE user_id = ?', (user_id,))
            birthdays_exists = cursor.fetchone() is not None

            # Проверяем существует ли запись в notifications
            cursor.execute('SELECT user_id FROM notifications WHERE user_id = ?', (user_id,))
            notifications_exists = cursor.fetchone() is not None

            # Получаем avatar_url только если оно явно передано
            avatar_url = profile_data.get('avatar_url')
            
            # Получаем birthday из profile_data
            birthday = profile_data.get('birthday')
            # Преобразуем пустую строку в None
            if birthday is not None and birthday.strip() == '':
                birthday = None
            
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
                
                # Получаем psn_id один раз для всех обновлений
                psn_id = profile_data.get('psn_id', '') or ''
                
                # Убеждаемся что запись в mastery существует (создаём если её нет)
                if not mastery_exists:
                    cursor.execute('''
                        INSERT INTO mastery (user_id, psn_id, solo, hellmode, raid, speedrun, glitch)
                        VALUES (?, ?, 0, 0, 0, 0, 0)
                    ''', (user_id, psn_id))
                else:
                    # Обновляем psn_id в mastery если запись существует
                    cursor.execute('''
                        UPDATE mastery SET psn_id = ? WHERE user_id = ?
                    ''', (psn_id, user_id))
                
                # Обновляем или создаем запись в trophies
                if trophies_exists:
                    # Обновляем psn_id в trophies если запись существует
                    cursor.execute('''
                        UPDATE trophies SET psn_id = ? WHERE user_id = ?
                    ''', (psn_id, user_id))
                else:
                    # Создаем новую запись в trophies
                    cursor.execute('''
                        INSERT INTO trophies (user_id, psn_id, trophies, active_trophies)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, psn_id, '', ''))
                
                # Обновляем или создаем запись в birthdays
                if birthdays_exists:
                    # Обновляем существующую запись
                    cursor.execute('''
                        UPDATE birthdays SET psn_id = ?, birthday = ? WHERE user_id = ?
                    ''', (psn_id, birthday, user_id))
                else:
                    # Создаем новую запись
                    cursor.execute('''
                        INSERT INTO birthdays (user_id, psn_id, birthday)
                        VALUES (?, ?, ?)
                    ''', (user_id, psn_id, birthday))
                
                # Обновляем psn_id в recent_events
                cursor.execute('''
                    UPDATE recent_events SET psn_id = ? WHERE user_id = ?
                ''', (psn_id, user_id))
                
                # Обновляем author в builds (author = psn_id)
                cursor.execute('''
                    UPDATE builds SET author = ? WHERE user_id = ?
                    ''', (psn_id, user_id))
                
                # Обновляем или создаем запись в notifications
                if notifications_exists:
                    # Обновляем psn_id в notifications если запись существует
                    cursor.execute('''
                        UPDATE notifications SET psn_id = ? WHERE user_id = ?
                    ''', (psn_id, user_id))
                else:
                    # Создаем новую запись в notifications со всеми полями = 1
                    cursor.execute('''
                        INSERT INTO notifications (user_id, psn_id, [check], speedrun, raid, ghost, hellmode, story, rivals, trials)
                        VALUES (?, ?, 1, 1, 1, 1, 1, 1, 1, 1)
                    ''', (user_id, psn_id))
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
                    psn_id = profile_data.get('psn_id', '') or ''
                    cursor.execute('''
                        INSERT INTO mastery (user_id, psn_id, solo, hellmode, raid, speedrun, glitch)
                        VALUES (?, ?, 0, 0, 0, 0, 0)
                    ''', (user_id, psn_id))
                
                # Автоматически создаём запись в trophies для нового пользователя (только если её нет)
                if not trophies_exists:
                    psn_id = profile_data.get('psn_id', '') or ''
                    cursor.execute('''
                        INSERT INTO trophies (user_id, psn_id, trophies, active_trophies)
                        VALUES (?, ?, ?, ?)
                    ''', (user_id, psn_id, '', ''))
                
                # Автоматически создаём запись в birthdays для нового пользователя (только если её нет)
                if not birthdays_exists:
                    psn_id = profile_data.get('psn_id', '') or ''
                    cursor.execute('''
                        INSERT INTO birthdays (user_id, psn_id, birthday)
                        VALUES (?, ?, ?)
                    ''', (user_id, psn_id, birthday))
                
                # Автоматически создаём запись в notifications для нового пользователя со всеми полями = 1
                if not notifications_exists:
                    psn_id = profile_data.get('psn_id', '') or ''
                    cursor.execute('''
                        INSERT INTO notifications (user_id, psn_id, [check], speedrun, raid, ghost, hellmode, story, rivals, trials)
                        VALUES (?, ?, 1, 1, 1, 1, 1, 1, 1, 1)
                    ''', (user_id, psn_id))
            
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
    Публичные билды (is_public = 1) сохраняются вместе с комментариями и реакциями.
    
    Порядок удаления:
    1. Разделяет билды пользователя на публичные и приватные
    2. Удаляет все comments под приватными билдами пользователя (комментарии всех участников)
    3. Удаляет все build_reactions под приватными билдами пользователя (реакции всех участников)
    4. Удаляет build_reactions пользователя (реакции самого пользователя на чужие билды)
    5. Удаляет comments пользователя (комментарии самого пользователя под чужими билдами)
    6. Удаляет только приватные builds (билды пользователя)
    7. Удаляет папки только приватных билдов на сервере
    8. Удаляет mastery (уровни мастерства)
    9. Удаляет trophies (трофеи пользователя)
    10. Удаляет birthdays (день рождения пользователя)
    11. Удаляет users (профиль пользователя)
    12. Удаляет папку пользователя на сервере
    
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
            
            # 1. Разделяем билды пользователя на публичные и приватные
            cursor.execute('SELECT build_id, is_public FROM builds WHERE user_id = ?', (user_id,))
            all_builds = cursor.fetchall()
            public_build_ids = [row[0] for row in all_builds if row[1] == 1]
            private_build_ids = [row[0] for row in all_builds if row[1] == 0]
            
            # 2. Удаляем все comments под приватными билдами пользователя (комментарии всех участников)
            if private_build_ids:
                placeholders = ','.join('?' * len(private_build_ids))
                cursor.execute(f'DELETE FROM comments WHERE build_id IN ({placeholders})', private_build_ids)
            
            # 3. Удаляем все build_reactions под приватными билдами пользователя (реакции всех участников)
            if private_build_ids:
                placeholders = ','.join('?' * len(private_build_ids))
                cursor.execute(f'DELETE FROM build_reactions WHERE build_id IN ({placeholders})', private_build_ids)
            
            # 4. Удаляем build_reactions пользователя (реакции самого пользователя на чужие билды)
            cursor.execute('DELETE FROM build_reactions WHERE user_id = ?', (user_id,))
            
            # 5. Удаляем comments пользователя (комментарии самого пользователя под чужими билдами)
            cursor.execute('DELETE FROM comments WHERE user_id = ?', (user_id,))
            
            # 6. Удаляем только приватные builds (билды пользователя)
            if private_build_ids:
                placeholders = ','.join('?' * len(private_build_ids))
                cursor.execute(f'DELETE FROM builds WHERE build_id IN ({placeholders})', private_build_ids)
            
            # 7. Удаляем папки только приватных билдов на сервере
            base_dir = os.path.dirname(db_path)
            for build_id in private_build_ids:
                build_dir = os.path.join(base_dir, 'builds', str(build_id))
                if os.path.exists(build_dir):
                    try:
                        shutil.rmtree(build_dir)
                    except OSError as e:
                        print(f"Ошибка удаления папки билда {build_id}: {e}")
            
            # 8. Удаляем mastery (уровни мастерства)
            cursor.execute('DELETE FROM mastery WHERE user_id = ?', (user_id,))
            
            # 9. Удаляем trophies (трофеи пользователя)
            cursor.execute('DELETE FROM trophies WHERE user_id = ?', (user_id,))
            
            # 10. Удаляем birthdays (день рождения пользователя)
            cursor.execute('DELETE FROM birthdays WHERE user_id = ?', (user_id,))
            
            # 11. Удаляем users (профиль пользователя)
            cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
            
            # 12. Удаляем папку пользователя на сервере
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
            
            # Получаем билды с подзапросами для статистики комментариев и реакций
            # Используем подзапросы вместо JOIN, чтобы избежать декартова произведения
            cursor.execute('''
                SELECT 
                    b.build_id, b.user_id, b.author, b.name, b.class, b.tags, b.description, 
                    b.photo_1, b.photo_2, b.created_at, b.is_public,
                    (SELECT COUNT(*) FROM comments c WHERE c.build_id = b.build_id) as comments_count,
                    (SELECT COUNT(*) FROM build_reactions r WHERE r.build_id = b.build_id AND r.reaction_type = 'like') as likes_count,
                    (SELECT COUNT(*) FROM build_reactions r WHERE r.build_id = b.build_id AND r.reaction_type = 'dislike') as dislikes_count
                FROM builds b
                WHERE b.user_id = ?
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
            
            # Получаем билды с подзапросами для статистики комментариев и реакций
            # Используем подзапросы вместо JOIN, чтобы избежать декартова произведения
            cursor.execute('''
                SELECT 
                    b.build_id, b.user_id, b.author, b.name, b.class, b.tags, b.description, 
                    b.photo_1, b.photo_2, b.created_at, b.is_public,
                    (SELECT COUNT(*) FROM comments c WHERE c.build_id = b.build_id) as comments_count,
                    (SELECT COUNT(*) FROM build_reactions r WHERE r.build_id = b.build_id AND r.reaction_type = 'like') as likes_count,
                    (SELECT COUNT(*) FROM build_reactions r WHERE r.build_id = b.build_id AND r.reaction_type = 'dislike') as dislikes_count
                FROM builds b
                WHERE b.is_public = 1
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
                       COALESCE(m.speedrun, 0) as speedrun,
                       COALESCE(m.glitch, 0) as glitch
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
                        'speedrun': row[6],
                        'glitch': row[7]
                    }
                })
            
            return users
        
    except sqlite3.Error as e:
        print(f"Ошибка получения списка пользователей: {e}")
        traceback.print_exc()
        return []


def get_user_public_builds_count(db_path: str, user_id: int) -> int:
    """
    Возвращает количество публичных билдов пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Количество публичных билдов (int)
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return 0
            
            cursor.execute('''
                SELECT COUNT(*) 
                FROM builds 
                WHERE user_id = ? AND is_public = 1
            ''', (user_id,))
            
            row = cursor.fetchone()
            return int(row[0] or 0)
    except sqlite3.Error as e:
        print(f"Ошибка подсчета публичных билдов пользователя: {e}")
        traceback.print_exc()
        return 0

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
                SELECT solo, hellmode, raid, speedrun, glitch
                FROM mastery WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return default_mastery
            
            return {
                "solo": row[0],
                "hellmode": row[1],
                "raid": row[2],
                "speedrun": row[3],
                "glitch": row[4]
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
        category: Категория (solo, hellmode, raid, speedrun, glitch)
        level: Уровень (0-11)
    
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
                'speedrun': 'speedrun',
                'glitch': 'glitch'
            }
            
            db_field = category_mapping.get(category)
            if not db_field:
                return False
            
            if exists:
                # Обновляем существующую запись
                # Используем безопасный подход - обновляем все поля, но только нужное меняем
                # Получаем текущие значения
                cursor.execute('SELECT solo, hellmode, raid, speedrun, glitch FROM mastery WHERE user_id = ?', (user_id,))
                current_row = cursor.fetchone()
                if not current_row:
                    current_row = (0, 0, 0, 0, 0)
                current_values = {
                    'solo': current_row[0],
                    'hellmode': current_row[1],
                    'raid': current_row[2],
                    'speedrun': current_row[3],
                    'glitch': current_row[4]
                }
                # Обновляем только нужное поле
                current_values[db_field] = level
                cursor.execute('''
                    UPDATE mastery 
                    SET solo = ?, hellmode = ?, raid = ?, speedrun = ?, glitch = ?
                    WHERE user_id = ?
                ''', (
                    current_values['solo'],
                    current_values['hellmode'],
                    current_values['raid'],
                    current_values['speedrun'],
                    current_values['glitch'],
                    user_id
                ))
            else:
                # Создаём новую запись с нужным уровнем
                # Получаем psn_id из таблицы users
                cursor.execute('SELECT psn_id FROM users WHERE user_id = ?', (user_id,))
                user_row = cursor.fetchone()
                psn_id = user_row[0] if user_row and user_row[0] else None
                
                # Используем INSERT с явным указанием всех полей
                mastery_values = {cat: level if cat == category else 0 for cat in MASTERY_CATEGORIES}
                cursor.execute('''
                    INSERT INTO mastery (user_id, psn_id, solo, hellmode, raid, speedrun, glitch)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    psn_id,
                    mastery_values['solo'],
                    mastery_values['hellmode'],
                    mastery_values['raid'],
                    mastery_values['speedrun'],
                    mastery_values['glitch']
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


def get_recent_comments(db_path: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Возвращает последние комментарии с информацией об авторах и билдах.
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []

            cursor.execute(
                '''
                SELECT c.comment_id, c.build_id, c.user_id, c.comment_text, c.created_at,
                       u.psn_id, u.avatar_url,
                       b.name as build_name, b.class as build_class
                FROM comments c
                LEFT JOIN users u ON c.user_id = u.user_id
                LEFT JOIN builds b ON c.build_id = b.build_id
                ORDER BY c.created_at DESC
                LIMIT ?
                ''',
                (limit,),
            )

            rows = cursor.fetchall() or []
            comments = []
            for row in rows:
                comments.append({
                    'comment_id': row[0],
                    'build_id': row[1],
                    'user_id': row[2],
                    'comment_text': row[3],
                    'created_at': row[4],
                    'psn_id': row[5] or 'Скрытый автор',
                    'avatar_url': row[6],
                    'build_name': row[7] or 'Без названия',
                    'build_class': row[8] or '',
                })
            return comments
    except sqlite3.Error as e:
        print(f"Ошибка получения последних комментариев: {e}")
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


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С ТРОФЕЯМИ ==========

def init_user_trophies(db_path: str, user_id: int, psn_id: str) -> bool:
    """
    Создает запись трофеев для нового пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        psn_id: PSN ID пользователя
    
    Returns:
        True при успешном создании, иначе False
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Проверяем существует ли запись
            cursor.execute('SELECT user_id FROM trophies WHERE user_id = ?', (user_id,))
            if cursor.fetchone() is not None:
                return True  # Запись уже существует
            
            # Создаем новую запись
            cursor.execute('''
                INSERT INTO trophies (user_id, psn_id, trophies, active_trophies)
                VALUES (?, ?, ?, ?)
            ''', (user_id, psn_id or '', '', ''))
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка создания записи трофеев: {e}")
        traceback.print_exc()
        return False


def get_trophies(db_path: str, user_id: int) -> Dict[str, Any]:
    """
    Получает все трофеи и активные трофеи пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Словарь с данными: {
            'trophies': List[str],  # Список всех трофеев
            'active_trophies': List[str]  # Список активных трофеев
        }
        Если записи нет, возвращает пустые списки
    """
    default_result = {
        'trophies': [],
        'active_trophies': []
    }
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return default_result
            
            cursor.execute('''
                SELECT trophies, active_trophies
                FROM trophies WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return default_result
            
            trophies_str = row[0] or ''
            active_trophies_str = row[1] or ''
            
            return {
                'trophies': parse_comma_separated_list(trophies_str),
                'active_trophies': parse_comma_separated_list(active_trophies_str)
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка получения трофеев: {e}")
        traceback.print_exc()
        return default_result


def add_trophy(db_path: str, user_id: int, trophy_key: str) -> bool:
    """
    Добавляет трофей в список пользователя (с проверкой на дубликаты и сортировкой по алфавиту).
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        trophy_key: Ключ трофея (например, 'solo', 'hellmode')
    
    Returns:
        True при успешном добавлении, иначе False
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Получаем текущие трофеи
            cursor.execute('SELECT trophies FROM trophies WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            
            if not row:
                # Если записи нет, создаем её
                user = get_user(db_path, user_id)
                psn_id = user.get('psn_id', '') if user else ''
                if not init_user_trophies(db_path, user_id, psn_id):
                    return False
                current_trophies = []
            else:
                trophies_str = row[0] or ''
                current_trophies = parse_comma_separated_list(trophies_str)
            
            # Проверяем на дубликаты
            if trophy_key in current_trophies:
                return True  # Трофей уже есть, считаем успешным
            
            # Добавляем трофей и сортируем по алфавиту
            current_trophies.append(trophy_key)
            current_trophies.sort()  # Алфавитная сортировка
            
            # Обновляем запись
            trophies_str = join_comma_separated_list(current_trophies)
            cursor.execute('''
                UPDATE trophies SET trophies = ? WHERE user_id = ?
            ''', (trophies_str, user_id))
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка добавления трофея: {e}")
        traceback.print_exc()
        return False


def update_active_trophies(db_path: str, user_id: int, active_trophies_list: List[str]) -> bool:
    """
    Обновляет список активных трофеев пользователя (максимум 8).
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        active_trophies_list: Список активных трофеев (максимум 8)
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        # Ограничиваем до 8 трофеев
        if len(active_trophies_list) > 8:
            active_trophies_list = active_trophies_list[:8]
        
        # Проверяем, что все активные трофеи есть в списке всех трофеев пользователя
        user_trophies = get_trophies(db_path, user_id)
        all_trophies = set(user_trophies.get('trophies', []))
        active_set = set(active_trophies_list)
        
        # Удаляем трофеи, которых нет в списке всех трофеев
        valid_active = [t for t in active_trophies_list if t in all_trophies]
        
        # Сортируем по алфавиту (сохраняя порядок в пределах алфавитной сортировки)
        valid_active.sort()
        
        # Ограничиваем до 8 после фильтрации
        if len(valid_active) > 8:
            valid_active = valid_active[:8]
        
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Проверяем существует ли запись
            cursor.execute('SELECT user_id FROM trophies WHERE user_id = ?', (user_id,))
            if cursor.fetchone() is None:
                # Если записи нет, создаем её
                user = get_user(db_path, user_id)
                psn_id = user.get('psn_id', '') if user else ''
                if not init_user_trophies(db_path, user_id, psn_id):
                    return False
            
            # Обновляем активные трофеи
            active_trophies_str = join_comma_separated_list(valid_active)
            cursor.execute('''
                UPDATE trophies SET active_trophies = ? WHERE user_id = ?
            ''', (active_trophies_str, user_id))
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления активных трофеев: {e}")
        traceback.print_exc()
        return False


# ========== ФУНКЦИИ ДЛЯ ЛЕНТЫ СОБЫТИЙ ==========

def log_recent_event(
    db_path: str,
    event_type: str,
    user_id: Optional[int],
    psn_id: Optional[str],
    avatar_url: Optional[str],
    payload: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Логирует событие (повышение мастерства, трофей и т.д.) для ленты наград.
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False

            created_at = int(time.time())
            payload_json = json.dumps(payload or {}, ensure_ascii=False)

            cursor.execute(
                '''
                INSERT INTO recent_events (event_type, user_id, psn_id, avatar_url, payload, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (
                    event_type,
                    user_id,
                    (psn_id or '').strip(),
                    (avatar_url or '').strip(),
                    payload_json,
                    created_at,
                ),
            )
            return True
    except sqlite3.Error as e:
        print(f"Ошибка логирования события: {e}")
        traceback.print_exc()
        return False


def get_recent_events(db_path: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Возвращает последние события для ленты наград.
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []

            cursor.execute(
                '''
                SELECT event_id, event_type, user_id, psn_id, avatar_url, payload, created_at
                FROM recent_events
                ORDER BY created_at DESC, event_id DESC
                LIMIT ?
                ''',
                (limit,),
            )

            rows = cursor.fetchall() or []
            events = []
            for row in rows:
                payload_data = {}
                try:
                    payload_data = json.loads(row[5]) if row[5] else {}
                except json.JSONDecodeError:
                    payload_data = {}

                events.append({
                    'event_id': row[0],
                    'event_type': row[1],
                    'user_id': row[2],
                    'psn_id': row[3],
                    'avatar_url': row[4],
                    'payload': payload_data,
                    'created_at': row[6],
                })
            return events
    except sqlite3.Error as e:
        print(f"Ошибка чтения событий: {e}")
        traceback.print_exc()
        return []


def get_current_rotation_week(db_path: str) -> Optional[int]:
    """
    Получает текущую неделю ротации из БД.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Номер недели (1-16) или None в случае ошибки
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('SELECT week FROM rotation_current_week WHERE id = 1')
            row = cursor.fetchone()
            
            if row:
                return row[0]
            else:
                # Если записи нет, создаем с начальным значением 14
                current_time = int(time.time())
                cursor.execute('''
                    INSERT INTO rotation_current_week (id, week, last_updated)
                    VALUES (1, 14, ?)
                ''', (current_time,))
                return 14
            
    except sqlite3.Error as e:
        print(f"Ошибка получения текущей недели: {e}")
        traceback.print_exc()
        return None


def get_rotation_week_info(db_path: str) -> Optional[Dict[str, Any]]:
    """
    Получает информацию о текущей неделе ротации (номер недели и время последнего обновления).
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Словарь с ключами 'week' и 'last_updated' или None в случае ошибки
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('SELECT week, last_updated FROM rotation_current_week WHERE id = 1')
            row = cursor.fetchone()
            
            if row:
                return {
                    'week': row[0],
                    'last_updated': row[1]
                }
            else:
                # Если записи нет, создаем с начальным значением 14
                current_time = int(time.time())
                cursor.execute('''
                    INSERT INTO rotation_current_week (id, week, last_updated)
                    VALUES (1, 14, ?)
                ''', (current_time,))
                return {
                    'week': 14,
                    'last_updated': current_time
                }
            
    except sqlite3.Error as e:
        print(f"Ошибка получения информации о неделе: {e}")
        traceback.print_exc()
        return None


def update_rotation_week(db_path: str) -> bool:
    """
    Обновляет неделю ротации (увеличивает на 1, после 16 → 1).
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Получаем текущую неделю
            cursor.execute('SELECT week FROM rotation_current_week WHERE id = 1')
            row = cursor.fetchone()
            
            if not row:
                # Если записи нет, создаем с начальным значением 14
                current_time = int(time.time())
                cursor.execute('''
                    INSERT INTO rotation_current_week (id, week, last_updated)
                    VALUES (1, 14, ?)
                ''', (current_time,))
                return True
            
            current_week = row[0]
            # Увеличиваем неделю на 1, после 16 → 1
            new_week = (current_week % 16) + 1
            current_time = int(time.time())
            
            cursor.execute('''
                UPDATE rotation_current_week 
                SET week = ?, last_updated = ?
                WHERE id = 1
            ''', (new_week, current_time))
            
            return True
            
    except sqlite3.Error as e:
        print(f"Ошибка обновления недели ротации: {e}")
        traceback.print_exc()
        return False


def get_current_hellmode_quest(db_path: str) -> Optional[Dict[str, Any]]:
    """
    Получает текущее задание HellMode из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Словарь с полями: map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward
        или None если задание не найдено или пустое
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward
                FROM hellmode_quest
                LIMIT 1
            ''')
            
            row = cursor.fetchone()
            if not row:
                return None
            
            map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward = row
            
            # Проверяем, что задание не пустое
            if not map_slug or not emote_slug or not class_slug or not gear_slug:
                return None
            
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
            
    except sqlite3.Error as e:
        print(f"Ошибка получения текущего задания HellMode: {e}")
        traceback.print_exc()
        return None


def update_hellmode_quest(
    db_path: str,
    map_slug: str,
    map_name: str,
    emote_slug: str,
    emote_name: str,
    class_slug: str,
    class_name: str,
    gear_slug: str,
    gear_name: str,
    reward: int
) -> bool:
    """
    Обновляет текущее задание HellMode в базе данных.
    
    Args:
        db_path: Путь к файлу базы данных
        map_slug: Slug карты
        map_name: Название карты
        emote_slug: Slug эмоции
        emote_name: Название эмоции
        class_slug: Slug класса
        class_name: Название класса
        gear_slug: Slug снаряжения
        gear_name: Название снаряжения
        reward: Награда за выполнение
    
    Returns:
        True если обновление успешно, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Обновляем запись (в таблице всегда только одна запись)
            cursor.execute('''
                UPDATE hellmode_quest
                SET map_slug = ?, map_name = ?, 
                    emote_slug = ?, emote_name = ?,
                    class_slug = ?, class_name = ?,
                    gear_slug = ?, gear_name = ?,
                    reward = ?
            ''', (map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward))
            
            # Если запись не была обновлена (не существует), создаем новую
            if cursor.rowcount == 0:
                cursor.execute('''
                    INSERT INTO hellmode_quest (
                        map_slug, map_name, 
                        emote_slug, emote_name,
                        class_slug, class_name,
                        gear_slug, gear_name,
                        reward
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (map_slug, map_name, emote_slug, emote_name, class_slug, class_name, gear_slug, gear_name, reward))
            
            return True
            
    except sqlite3.Error as e:
        print(f"Ошибка обновления задания HellMode: {e}")
        traceback.print_exc()
        return False


def get_top50_current_prize(db_path: str) -> Optional[int]:
    """
    Получает текущее значение приза Top50.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Текущее значение приза или None если не найдено
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('SELECT value FROM top50_current_prize LIMIT 1')
            row = cursor.fetchone()
            
            if row:
                return row[0]
            return None
            
    except sqlite3.Error as e:
        print(f"Ошибка получения приза Top50: {e}")
        traceback.print_exc()
        return None


def update_top50_current_prize(db_path: str, value: int) -> bool:
    """
    Обновляет значение приза Top50.
    
    Args:
        db_path: Путь к файлу базы данных
        value: Новое значение приза
    
    Returns:
        True если обновление успешно, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Обновляем значение (в таблице всегда только одна запись)
            cursor.execute('UPDATE top50_current_prize SET value = ?', (value,))
            
            # Если запись не была обновлена (не существует), создаем новую
            if cursor.rowcount == 0:
                cursor.execute('INSERT INTO top50_current_prize (value) VALUES (?)', (value,))
            
            return True
            
    except sqlite3.Error as e:
        print(f"Ошибка обновления приза Top50: {e}")
        traceback.print_exc()
        return False


def mark_quest_done(db_path: str, user_id: int, psn_id: str, quest_type: str) -> bool:
    """
    Отмечает задание как выполненное для пользователя.
    Увеличивает all_completed на 1, если все 4 задания выполнены.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        psn_id: PSN ID пользователя
        quest_type: Тип задания ('hellmode', 'story', 'survival', 'trials')
    
    Returns:
        True если обновление успешно, иначе False
    """
    valid_quest_types = {'hellmode', 'story', 'survival', 'trials'}
    if quest_type not in valid_quest_types:
        print(f"Ошибка: недопустимый тип задания: {quest_type}")
        return False
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Получаем текущее состояние
            cursor.execute('''
                SELECT hellmode, story, survival, trials, all_completed, first_completed_at
                FROM quests_done
                WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            
            if row:
                hellmode, story, survival, trials, all_completed, first_completed_at = row
            else:
                # Записи нет, создаем новую
                hellmode, story, survival, trials, all_completed, first_completed_at = 0, 0, 0, 0, 0, None
            
            # Вычисляем сумму заданий до обновления
            sum_before = hellmode + story + survival + trials
            
            # Обновляем соответствующее поле на 1
            if quest_type == 'hellmode':
                hellmode = 1
            elif quest_type == 'story':
                story = 1
            elif quest_type == 'survival':
                survival = 1
            elif quest_type == 'trials':
                trials = 1
            
            # Вычисляем сумму после обновления
            sum_after = hellmode + story + survival + trials
            
            # Если все 4 задания выполнены И до обновления не все были выполнены
            if sum_after == 4 and sum_before < 4:
                all_completed = all_completed + 1
                
                # Если это первое завершение всех заданий - записываем время
                if all_completed == 1:
                    first_completed_at = int(time.time())
                
                # Если достигли 5 недель подряд, выдаем трофей "Герой недели"
                if all_completed == 5:
                    add_trophy(db_path, user_id, 'week-hero')
            
            # Вставляем или обновляем запись
            cursor.execute('''
                INSERT OR REPLACE INTO quests_done 
                (user_id, psn_id, hellmode, story, survival, trials, all_completed, first_completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, psn_id, hellmode, story, survival, trials, all_completed, first_completed_at))
            
            return True
            
    except sqlite3.Error as e:
        print(f"Ошибка отметки задания как выполненного: {e}")
        traceback.print_exc()
        return False


def is_quest_done(db_path: str, user_id: int, quest_type: str) -> bool:
    """
    Проверяет, выполнено ли задание пользователем на текущей неделе.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        quest_type: Тип задания ('hellmode', 'story', 'survival', 'trials')
    
    Returns:
        True если задание выполнено, иначе False
    """
    valid_quest_types = {'hellmode', 'story', 'survival', 'trials'}
    if quest_type not in valid_quest_types:
        return False
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute(f'''
                SELECT {quest_type}
                FROM quests_done
                WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            
            if row:
                return row[0] == 1
            return False
            
    except sqlite3.Error as e:
        print(f"Ошибка проверки выполнения задания: {e}")
        traceback.print_exc()
        return False


def reset_weekly_quests(db_path: str) -> bool:
    """
    Сбрасывает задания для новой недели.
    
    Логика сброса:
    - Для пользователей с all_completed > 0:
      * Если все 4 задания выполнены: сбросить только задания (в 0), сохранить all_completed
      * Если не все задания выполнены: сбросить all_completed в 0 и удалить запись
    - Для пользователей с all_completed = 0: удалить запись
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        True если сброс успешен, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Получаем всех пользователей с их статусом
            cursor.execute('''
                SELECT user_id, hellmode, story, survival, trials, all_completed
                FROM quests_done
            ''')
            rows = cursor.fetchall()
            
            for row in rows:
                user_id, hellmode, story, survival, trials, all_completed = row
                
                # Считаем количество выполненных заданий
                completed_count = hellmode + story + survival + trials
                
                if all_completed > 0:
                    # Если все 4 задания выполнены - сбросить только задания, сохранить all_completed
                    if completed_count == 4:
                        cursor.execute('''
                            UPDATE quests_done
                            SET hellmode = 0, story = 0, survival = 0, trials = 0
                            WHERE user_id = ?
                        ''', (user_id,))
                    else:
                        # Если не все задания выполнены - сбросить прогресс и удалить запись
                        cursor.execute('''
                            DELETE FROM quests_done
                            WHERE user_id = ?
                        ''', (user_id,))
                else:
                    # Если all_completed = 0 - удалить запись
                    cursor.execute('''
                        DELETE FROM quests_done
                        WHERE user_id = ?
                    ''', (user_id,))
            
            return True
            
    except sqlite3.Error as e:
        print(f"Ошибка сброса заданий: {e}")
        traceback.print_exc()
        return False


def get_user_quests_status(db_path: str, user_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает статус всех заданий пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Словарь с статусом заданий или None если запись не найдена
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT hellmode, story, survival, trials, all_completed
                FROM quests_done
                WHERE user_id = ?
            ''', (user_id,))
            row = cursor.fetchone()
            
            if row:
                return {
                    'hellmode': bool(row[0]),
                    'story': bool(row[1]),
                    'survival': bool(row[2]),
                    'trials': bool(row[3]),
                    'all_completed': row[4]
                }
            return None
            
    except sqlite3.Error as e:
        print(f"Ошибка получения статуса заданий: {e}")
        traceback.print_exc()
        return None


def get_week_heroes(db_path: str, limit: int = 3) -> List[Dict[str, Any]]:
    """
    Получает список героев недели - пользователей с all_completed > 0.
    
    Args:
        db_path: Путь к файлу базы данных
        limit: Максимальное количество результатов
    
    Returns:
        Список словарей с данными пользователей:
        {
            'user_id': int,
            'psn_id': str,
            'avatar_url': str,
            'all_completed': int
        }
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            cursor.execute('''
                SELECT 
                    qd.user_id,
                    qd.all_completed,
                    u.psn_id,
                    u.avatar_url
                FROM quests_done qd
                LEFT JOIN users u ON qd.user_id = u.user_id
                WHERE qd.all_completed > 0
                ORDER BY qd.all_completed DESC, qd.first_completed_at ASC
                LIMIT ?
            ''', (limit,))
            
            rows = cursor.fetchall()
            
            if not rows:
                return []
            
            heroes = []
            for row in rows:
                user_id, all_completed, psn_id, avatar_url = row
                heroes.append({
                    'user_id': user_id,
                    'psn_id': psn_id or '',
                    'avatar_url': avatar_url or '',
                    'all_completed': all_completed
                })
            
            return heroes
            
    except sqlite3.Error as e:
        print(f"Ошибка получения героев недели: {e}")
        traceback.print_exc()
        return []


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ С УВЕДОМЛЕНИЯМИ ==========

def get_notification_subscribers(db_path: str, notification_type: str) -> List[int]:
    """
    Получает список user_id пользователей, подписанных на указанный тип уведомлений.
    
    Args:
        db_path: Путь к файлу базы данных
        notification_type: Тип уведомления (check, speedrun, raid, ghost, hellmode, story, rivals, trials)
    
    Returns:
        Список user_id пользователей, у которых соответствующее поле = 1
    """
    valid_types = {'check', 'speedrun', 'raid', 'ghost', 'hellmode', 'story', 'rivals', 'trials'}
    if notification_type not in valid_types:
        print(f"Ошибка: недопустимый тип уведомления: {notification_type}")
        return []
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            # Безопасный запрос с использованием whitelist
            # Используем квадратные скобки для поля check, так как это зарезервированное слово
            field_name = f'[{notification_type}]' if notification_type == 'check' else notification_type
            cursor.execute(f'''
                SELECT user_id FROM notifications
                WHERE {field_name} = 1
            ''', ())
            
            rows = cursor.fetchall()
            return [row[0] for row in rows]
            
    except sqlite3.Error as e:
        print(f"Ошибка получения подписчиков на уведомления: {e}")
        traceback.print_exc()
        return []


def init_user_notifications(db_path: str, user_id: int, psn_id: str) -> bool:
    """
    Создает запись в notifications для нового пользователя со всеми полями = 1.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        psn_id: PSN ID пользователя
    
    Returns:
        True при успешном создании, иначе False
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return False
            
            # Проверяем существует ли запись
            cursor.execute('SELECT user_id FROM notifications WHERE user_id = ?', (user_id,))
            if cursor.fetchone() is not None:
                return True  # Запись уже существует
            
            # Создаем новую запись со всеми полями = 1
            cursor.execute('''
                INSERT INTO notifications (user_id, psn_id, [check], speedrun, raid, ghost, hellmode, story, rivals, trials)
                VALUES (?, ?, 1, 1, 1, 1, 1, 1, 1, 1)
            ''', (user_id, psn_id or ''))
            
            return True
        
    except sqlite3.Error as e:
        print(f"Ошибка создания записи уведомлений: {e}")
        traceback.print_exc()
        return False


def update_notifications_psn_id(db_path: str, user_id: int, psn_id: str) -> bool:
    """
    Обновляет psn_id в таблице notifications.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        psn_id: Новый PSN ID
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute('''
                UPDATE notifications SET psn_id = ? WHERE user_id = ?
            ''', (psn_id or '', user_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления psn_id в уведомлениях: {e}")
        traceback.print_exc()
        return False


def get_user_notifications(db_path: str, user_id: int) -> Dict[str, int]:
    """
    Получает все настройки уведомлений пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Словарь с настройками уведомлений:
        {
            'check': 0 или 1,
            'speedrun': 0 или 1,
            'raid': 0 или 1,
            'ghost': 0 или 1,
            'hellmode': 0 или 1,
            'story': 0 или 1,
            'rivals': 0 или 1,
            'trials': 0 или 1
        }
        Если записи нет, возвращает все нули
    """
    default_notifications = {
        'check': 0,
        'speedrun': 0,
        'raid': 0,
        'ghost': 0,
        'hellmode': 0,
        'story': 0,
        'rivals': 0,
        'trials': 0
    }
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return default_notifications
            
            cursor.execute('''
                SELECT [check], speedrun, raid, ghost, hellmode, story, rivals, trials
                FROM notifications WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                return default_notifications
            
            return {
                'check': row[0],
                'speedrun': row[1],
                'raid': row[2],
                'ghost': row[3],
                'hellmode': row[4],
                'story': row[5],
                'rivals': row[6],
                'trials': row[7]
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка получения настроек уведомлений: {e}")
        traceback.print_exc()
        return default_notifications


def toggle_notification(db_path: str, user_id: int, notification_type: str) -> bool:
    """
    Переключает настройку уведомления пользователя (0 ↔ 1).
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        notification_type: Тип уведомления (check, speedrun, raid, ghost, hellmode, story, rivals, trials)
    
    Returns:
        True при успешном переключении, иначе False
    """
    valid_types = {'check', 'speedrun', 'raid', 'ghost', 'hellmode', 'story', 'rivals', 'trials'}
    if notification_type not in valid_types:
        print(f"Ошибка: недопустимый тип уведомления: {notification_type}")
        return False
    
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Получаем текущее значение
            field_name = f'[{notification_type}]' if notification_type == 'check' else notification_type
            cursor.execute(f'''
                SELECT {field_name} FROM notifications WHERE user_id = ?
            ''', (user_id,))
            
            row = cursor.fetchone()
            
            if not row:
                # Если записи нет, создаем её со всеми полями = 1, затем переключаем нужное
                # Получаем psn_id из users
                cursor.execute('SELECT psn_id FROM users WHERE user_id = ?', (user_id,))
                user_row = cursor.fetchone()
                psn_id = user_row[0] if user_row and user_row[0] else ''
                
                cursor.execute('''
                    INSERT INTO notifications (user_id, psn_id, [check], speedrun, raid, ghost, hellmode, story, rivals, trials)
                    VALUES (?, ?, 1, 1, 1, 1, 1, 1, 1, 1)
                ''', (user_id, psn_id))
                # Теперь переключаем на 0
                new_value = 0
            else:
                # Переключаем значение (0 → 1, 1 → 0)
                current_value = row[0]
                new_value = 1 if current_value == 0 else 0
            
            # Обновляем значение
            cursor.execute(f'''
                UPDATE notifications SET {field_name} = ? WHERE user_id = ?
            ''', (new_value, user_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка переключения уведомления: {e}")
        traceback.print_exc()
        return False


def save_feedback_message(db_path: str, user_id: int, group_message_id: int) -> bool:
    """
    Сохраняет связь между user_id и group_message_id для баг-репорта.
    
    Args:
        db_path: Путь к базе данных
        user_id: ID пользователя, отправившего баг-репорт через приложение
        group_message_id: ID сообщения бота в группе с баг-репортом
    
    Returns:
        True при успешном сохранении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute("""
                INSERT OR REPLACE INTO feedback_messages (user_id, group_message_id)
                VALUES (?, ?)
            """, (user_id, group_message_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка сохранения feedback_message: {e}")
        return False


def get_feedback_message_by_group_id(db_path: str, group_message_id: int) -> Optional[int]:
    """
    Получает user_id по group_message_id из таблицы feedback_messages.
    
    Args:
        db_path: Путь к базе данных
        group_message_id: ID сообщения бота в группе
    
    Returns:
        user_id если найдено, иначе None
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute("""
                SELECT user_id FROM feedback_messages 
                WHERE group_message_id = ?
            """, (group_message_id,))
            
            row = cursor.fetchone()
            
            if row:
                return row[0]
            
            return None
        
    except sqlite3.Error as e:
        print(f"Ошибка получения feedback_message: {e}")
        return None


def delete_feedback_message(db_path: str, group_message_id: int) -> bool:
    """
    Удаляет запись из таблицы feedback_messages по group_message_id.
    
    Args:
        db_path: Путь к базе данных
        group_message_id: ID сообщения бота в группе
    
    Returns:
        True при успешном удалении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            cursor.execute("""
                DELETE FROM feedback_messages 
                WHERE group_message_id = ?
            """, (group_message_id,))
            
            return cursor.rowcount > 0
    
    except sqlite3.Error as e:
        print(f"Ошибка удаления feedback_message: {e}")
        traceback.print_exc()
        return False


# ========== ФУНКЦИИ ДЛЯ РАБОТЫ СО СНИППЕТАМИ ==========

def get_all_snippets(db_path: str) -> List[Dict[str, Any]]:
    """
    Получает все сниппеты из базы данных.
    
    Args:
        db_path: Путь к файлу базы данных
    
    Returns:
        Список словарей с данными сниппетов
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            cursor.execute('''
                SELECT snippet_id, user_id, trigger, message, media, media_type, created_at, entities_json
                FROM snippets
                ORDER BY created_at DESC
            ''')
            
            rows = cursor.fetchall()
            snippets = []
            for row in rows:
                snippets.append({
                    'snippet_id': row[0],
                    'user_id': row[1],
                    'trigger': row[2],
                    'message': row[3],
                    'media': row[4],
                    'media_type': row[5],
                    'created_at': row[6],
                    'entities_json': row[7] if len(row) > 7 else None
                })
            
            return snippets
        
    except sqlite3.Error as e:
        print(f"Ошибка получения всех сниппетов: {e}")
        traceback.print_exc()
        return []


def get_user_snippets(db_path: str, user_id: int) -> List[Dict[str, Any]]:
    """
    Получает все сниппеты пользователя.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
    
    Returns:
        Список словарей с данными сниппетов пользователя
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return []
            
            cursor.execute('''
                SELECT snippet_id, user_id, trigger, message, media, media_type, created_at, entities_json
                FROM snippets
                WHERE user_id = ?
                ORDER BY created_at DESC
            ''', (user_id,))
            
            rows = cursor.fetchall()
            snippets = []
            for row in rows:
                snippets.append({
                    'snippet_id': row[0],
                    'user_id': row[1],
                    'trigger': row[2],
                    'message': row[3],
                    'media': row[4],
                    'media_type': row[5],
                    'created_at': row[6],
                    'entities_json': row[7] if len(row) > 7 else None
                })
            
            return snippets
        
    except sqlite3.Error as e:
        print(f"Ошибка получения сниппетов пользователя: {e}")
        traceback.print_exc()
        return []


def get_snippet_by_trigger(db_path: str, trigger: str) -> Optional[Dict[str, Any]]:
    """
    Получает сниппет по триггеру.
    
    Args:
        db_path: Путь к файлу базы данных
        trigger: Триггер сниппета
    
    Returns:
        Словарь с данными сниппета или None если не найден
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT snippet_id, user_id, trigger, message, media, media_type, created_at, entities_json
                FROM snippets
                WHERE trigger = ?
            ''', (trigger,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'snippet_id': row[0],
                'user_id': row[1],
                'trigger': row[2],
                'message': row[3],
                'media': row[4],
                'media_type': row[5],
                'created_at': row[6],
                'entities_json': row[7] if len(row) > 7 else None
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка получения сниппета по триггеру: {e}")
        traceback.print_exc()
        return None


def get_snippet_by_id(db_path: str, snippet_id: int) -> Optional[Dict[str, Any]]:
    """
    Получает сниппет по ID.
    
    Args:
        db_path: Путь к файлу базы данных
        snippet_id: ID сниппета
    
    Returns:
        Словарь с данными сниппета или None если не найден
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return None
            
            cursor.execute('''
                SELECT snippet_id, user_id, trigger, message, media, media_type, created_at, entities_json
                FROM snippets
                WHERE snippet_id = ?
            ''', (snippet_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                'snippet_id': row[0],
                'user_id': row[1],
                'trigger': row[2],
                'message': row[3],
                'media': row[4],
                'media_type': row[5],
                'created_at': row[6],
                'entities_json': row[7] if len(row) > 7 else None
            }
        
    except sqlite3.Error as e:
        print(f"Ошибка получения сниппета по ID: {e}")
        traceback.print_exc()
        return None


def create_snippet(
    db_path: str,
    user_id: int,
    trigger: str,
    message: str,
    media: Optional[str] = None,
    media_type: Optional[str] = None,
    entities_json: Optional[str] = None
) -> Optional[int]:
    """
    Создает новый сниппет.
    
    Args:
        db_path: Путь к файлу базы данных
        user_id: ID пользователя
        trigger: Триггер сниппета
        message: Текст сниппета
        media: file_id медиа (опционально)
        media_type: Тип медиа 'photo' или 'video' (опционально)
    
    Returns:
        snippet_id созданного сниппета или None при ошибке
    """
    try:
        with db_connection(db_path, init_if_missing=True) as cursor:
            if cursor is None:
                return None
            
            current_time = int(time.time())
            
            cursor.execute('''
                INSERT INTO snippets (user_id, trigger, message, media, media_type, created_at, entities_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, trigger, message, media, media_type, current_time, entities_json))
            
            return cursor.lastrowid
        
    except sqlite3.Error as e:
        print(f"Ошибка создания сниппета: {e}")
        traceback.print_exc()
        return None


def update_snippet(
    db_path: str,
    snippet_id: int,
    user_id: int,
    trigger: Optional[str] = None,
    message: Optional[str] = None,
    media: Optional[str] = None,
    media_type: Optional[str] = None,
    entities_json: Optional[str] = None
) -> bool:
    """
    Обновляет существующий сниппет.
    
    Args:
        db_path: Путь к файлу базы данных
        snippet_id: ID сниппета
        user_id: ID пользователя (для проверки прав)
        trigger: Новый триггер (опционально)
        message: Новый текст (опционально)
        media: Новый file_id медиа (опционально, None для удаления)
        media_type: Новый тип медиа (опционально, None для удаления)
    
    Returns:
        True при успешном обновлении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Проверяем, что сниппет существует и принадлежит пользователю
            cursor.execute('''
                SELECT snippet_id FROM snippets
                WHERE snippet_id = ? AND user_id = ?
            ''', (snippet_id, user_id))
            
            if not cursor.fetchone():
                return False
            
            # Формируем список полей для обновления
            update_fields = []
            update_values = []
            
            if trigger is not None:
                update_fields.append('trigger = ?')
                update_values.append(trigger)
            
            if message is not None:
                update_fields.append('message = ?')
                update_values.append(message)
            
            if media is not None:
                update_fields.append('media = ?')
                update_values.append(media)
            
            if media_type is not None:
                update_fields.append('media_type = ?')
                update_values.append(media_type)
            
            if entities_json is not None:
                update_fields.append('entities_json = ?')
                update_values.append(entities_json)
            
            if not update_fields:
                return False
            
            # Добавляем snippet_id в конец для WHERE
            update_values.append(snippet_id)
            
            # Выполняем обновление
            sql = f'''
                UPDATE snippets
                SET {', '.join(update_fields)}
                WHERE snippet_id = ?
            '''
            
            cursor.execute(sql, update_values)
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка обновления сниппета: {e}")
        traceback.print_exc()
        return False


def delete_snippet(db_path: str, snippet_id: int, user_id: int) -> bool:
    """
    Удаляет сниппет.
    
    Args:
        db_path: Путь к файлу базы данных
        snippet_id: ID сниппета
        user_id: ID пользователя (для проверки прав)
    
    Returns:
        True при успешном удалении, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            # Проверяем, что сниппет существует и принадлежит пользователю
            cursor.execute('''
                DELETE FROM snippets
                WHERE snippet_id = ? AND user_id = ?
            ''', (snippet_id, user_id))
            
            return cursor.rowcount > 0
        
    except sqlite3.Error as e:
        print(f"Ошибка удаления сниппета: {e}")
        traceback.print_exc()
        return False


def check_trigger_exists(db_path: str, trigger: str, exclude_snippet_id: Optional[int] = None) -> bool:
    """
    Проверяет, существует ли сниппет с указанным триггером.
    
    Args:
        db_path: Путь к файлу базы данных
        trigger: Триггер для проверки
        exclude_snippet_id: ID сниппета, который исключается из проверки (для обновления)
    
    Returns:
        True если триггер уже существует, иначе False
    """
    try:
        with db_connection(db_path) as cursor:
            if cursor is None:
                return False
            
            if exclude_snippet_id is not None:
                cursor.execute('''
                    SELECT snippet_id FROM snippets
                    WHERE trigger = ? AND snippet_id != ?
                ''', (trigger, exclude_snippet_id))
            else:
                cursor.execute('''
                    SELECT snippet_id FROM snippets
                    WHERE trigger = ?
                ''', (trigger,))
            
            return cursor.fetchone() is not None
        
    except sqlite3.Error as e:
        print(f"Ошибка проверки существования триггера: {e}")
        traceback.print_exc()
        return False
