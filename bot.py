# bot.py (обновленный)
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database import init_db
from handlers import common, director, agent
from services.scheduler import setup_scheduler

async def set_main_menu(bot: Bot):
    """Создает кнопку Меню с основными командами."""
    main_menu_commands = [
        types.BotCommand(command="/start", description="Перезапустить бота / Главное меню"),
        # Сюда можно будет добавить другие команды, например /help
    ]
    await bot.set_my_commands(main_menu_commands)

async def main():
    init_db()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()

    dp.include_router(common.router)
    dp.include_router(director.router)
    dp.include_router(agent.router)

    # Устанавливаем меню команд при запуске
    await set_main_menu(bot)

    # --- ЗАПУСКАЕМ ПЛАНИРОВЩИК ---
    setup_scheduler(bot)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())