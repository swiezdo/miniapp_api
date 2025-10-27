#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram Bot для обработки заявок на трофеи Tsushima Mini App
Отдельное приложение, которое работает независимо от API сервера
Использует aiogram 3.18.0
"""

import os
import asyncio
import aiohttp
import json
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Конфигурация
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
TROPHY_GROUP_CHAT_ID = os.getenv("TROPHY_GROUP_CHAT_ID", "-1002348168326")
TROPHY_GROUP_TOPIC_ID = os.getenv("TROPHY_GROUP_TOPIC_ID", "5675")
MINI_APP_URL = os.getenv("MINI_APP_URL", "https://your-domain.com/docs/index.html")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в .env файле")

# Создаем экземпляры бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def start_command(message: types.Message):
    """Обработчик команды /start"""
    user = message.from_user
    
    welcome_text = f"""Привет, {user.first_name}! 👋

Я бот для системы трофеев Tsushima.Ru Mini App.

🏆 Здесь вы можете:
• Подавать заявки на получение трофеев
• Отслеживать свой прогресс
• Получать уведомления о статусе заявок

Для начала работы откройте мини-приложение:"""
    
    # Создаем клавиатуру с кнопкой WebApp
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="🏆 Открыть трофеи",
        web_app=WebAppInfo(url=f"{MINI_APP_URL}#trophies")
    ))
    
    await message.answer(welcome_text, reply_markup=builder.as_markup())

async def get_trophy_and_user_info(user_id: int, trophy_id: str) -> tuple:
    """Получает название трофея и PSN ID пользователя"""
    trophy_name = trophy_id
    psn_id = str(user_id)
    
    try:
        # Получаем данные трофея
        async with aiohttp.ClientSession() as session:
            trophy_url = f"{API_BASE_URL}/api/trophy_info/{trophy_id}"
            async with session.get(trophy_url) as trophy_response:
                if trophy_response.status == 200:
                    trophy_data = await trophy_response.json()
                    trophy_name = f"{trophy_data.get('name', trophy_id)} {trophy_data.get('emoji', '')}".strip()
            
            # Получаем PSN ID пользователя
            user_url = f"{API_BASE_URL}/api/user_info/{user_id}"
            async with session.get(user_url) as user_response:
                if user_response.status == 200:
                    user_data = await user_response.json()
                    psn_id = user_data.get('psn_id', str(user_id))
    except Exception as e:
        logger.error(f"Ошибка получения данных: {e}")
    
    return trophy_name, psn_id

@dp.callback_query(F.data.startswith("trophy_approve:"))
async def handle_trophy_approve(callback: types.CallbackQuery):
    """Обработчик callback кнопки одобрения трофея"""
    await callback.answer()
    
    callback_data = callback.data
    parts = callback_data.split(":")
    
    if len(parts) == 3:
        user_id = int(parts[1])
        trophy_id = parts[2]
        
        # Получаем данные трофея и пользователя
        trophy_name, psn_id = await get_trophy_and_user_info(user_id, trophy_id)
        
        success = await approve_trophy(user_id, trophy_id)
        
        if success:
            await callback.message.edit_text(
                f"✅ Заявка одобрена\n\nТрофей: {trophy_name}\nПользователь: {psn_id}"
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка при одобрении трофея"
            )

@dp.callback_query(F.data.startswith("trophy_reject:"))
async def handle_trophy_reject(callback: types.CallbackQuery):
    """Обработчик callback кнопки отклонения трофея"""
    await callback.answer()
    
    callback_data = callback.data
    parts = callback_data.split(":")
    
    if len(parts) == 3:
        user_id = int(parts[1])
        trophy_id = parts[2]
        
        # Получаем данные трофея и пользователя
        trophy_name, psn_id = await get_trophy_and_user_info(user_id, trophy_id)
        
        success = await reject_trophy(user_id, trophy_id)
        
        if success:
            await callback.message.edit_text(
                f"❌ Заявка отклонена\n\nТрофей: {trophy_name}\nПользователь: {psn_id}"
            )
        else:
            await callback.message.edit_text(
                f"❌ Ошибка при отклонении трофея"
            )

async def approve_trophy(user_id: int, trophy_id: str) -> bool:
    """Одобряет трофей через API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE_URL}/api/trophies.approve"
            data = {
                "user_id": user_id,
                "trophy_id": trophy_id
            }
            
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Трофей {trophy_id} одобрен для пользователя {user_id}: {result}")
                    return True
                else:
                    logger.error(f"Ошибка одобрения трофея: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Ошибка при одобрении трофея: {e}")
        return False

async def reject_trophy(user_id: int, trophy_id: str) -> bool:
    """Отклоняет трофей через API"""
    try:
        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE_URL}/api/trophies.reject"
            data = {
                "user_id": user_id,
                "trophy_id": trophy_id
            }
            
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"Трофей {trophy_id} отклонен для пользователя {user_id}: {result}")
                    return True
                else:
                    logger.error(f"Ошибка отклонения трофея: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"Ошибка при отклонении трофея: {e}")
        return False

async def main():
    """Основная функция запуска бота"""
    logger.info("🤖 Запуск Telegram бота для системы трофеев...")
    logger.info(f"📡 API URL: {API_BASE_URL}")
    logger.info(f"🏆 Группа трофеев: {TROPHY_GROUP_CHAT_ID}")
    
    # Запускаем бота
    logger.info("🚀 Бот запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")