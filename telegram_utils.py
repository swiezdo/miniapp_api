# telegram_utils.py
# Утилиты для работы с Telegram Bot API

import json
import aiohttp
from typing import Optional, List, Dict, Any


async def send_telegram_message(
    bot_token: str,
    chat_id: str,
    text: str,
    reply_markup: Optional[dict] = None,
    message_thread_id: Optional[str] = None,
    reply_to_message_id: Optional[int] = None
) -> dict:
    """
    Отправляет сообщение в Telegram через Bot API.
    
    Args:
        bot_token: Токен бота
        chat_id: ID чата
        text: Текст сообщения
        reply_markup: Inline клавиатура (опционально)
        message_thread_id: ID темы (опционально)
        reply_to_message_id: ID сообщения для ответа (опционально)
    
    Returns:
        Результат запроса к Telegram API
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML"
    }
    
    if message_thread_id:
        data["message_thread_id"] = message_thread_id
    
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    
    if reply_to_message_id:
        data["reply_to_message_id"] = reply_to_message_id
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            return await response.json()


async def send_telegram_photo(
    bot_token: str,
    chat_id: str,
    photo_path: str,
    caption: str = "",
    reply_markup: Optional[dict] = None,
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Отправляет фотографию в Telegram через Bot API.
    
    Args:
        bot_token: Токен бота
        chat_id: ID чата
        photo_path: Путь к файлу фотографии
        caption: Подпись к фото (опционально)
        reply_markup: Inline клавиатура (опционально)
        message_thread_id: ID темы (опционально)
    
    Returns:
        Результат запроса к Telegram API
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    
    with open(photo_path, 'rb') as photo_file:
        data = aiohttp.FormData()
        data.add_field('chat_id', chat_id)
        data.add_field('photo', photo_file, filename='photo.jpg')
        data.add_field('caption', caption)
        data.add_field('parse_mode', 'HTML')
        
        if message_thread_id:
            data.add_field('message_thread_id', message_thread_id)
        
        if reply_markup:
            data.add_field('reply_markup', json.dumps(reply_markup))
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.json()


async def send_telegram_media_group(
    bot_token: str,
    chat_id: str,
    photo_paths: List[str],
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Отправляет группу фотографий в Telegram через Bot API.
    
    Args:
        bot_token: Токен бота
        chat_id: ID чата
        photo_paths: Список путей к файлам фотографий
        message_thread_id: ID темы (опционально)
    
    Returns:
        Результат запроса к Telegram API
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMediaGroup"
    
    media = []
    for i, photo_path in enumerate(photo_paths):
        media.append({
            "type": "photo",
            "media": f"attach://photo_{i}"
        })
    
    # Открываем все файлы
    photo_files = []
    try:
        for photo_path in photo_paths:
            photo_files.append(open(photo_path, 'rb'))
        
        data = aiohttp.FormData()
        data.add_field('chat_id', chat_id)
        data.add_field('media', json.dumps(media))
        data.add_field('parse_mode', 'HTML')
        
        if message_thread_id:
            data.add_field('message_thread_id', message_thread_id)
        
        # Добавляем файлы в FormData
        for i, photo_file in enumerate(photo_files):
            data.add_field(f'photo_{i}', photo_file, filename=f'photo_{i}.jpg')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                result = await response.json()
                return result
    finally:
        # Закрываем все файлы
        for photo_file in photo_files:
            photo_file.close()


async def send_photos_to_telegram_group(
    bot_token: str,
    chat_id: str,
    photo_paths: List[str],
    message_text: str = "",
    reply_markup: Optional[dict] = None,
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Универсальная функция отправки фото в Telegram группу.
    
    Автоматически выбирает между sendPhoto (1 фото) и sendMediaGroup (несколько фото).
    Обрабатывает reply_to_message_id для медиагрупп.
    
    Args:
        bot_token: Токен бота
        chat_id: ID чата
        photo_paths: Список путей к файлам фотографий
        message_text: Текст сообщения
        reply_markup: Inline клавиатура (опционально)
        message_thread_id: ID темы (опционально)
    
    Returns:
        Результат запроса к Telegram API
    """
    if len(photo_paths) == 1:
        # Одна фотография - отправляем как фото с подписью и кнопками
        return await send_telegram_photo(
            bot_token=bot_token,
            chat_id=chat_id,
            photo_path=photo_paths[0],
            caption=message_text,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id
        )
    elif len(photo_paths) > 1:
        # Несколько фотографий - сначала медиагруппа, потом текст с кнопками как ответ
        media_group_result = await send_telegram_media_group(
            bot_token=bot_token,
            chat_id=chat_id,
            photo_paths=photo_paths,
            message_thread_id=message_thread_id
        )
        
        # Получаем message_id первого сообщения из медиагруппы
        reply_to_message_id = None
        if media_group_result.get('ok') and media_group_result.get('result'):
            # Первое сообщение в медиагруппе - это первое фото
            reply_to_message_id = media_group_result['result'][0].get('message_id')
        
        # Отправляем текстовое сообщение с кнопками как ответ на первое фото
        return await send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=message_text,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id,
            reply_to_message_id=reply_to_message_id
        )
    else:
        # Нет фотографий - только текстовое сообщение
        return await send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=message_text,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id
        )

