# bot.py

import asyncio
import logging
import pandas as pd
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command

# Импортируем наши настройки
from config import BOT_TOKEN, DIRECTOR_ID

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Создаем объекты Бота и Диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хэндлер на команду /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_name = message.from_user.full_name
    await message.answer(f"Бро, {user_name}, привет! Я готов к работе.")


# Хэндлер на загрузку документа (Excel-файла)
# Срабатывает, только если сообщение прислал Директор
@dp.message(F.document & (F.from_user.id == DIRECTOR_ID))
async def handle_schedule_file(message: types.Message):
    document = message.document
    
    # Проверяем, что это Excel файл
    if not document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("Это не похоже на Excel-файл. Пожалуйста, загрузи файл в формате .xlsx")
        return

    await message.answer("Получил файл. Начинаю обработку...")

    try:
        # Скачиваем файл во временную папку
        file_info = await bot.get_file(document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        # Читаем данные из Excel файла с помощью pandas
        # openpyxl нужен для .xlsx файлов
        df = pd.read_excel(downloaded_file, engine='openpyxl', header=1)

        # Простая проверка, что в файле есть нужные колонки
        required_columns = ['ТМ', 'ТТ', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
        if not all(col in df.columns for col in required_columns):
            await message.answer("Ошибка! В файле отсутствуют обязательные колонки: 'ТМ', 'ТТ', 'ПН', 'ВТ'...")
            return

        # Если все хорошо
        num_rows = len(df)
        num_agents = len(df['ТМ'].unique())
        
        await message.answer(
            f"✅ Расписание успешно загружено и обработано!\n\n"
            f"📊 **Статистика по файлу:**\n"
            f"- Всего строк (маршрутов): {num_rows}\n"
            f"- Уникальных торговых агентов: {num_agents}",
            parse_mode="HTML" # Используем HTML для жирного текста
        )

        # Здесь в будущем будет код для сохранения этого расписания в базу данных

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"Ой, произошла ошибка при обработке файла. Подробности: {e}")


# Хэндлер для всех остальных сообщений от Директора
@dp.message(F.from_user.id == DIRECTOR_ID)
async def any_message_from_director(message: types.Message):
    await message.answer("Я вас слушаю, Директор. Чтобы обновить расписание, просто пришлите мне Excel-файл.")


# Основная функция для запуска бота
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())