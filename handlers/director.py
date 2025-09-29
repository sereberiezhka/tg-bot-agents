# handlers/director.py
import logging
import pandas as pd
from aiogram import Router, F, types, Bot

from config import DIRECTOR_ID
from database import create_invite_code, save_schedule_from_dataframe

router = Router()
# Ограничиваем все хэндлеры в этом файле, чтобы они срабатывали только для Директора
router.message.filter(F.from_user.id == DIRECTOR_ID)

@router.message(F.text == "Создать инвайт-код")
async def create_invite_handler(message: types.Message):
    new_code = create_invite_code(role='agent')
    await message.answer(
        f"Создан новый инвайт-код для Агента:\n\n"
        f"`{new_code}`\n\n"
        f"Отправьте этот код новому сотруднику. Он действует один раз.",
        parse_mode="Markdown"
    )

@router.message(F.text == "Загрузить расписание")
async def ask_for_schedule_file(message: types.Message):
    await message.answer("Пожалуйста, отправьте мне Excel-файл с расписанием.")

@router.message(F.document)
async def handle_schedule_file(message: types.Message, bot: Bot):
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("Это не похоже на Excel-файл.")
        return
    await message.answer("Получил файл. Начинаю обработку...")
    try:
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        df = pd.read_excel(downloaded_file, engine='openpyxl', header=1)
        required_columns = ['ТМ', 'ТТ', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
        if not all(col in df.columns for col in required_columns):
            await message.answer(f"Ошибка! В файле отсутствуют обязательные колонки.\nНашел: {list(df.columns)}")
            return
        
        save_schedule_from_dataframe(df) # Здесь позже добавим уведомления
        num_agents = len(df['ТМ'].unique())
        await message.answer(f"✅ Расписание успешно сохранено в базу!\nУникальных агентов: {num_agents}")

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"Ой, произошла ошибка при обработке файла: {e}")