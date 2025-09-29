# bot.py

import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command

# Импортируем наш токен из файла config
from config import BOT_TOKEN

# Включаем логирование, чтобы видеть сообщения в терминале
logging.basicConfig(level=logging.INFO)

# Создаем объекты Бота и Диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Этот хэндлер будет срабатывать на команду /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("Бро, привет! Я готов к работе.")

# Основная функция для запуска бота
async def main():
    # Запускаем бота и пропускаем все накопленные входящие
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())