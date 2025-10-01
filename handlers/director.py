# handlers/director.py (полностью обновленный)
import logging
import pandas as pd
from aiogram import Router, F, types, Bot

from config import DIRECTOR_ID
from database import create_invite_code, save_schedule_from_dataframe

router = Router()
# Фильтр теперь будет применяться и к callback_query
router.message.filter(F.from_user.id == DIRECTOR_ID)
router.callback_query.filter(F.from_user.id == DIRECTOR_ID)

# --- НОВЫЕ ХЭНДЛЕРЫ ДЛЯ INLINE-КНОПОК ---

@router.callback_query(F.data == "director_create_invite")
async def create_invite_handler(callback: types.CallbackQuery):
    new_code = create_invite_code(role='agent')
    await callback.message.answer(
        f"Создан новый инвайт-код для Агента:\n\n"
        f"`{new_code}`\n\n"
        f"Отправьте этот код новому сотруднику. Он действует один раз.",
        parse_mode="Markdown"
    )
    await callback.answer() # "Закрываем" часики на кнопке

@router.callback_query(F.data == "director_upload_schedule")
async def ask_for_schedule_file(callback: types.CallbackQuery):
    await callback.message.answer("Пожалуйста, отправьте мне Excel-файл с расписанием.")
    await callback.answer()

# --- ХЭНДЛЕР ДЛЯ ПРИЕМА ФАЙЛА ОСТАЕТСЯ ПРЕЖНИМ ---

@router.message(F.document)
async def handle_schedule_file(message: types.Message, bot: Bot):
    if not message.document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("Это не похоже на Excel-файл."); return
        
    await message.answer("Получил файл. Начинаю обработку...")
    try:
        file_info = await bot.get_file(message.document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        df = pd.read_excel(downloaded_file, engine='openpyxl', header=1)
        
        # --- Добавляем подсчет точек, как ты и хотел ---
        affected_agent_ids = save_schedule_from_dataframe(df)
        num_agents = len(df['ТМ'].unique())
        num_points = len(df['ТТ'].unique())

        await message.answer(
            f"✅ Расписание успешно сохранено!\n\n"
            f"👨‍💼 Уникальных агентов: {num_agents}\n"
            f"🏢 Уникальных торговых точек: {num_points}"
        )

        if affected_agent_ids:
            # ... (логика уведомлений остается без изменений)
            notification_count = 0
            for agent_id in affected_agent_ids:
                try:
                    await bot.send_message(agent_id, text="❗️<b>Внимание!</b>\nВаш маршрут был изменен.")
                    notification_count += 1
                except Exception as e:
                    logging.warning(f"Не удалось отправить уведомление пользователю {agent_id}: {e}")
            await message.answer(f"🔔 Отправлено уведомлений об изменении: {notification_count}")

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"Ой, произошла ошибка при обработке файла: {e}")