# telegram_utils.py
# Утилиты для работы с Telegram Bot API

import json
import os
import aiohttp
from typing import Optional, List, Dict, Any

MEDIA_GROUP_LIMIT = 9


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


async def send_telegram_video(
    bot_token: str,
    chat_id: str,
    video_path: str,
    caption: str = "",
    reply_markup: Optional[dict] = None,
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Отправляет видео в Telegram через Bot API.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendVideo"

    with open(video_path, 'rb') as video_file:
        data = aiohttp.FormData()
        data.add_field('chat_id', chat_id)
        data.add_field('video', video_file, filename=os.path.basename(video_path))
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
    media_items: List[Dict[str, str]],
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Отправляет медиагруппу (фото/видео) в Telegram через Bot API.
    """
    url = f"https://api.telegram.org/bot{bot_token}/sendMediaGroup"

    media_payload = []
    file_handles = []

    try:
        for index, item in enumerate(media_items):
            attach_id = f'media_{index}'
            media_payload.append({
                "type": item.get("type", "photo"),
                "media": f"attach://{attach_id}"
            })
            file_path = item.get("path")
            if not file_path:
                continue
            file_handles.append(open(file_path, 'rb'))

        data = aiohttp.FormData()
        data.add_field('chat_id', chat_id)
        data.add_field('media', json.dumps(media_payload))
        data.add_field('parse_mode', 'HTML')

        if message_thread_id:
            data.add_field('message_thread_id', message_thread_id)

        for index, file_handle in enumerate(file_handles):
            filename = os.path.basename(media_items[index].get("path", f'media_{index}'))
            data.add_field(f'media_{index}', file_handle, filename=filename)

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                return await response.json()
    finally:
        for file_handle in file_handles:
            file_handle.close()


def _chunk_media_items(items: List[Dict[str, str]], chunk_size: int) -> List[List[Dict[str, str]]]:
    if chunk_size <= 0:
        return [items]
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


async def send_photos_to_telegram_group(
    bot_token: str,
    chat_id: str,
    photo_paths: List[str],
    message_text: str = "",
    reply_markup: Optional[dict] = None,
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Вспомогательная обёртка для обратной совместимости с кодом, который передаёт только фотографии.
    """
    media_items = [{"type": "photo", "path": path} for path in photo_paths]
    return await send_media_to_telegram_group(
        bot_token=bot_token,
        chat_id=chat_id,
        media_items=media_items,
        message_text=message_text,
        reply_markup=reply_markup,
        message_thread_id=message_thread_id,
    )


async def send_media_to_telegram_group(
    bot_token: str,
    chat_id: str,
    media_items: List[Dict[str, str]],
    message_text: str = "",
    reply_markup: Optional[dict] = None,
    message_thread_id: Optional[str] = None
) -> dict:
    """
    Отправляет смешанную медиагруппу (фото и видео), разбивая по лимиту Telegram и добавляя текст.
    """
    if not media_items:
        return await send_telegram_message(
            bot_token=bot_token,
            chat_id=chat_id,
            text=message_text,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id,
        )

    if len(media_items) == 1:
        item = media_items[0]
        media_type = item.get("type", "photo")
        media_path = item.get("path", "")

        if media_type == 'video':
            return await send_telegram_video(
                bot_token=bot_token,
                chat_id=chat_id,
                video_path=media_path,
                caption=message_text,
                reply_markup=reply_markup,
                message_thread_id=message_thread_id,
            )

        return await send_telegram_photo(
            bot_token=bot_token,
            chat_id=chat_id,
            photo_path=media_path,
            caption=message_text,
            reply_markup=reply_markup,
            message_thread_id=message_thread_id,
        )

    batches = _chunk_media_items(media_items, MEDIA_GROUP_LIMIT)
    first_message_id: Optional[int] = None
    last_response: Optional[dict] = None

    for batch in batches:
        batch_result = await send_telegram_media_group(
            bot_token=bot_token,
            chat_id=chat_id,
            media_items=batch,
            message_thread_id=message_thread_id,
        )

        if first_message_id is None and batch_result.get('ok') and batch_result.get('result'):
            first_message = batch_result['result'][0]
            first_message_id = first_message.get('message_id')

        last_response = batch_result

    if not message_text:
        return last_response or {"ok": True}

    return await send_telegram_message(
        bot_token=bot_token,
        chat_id=chat_id,
        text=message_text,
        reply_markup=reply_markup,
        message_thread_id=message_thread_id,
        reply_to_message_id=first_message_id,
    )


async def get_chat_member(
    bot_token: str,
    chat_id: str,
    user_id: int
) -> dict:
    """
    Получает информацию об участнике чата через Telegram Bot API.
    
    Args:
        bot_token: Токен бота
        chat_id: ID чата (группы)
        user_id: ID пользователя
    
    Returns:
        Результат запроса к Telegram API с информацией об участнике
    """
    url = f"https://api.telegram.org/bot{bot_token}/getChatMember"
    
    data = {
        "chat_id": chat_id,
        "user_id": user_id
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data) as response:
            return await response.json()

