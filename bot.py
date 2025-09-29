# bot.py

import asyncio
import logging
import pandas as pd
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import BOT_TOKEN, DIRECTOR_ID
# Импортируем все наши новые функции
from database import (
    init_db, get_user_by_telegram_id, add_user, save_schedule_from_dataframe, 
    get_agent_by_telegram_id, get_agent_schedule_for_day, create_invite_code, 
    get_invite_code, deactivate_invite_code, get_unregistered_agents, 
    link_agent_to_telegram_id
)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Создаем "состояния" для процесса регистрации
class Registration(StatesGroup):
    waiting_for_code = State()
    choosing_profile = State()

# --- МЕНЮ И КЛАВИАТУРЫ ---

def director_menu_keyboard():
    kb = [
        [types.KeyboardButton(text="Загрузить расписание")],
        [types.KeyboardButton(text="Создать инвайт-код")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def agent_menu_keyboard():
    kb = [[types.KeyboardButton(text="Мой маршрут на сегодня")]]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- ХЭНДЛЕРЫ ДЛЯ ДИРЕКТОРА ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear() # Сбрасываем состояния при старте
    user_id = message.from_user.id
    db_user = get_user_by_telegram_id(user_id)

    if user_id == DIRECTOR_ID and not db_user:
        add_user(user_id, message.from_user.full_name, 'director')
        db_user = get_user_by_telegram_id(user_id)

    if db_user:
        role = db_user[2] # Индекс роли в кортеже из БД
        if role == 'director':
            await message.answer(f"С возвращением, Директор!", reply_markup=director_menu_keyboard())
        elif role == 'agent':
            await message.answer(f"Привет, Агент!", reply_markup=agent_menu_keyboard())
    else:
        await message.answer(f"Привет, {message.from_user.full_name}! 👋\nДля начала работы введите свой инвайт-код.")
        await state.set_state(Registration.waiting_for_code)

@dp.message(F.text == "Создать инвайт-код", F.from_user.id == DIRECTOR_ID)
async def create_invite_handler(message: types.Message):
    # Пока создаем коды только для агентов
    new_code = create_invite_code(role='agent')
    await message.answer(
        f"Создан новый инвайт-код для Агента:\n\n"
        f"`{new_code}`\n\n"
        f"Отправьте этот код новому сотруднику. Он действует один раз.",
        parse_mode="Markdown"
    )

@dp.message(F.text == "Загрузить расписание", F.from_user.id == DIRECTOR_ID)
async def ask_for_schedule_file(message: types.Message):
    await message.answer("Пожалуйста, отправьте мне Excel-файл с расписанием.")

@dp.message(F.document, F.from_user.id == DIRECTOR_ID)
async def handle_schedule_file(message: types.Message):
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
        save_schedule_from_dataframe(df)
        num_agents = len(df['ТМ'].unique())
        await message.answer(f"✅ Расписание успешно сохранено в базу!\nУникальных агентов: {num_agents}")
    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"Ой, произошла ошибка при обработке файла: {e}")

# --- ХЭНДЛЕРЫ ДЛЯ АГЕНТОВ ---

@dp.message(F.text == "Мой маршрут на сегодня")
async def get_my_schedule(message: types.Message):
    agent_data = get_agent_by_telegram_id(message.from_user.id)
    if not agent_data:
        await message.answer("Ваш профиль не найден. Попробуйте /start.")
        return
    
    agent_db_id, agent_full_name, _ = agent_data
    current_day_num = pd.Timestamp.now().weekday()
    day_mapping = {0: 'ПН', 1: 'ВТ', 2: 'СР', 3: 'ЧТ', 4: 'ПТ', 5: 'СБ', 6: 'ВС'}
    current_day = day_mapping.get(current_day_num, 'Н/Д')

    if current_day == 'ВС':
        await message.answer("Сегодня воскресенье, отдыхай! 🏖️")
        return

    schedule = get_agent_schedule_for_day(agent_db_id, current_day)
    if not schedule:
        await message.answer(f"На сегодня ({current_day}) у тебя нет задач.")
        return
    
    response_text = f"Твой маршрут на **{current_day}**:\n\n"
    for i, (point_name, parent_object) in enumerate(schedule, 1):
        response_text += f"{i}. **{point_name}** ({parent_object or 'район не указан'})\n"
    await message.answer(response_text)


# --- ХЭНДЛЕРЫ ДЛЯ РЕГИСТРАЦИИ ---

@dp.message(Registration.waiting_for_code)
async def process_invite_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    code_data = get_invite_code(code)
    
    if not code_data or not code_data[1]: # Если кода нет или он неактивен
        await message.answer("Неверный или уже использованный инвайт-код. Попробуйте еще раз или запросите новый.")
        return

    # Код верный, теперь просим выбрать профиль
    unregistered_agents = get_unregistered_agents()
    if not unregistered_agents:
        await message.answer("Все агенты из расписания уже зарегистрированы. Обратитесь к Директору.")
        await state.clear()
        return

    # Сохраняем telegram_id и full_name для следующего шага
    await state.update_data(
        telegram_id=message.from_user.id,
        telegram_name=message.from_user.full_name,
        code=code
    )

    # Создаем клавиатуру с именами
    builder = InlineKeyboardBuilder()
    for user_id, full_name in unregistered_agents:
        builder.add(InlineKeyboardButton(text=full_name, callback_data=f"link_profile_{user_id}"))
    builder.adjust(1) # По одной кнопке в строке

    await message.answer("Отлично! Теперь подтвердите, кто вы, выбрав свое имя из списка:", reply_markup=builder.as_markup())
    await state.set_state(Registration.choosing_profile)

@dp.callback_query(F.data.startswith("link_profile_"), Registration.choosing_profile)
async def link_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    user_db_id = int(callback.data.split("_")[2])
    
    # Получаем данные, которые сохранили на прошлом шаге
    state_data = await state.get_data()
    telegram_id = state_data.get('telegram_id')
    telegram_name = state_data.get('telegram_name')
    code = state_data.get('code')

    # Привязываем telegram_id к профилю в БД
    link_agent_to_telegram_id(user_db_id, telegram_id, telegram_name)
    
    # Деактивируем код
    deactivate_invite_code(code)

    await callback.message.edit_text("✅ **Регистрация успешно завершена!**")
    await callback.message.answer("Теперь вы можете пользоваться меню агента.", reply_markup=agent_menu_keyboard())
    
    await state.clear()


async def main():
    init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())