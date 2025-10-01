# handlers/agent.py (полностью обновленный)

import pandas as pd
import json
import asyncio
import logging
import pytz 

from datetime import datetime
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import get_agent_by_telegram_id, get_agent_schedule_for_day, save_report, get_point_id_by_name
from config import PHOTO_ARCHIVE_CHANNEL_ID

router = Router()

# Создаем состояния для процесса сдачи отчета
class Reporting(StatesGroup):
    confirming_point = State()      # Новое состояние для подтверждения точки
    waiting_for_photos = State()
    waiting_for_location = State()

# Этот словарь будет временно хранить фотографии от одного пользователя
user_photos_buffer = {}

# --- ОСНОВНЫЕ ФУНКЦИИ АГЕНТА ---

@router.message(F.text == "Мой маршрут на сегодня")
async def get_my_schedule(message: types.Message):
    agent_data = get_agent_by_telegram_id(message.from_user.id)
    if not agent_data:
        await message.answer("Ваш профиль не найден. Попробуйте /start.")
        return
    
    agent_db_id, _, _ = agent_data
    current_day_num = pd.Timestamp.now().weekday()
    day_mapping = {0: 'ПН', 1: 'ВТ', 2: 'СР', 3: 'ЧТ', 4: 'ПТ', 5: 'СБ', 6: 'ВС'}
    current_day = day_mapping.get(current_day_num, 'Н/Д')

    if current_day == 'ВС':
        await message.answer("Сегодня воскресенье, отдыхай! 🏖️"); return

    schedule = get_agent_schedule_for_day(agent_db_id, current_day)
    if not schedule:
        await message.answer(f"На сегодня ({current_day}) у тебя нет задач."); return
    
    builder = InlineKeyboardBuilder()
    for i, (point_name, _) in enumerate(schedule, 1):
        builder.add(InlineKeyboardButton(text=f"{i}. {point_name}", callback_data=f"point_{point_name}"))
    builder.adjust(1)
    
    await message.answer(f"Твой маршрут на **{current_day}**. \nНажми на точку, чтобы начать отчет:", reply_markup=builder.as_markup())


# --- ПРОЦЕСС СДАЧИ ОТЧЕТА ---

@router.callback_query(F.data.startswith("point_"))
async def select_point_callback(callback: types.CallbackQuery, state: FSMContext):
    point_name = callback.data.split("_", 1)[1]
    await state.update_data(point_name=point_name)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Да, верно", callback_data="confirm_point_yes"))
    builder.add(InlineKeyboardButton(text="⬅️ Нет, назад", callback_data="confirm_point_no"))
    
    await callback.message.edit_text(f"Вы выбрали точку: <b>{point_name}</b>\n\nВсе верно?", reply_markup=builder.as_markup())
    await state.set_state(Reporting.confirming_point)


@router.callback_query(F.data == "confirm_point_no", Reporting.confirming_point)
async def confirm_point_no(callback: types.CallbackQuery, state: FSMContext):
    # Если пользователь нажал "Нет", просто удаляем сообщение с вопросом
    # и он может выбрать другую точку из списка выше.
    await callback.message.delete()
    await state.clear()


@router.callback_query(F.data == "confirm_point_yes", Reporting.confirming_point)
async def confirm_point_yes(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Отлично! Теперь отправьте от 2 до 4 фотографий. Можно отправить их группой (альбомом).")
    await state.set_state(Reporting.waiting_for_photos)


@router.message(Reporting.waiting_for_photos, F.photo)
async def handle_photos(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in user_photos_buffer:
        user_photos_buffer[user_id] = []
    
    user_photos_buffer[user_id].append(message.photo[-1].file_id)

    # Используем "отложенную задачу", чтобы собрать все фото из альбома
    async def process_album():
        # Ждем 2 секунды. Если за это время придут еще фото, таймер сбросится.
        # Если нет - значит, альбом получен полностью.
        await asyncio.sleep(2)
        photos_received = user_photos_buffer.pop(user_id, [])

        if not photos_received: # Если по какой-то причине буфер уже пуст
            return

        if not (2 <= len(photos_received) <= 4):
            await message.answer(f"Нужно отправить от 2 до 4 фотографий. Вы отправили {len(photos_received)}. Пожалуйста, выберите точку и попробуйте снова.")
            await state.clear()
            return
        
        await state.update_data(photos=photos_received)
        kb = [[types.KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
        await message.answer("Отлично, фото приняты! 👍\nТеперь, пожалуйста, подтвердите ваше местоположение, нажав на кнопку ниже.", reply_markup=keyboard)
        await state.set_state(Reporting.waiting_for_location)

    asyncio.create_task(process_album())


@router.message(Reporting.waiting_for_location, F.location)
async def handle_location(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    point_name = data.get("point_name")
    photo_file_ids = data.get("photos")
    
    agent_data = get_agent_by_telegram_id(message.from_user.id)
    point_id = get_point_id_by_name(point_name)

    if not all([agent_data, point_id, photo_file_ids]):
        await message.answer("Произошла ошибка, не все данные были собраны. Попробуйте начать заново.", reply_markup=types.ReplyKeyboardRemove())
        await state.clear()
        return

    agent_db_id, agent_full_name, _ = agent_data
    
    save_report(
        user_id=agent_db_id,
        point_id=point_id,
        photo_file_ids_json=json.dumps(photo_file_ids),
        latitude=message.location.latitude,
        longitude=message.location.longitude
    )

    await message.answer(f"✅ Отчет по точке <b>{point_name}</b> принят! Спасибо!", reply_markup=types.ReplyKeyboardRemove())
    user_timezone = pytz.timezone('Asia/Almaty') 

    # Конвертируем UTC время сообщения в твой часовой пояс
    local_time = message.date.astimezone(user_timezone)

    caption = (
        f"📸 **Новый фотоотчет**\n\n"
        f"👤 **Агент:** {agent_full_name}\n"
        f"📍 **Торговая точка:** {point_name}\n"
        f"⏰ **Время:** {local_time.strftime('%Y-%m-%d %H:%M:%S')} ({user_timezone.zone})"
    )
    
    try:
        media_group = [types.InputMediaPhoto(media=file_id) for file_id in photo_file_ids]
        if media_group:
            media_group[0].caption = caption
            await bot.send_media_group(chat_id=PHOTO_ARCHIVE_CHANNEL_ID, media=media_group)
    except Exception as e:
        logging.error(f"Не удалось отправить фото в архивный канал {PHOTO_ARCHIVE_CHANNEL_ID}: {e}")
        await bot.send_message(chat_id=message.from_user.id, text="Не удалось отправить фото в архив, но отчет в базе сохранен.")

    await state.clear()