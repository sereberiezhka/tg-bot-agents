# handlers/director.py
import logging
import pandas as pd
from aiogram import Router, F, types, Bot

from config import DIRECTOR_ID
from database import create_invite_code, save_schedule_from_dataframe
from aiogram.filters import Command
from database import get_all_users_for_debug # Нам понадобится новая функция в database.py

router = Router()
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

@router.message(Command("getusers"))
async def get_all_users_command(message: types.Message):
    all_users = get_all_users_for_debug()
    if not all_users:
        await message.answer("В базе данных нет пользователей.")
        return
    
    response = "<b>Список всех пользователей в базе:</b>\n\n"
    for user in all_users:
        user_id, full_name, role, telegram_id = user
        # Если telegram_id есть, покажем его, если нет - напишем "НЕТ"
        tg_id_str = telegram_id if telegram_id else "<b>НЕТ</b>"
        response += f"ID: {user_id} | {full_name} ({role}) | TG_ID: {tg_id_str}\n"
    
    await message.answer(response)

@router.message(F.document)
async def handle_schedule_file(message: types.Message, bot: Bot):
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("Это не похоже на Excel-файл.")
        return
    await message.answer("Получил файл. Начинаю обработку и сравнение маршрутов...")
    try:
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        df = pd.read_excel(downloaded_file, engine='openpyxl', header=1)
        required_columns = ['ТМ', 'ТТ', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
        if not all(col in df.columns for col in required_columns):
            await message.answer(f"Ошибка! В файле отсутствуют обязательные колонки.\nНашел: {list(df.columns)}")
            return
        
        # --- !!! НОВАЯ ЛОГИКА ЗДЕСЬ !!! ---
        # Сохраняем и получаем список ID для уведомления
        affected_agent_ids = save_schedule_from_dataframe(df)
        
        num_agents = len(df['ТМ'].unique())
        num_points = len(df['ТТ'].unique()) # <-- Считаем уникальные точки
        await message.answer(
            f"✅ Расписание успешно сохранено в базу!\n\n"
            f"👨‍💼 Уникальных агентов: {num_agents}\n"
            f"🏢 Уникальных торговых точек: {num_points}"
            )

        # Рассылаем уведомления, если есть кому
        if affected_agent_ids:
            notification_count = 0
            for agent_id in affected_agent_ids:
                try:
                    await bot.send_message(
                        chat_id=agent_id,
                        text=(
                            "❗️<b>Внимание!</b>\n"
                            "Ваш маршрут был изменен. Пожалуйста, проверьте актуальное расписание, "
                            "нажав на кнопку 'Мой маршрут на сегодня'."
                        )
                    )
                    notification_count += 1
                except Exception as e:
                    # Если бот заблокирован у пользователя, мы просто пропустим его
                    logging.warning(f"Не удалось отправить уведомление пользователю {agent_id}: {e}")
            
            await message.answer(f"🔔 Отправлено уведомлений об изменении: {notification_count}")

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"Ой, произошла ошибка при обработке файла: {e}")