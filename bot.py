# bot.py
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import init_db
from handlers import common, director, agent

async def main():
    # Инициализируем базу данных
    init_db()

    # Создаем объекты Бота и Диспетчера
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    # Подключаем роутеры из наших файлов с хэндлерами
    dp.include_router(common.router)
    dp.include_router(director.router)
    dp.include_router(agent.router)

    # Запускаем бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())