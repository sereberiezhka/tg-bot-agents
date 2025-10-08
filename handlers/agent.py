# handlers/agent.py (полностью обновленный)
import pandas as pd
import json
import asyncio
import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services.google_sheets import add_report_to_sheet

from database import (
    get_agent_by_telegram_id, get_agent_schedule_for_day, save_report, 
    get_point_id_by_name, get_visited_points_today
)
from config import PHOTO_ARCHIVE_CHANNEL_ID

router = Router()

class Reporting(StatesGroup):
    confirming_point = State()
    waiting_for_photos = State()
    waiting_for_location = State()

user_photos_buffer = {}

# НОВЫЙ ХЭНДЛЕР ДЛЯ КНОПКИ
@router.callback_query(F.data == "agent_get_schedule")
async def get_my_schedule_callback(callback: types.CallbackQuery):
    # Вызываем нашу основную функцию отображения маршрута
    await show_schedule(callback.message)
    await callback.answer()

# Основная функция, которую теперь можно будет вызывать из разных мест
async def show_schedule(message: types.Message):
    agent_data = get_agent_by_telegram_id(message.chat.id)
    if not agent_data:
        await message.answer("Ваш профиль не найден. Попробуйте /start."); return
    
    agent_db_id, _, _ = agent_data
    
    # Получаем список посещенных СЕГОДНЯ точек
    visited_point_ids = get_visited_points_today(agent_db_id)
    
    day_mapping = {0: 'ПН', 1: 'ВТ', 2: 'СР', 3: 'ЧТ', 4: 'ПТ', 5: 'СБ', 6: 'ВС'}
    weekday_num = pd.Timestamp.now().weekday()
    current_day_key = day_mapping.get(weekday_num) # 'ПН', 'ВТ' и т.д.

    # Получаем полное русское название для красивого вывода
    day_names_full = {
        'ПН': 'Понедельник', 'ВТ': 'Вторник', 'СР': 'Среда', 
        'ЧТ': 'Четверг', 'ПТ': 'Пятница', 'СБ': 'Суббота', 'ВС': 'Воскресенье'
    }
    current_day_full_name = day_names_full.get(current_day_key, "Неизвестный день")

    schedule = get_agent_schedule_for_day(agent_db_id, current_day_key)
    if not schedule:
        await message.answer(f"На сегодня ({current_day_full_name}) у тебя нет задач."); return
    
    builder = InlineKeyboardBuilder()
    for point_id, point_name, _ in schedule:
        # --- ЛОГИКА С ГАЛОЧКАМИ ---
        is_visited = point_id in visited_point_ids
        button_text = f"✅ {point_name}" if is_visited else f"📍 {point_name}"
        
        # Делаем кнопку неактивной, если точка посещена
        if is_visited:
            builder.add(InlineKeyboardButton(text=button_text, callback_data="point_visited"))
        else:
            builder.add(InlineKeyboardButton(text=button_text, callback_data=f"point_{point_id}_{point_name}"))

    builder.adjust(1)
    
    # Редактируем старое сообщение или отправляем новое
    try:
        await message.edit_text(f"Твой маршрут на <b>{current_day_full_name}</b>. \nНажми на точку, чтобы начать отчет:", reply_markup=builder.as_markup())
    except:
        await message.answer(f"Твой маршрут на <b>{current_day_full_name}</b>. \nНажми на точку, чтобы начать отчет:", reply_markup=builder.as_markup())

@router.callback_query(F.data == "point_visited")
async def point_visited_callback(callback: types.CallbackQuery):
    await callback.answer("Эта точка уже посещена сегодня.", show_alert=True)


# Остальная логика отчета остается почти такой же, но с мелкими правками
@router.callback_query(F.data.startswith("point_"))
async def select_point_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split("_", 2)
    point_id = int(parts[1])
    point_name = parts[2]
    
    await state.update_data(point_name=point_name, point_id=point_id)

    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="✅ Да, верно", callback_data="confirm_point_yes"))
    builder.add(InlineKeyboardButton(text="⬅️ Нет, назад", callback_data="confirm_point_no"))
    
    await callback.message.edit_text(f"Вы выбрали точку: <b>{point_name}</b>\n\nВсе верно?", reply_markup=builder.as_markup())
    await state.set_state(Reporting.confirming_point)


@router.callback_query(F.data == "confirm_point_no", Reporting.confirming_point)
async def confirm_point_no(callback: types.CallbackQuery, state: FSMContext):
    # Возвращаемся к списку точек
    await show_schedule(callback.message)
    await state.clear()

@router.callback_query(F.data == "confirm_point_yes", Reporting.confirming_point)
async def confirm_point_yes(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    point_name = data.get("point_name")
    await callback.message.edit_text(f"Точка: <b>{point_name}</b>\n\nОтправьте от 2 до 8 фотографий (можно альбомом).")
    await state.set_state(Reporting.waiting_for_photos)


@router.message(Reporting.waiting_for_photos, F.photo)
async def handle_photos(message: types.Message, state: FSMContext, bot: Bot):
    user_id = message.from_user.id
    if user_id not in user_photos_buffer: user_photos_buffer[user_id] = []
    user_photos_buffer[user_id].append(message.photo[-1].file_id)
    
    async def process_album():
        await asyncio.sleep(7)
        photos_received = user_photos_buffer.pop(user_id, [])
        if not photos_received: return
        if not (2 <= len(photos_received) <= 8):
            # Получаем данные о точке из состояния
            data = await state.get_data()
            point_name = data.get("point_name", "Неизвестная точка")

            # Очищаем буфер, чтобы старые фото не мешали
            user_photos_buffer.pop(user_id, None)

            await message.answer(
                f"❌ **Ошибка!** Нужно отправить от 2 до 8 фотографий. Вы отправили {len(photos_received)}.\n\n"
                f"Пожалуйста, отправьте правильное количество фото для точки <b>{point_name}</b> еще раз."
            )
            # Мы НЕ вызываем state.clear(), бот остается в состоянии waiting_for_photos
            return
        
        await state.update_data(photos=photos_received)
        kb = [[types.KeyboardButton(text="📍 Отправить геолокацию", request_location=True)]]
        keyboard = types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)
        await message.answer("Фото приняты! 👍\nТеперь подтвердите местоположение.", reply_markup=keyboard)
        await state.set_state(Reporting.waiting_for_location)
    asyncio.create_task(process_album())


@router.message(Reporting.waiting_for_location, F.location)
async def handle_location(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    point_name = data.get("point_name")
    point_id = data.get("point_id")
    photo_file_ids = data.get("photos")
    
    agent_data = get_agent_by_telegram_id(message.from_user.id)
    if not all([agent_data, point_id, photo_file_ids]):
        await message.answer("Ошибка, не все данные собраны. Начните заново.", reply_markup=types.ReplyKeyboardRemove()); await state.clear(); return
    
    agent_db_id, agent_full_name, _ = agent_data
     # 1. Сохраняем отчет и получаем его ID
    report_id = save_report(
        user_id=agent_db_id, point_id=point_id, photo_file_ids_json=json.dumps(photo_file_ids),
        latitude=message.location.latitude, longitude=message.location.longitude
    )
    # 2. Вызываем функцию для добавления данных в Google Таблицу
    if report_id:
        add_report_to_sheet(report_id)
     
    await message.answer(f"✅ Отчет по точке <b>{point_name}</b> принят!", reply_markup=types.ReplyKeyboardRemove())
    
    # Отправка в архив (без изменений)
    caption = f"📸 **Новый фотоотчет**\n\n👤 **Агент:** {agent_full_name}\n📍 **Торговая точка:** {point_name}\n⏰ **Время:** {message.date.strftime('%Y-%m-%d %H:%M:%S')}"
    try:
        media_group = [types.InputMediaPhoto(media=file_id) for file_id in photo_file_ids]
        if media_group: media_group[0].caption = caption; await bot.send_media_group(chat_id=PHOTO_ARCHIVE_CHANNEL_ID, media=media_group)
    except Exception as e:
        logging.error(f"Не удалось отправить фото в архив: {e}")

    # --- ВОЗВРАЩАЕМ ПОЛЬЗОВАТЕЛЯ В МЕНЮ МАРШРУТА ---
    await state.clear()
    await show_schedule(message) # Вызываем функцию, чтобы показать обновленный список с галочкой