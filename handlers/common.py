# handlers/common.py
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import DIRECTOR_ID
from database import (
    get_user_by_telegram_id, add_user, get_invite_code, 
    deactivate_invite_code, get_unregistered_agents, link_agent_to_telegram_id
)
from ui.keyboards import director_menu_keyboard, agent_menu_keyboard

router = Router()

class Registration(StatesGroup):
    waiting_for_code = State()
    choosing_profile = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    db_user = get_user_by_telegram_id(user_id)

    if user_id == DIRECTOR_ID and not db_user:
        add_user(user_id, message.from_user.full_name, 'director')
        db_user = get_user_by_telegram_id(user_id)

    if db_user:
        role = db_user[2]
        if role == 'director':
            await message.answer("С возвращением, Директор!", reply_markup=director_menu_keyboard())
        elif role == 'agent':
            await message.answer("Привет, Агент!", reply_markup=agent_menu_keyboard())
    else:
        await message.answer(f"Привет, {message.from_user.full_name}! 👋\nДля начала работы введите свой инвайт-код.")
        await state.set_state(Registration.waiting_for_code)

@router.message(Registration.waiting_for_code)
async def process_invite_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    code_data = get_invite_code(code)
    
    if not code_data or not code_data[1]:
        await message.answer("Неверный или уже использованный инвайт-код. Попробуйте еще раз.")
        return

    unregistered_agents = get_unregistered_agents()
    if not unregistered_agents:
        await message.answer("Все агенты из расписания уже зарегистрированы. Обратитесь к Директору.")
        await state.clear()
        return

    await state.update_data(
        telegram_id=message.from_user.id,
        telegram_name=message.from_user.full_name,
        code=code
    )

    builder = InlineKeyboardBuilder()
    for user_id, full_name in unregistered_agents:
        builder.add(InlineKeyboardButton(text=full_name, callback_data=f"link_profile_{user_id}"))
    builder.adjust(1)

    await message.answer("Отлично! Теперь выберите свое имя из списка:", reply_markup=builder.as_markup())
    await state.set_state(Registration.choosing_profile)

@router.callback_query(F.data.startswith("link_profile_"), Registration.choosing_profile)
async def link_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    user_db_id = int(callback.data.split("_")[2])
    state_data = await state.get_data()
    telegram_id = state_data.get('telegram_id')
    telegram_name = state_data.get('telegram_name')
    code = state_data.get('code')

    link_agent_to_telegram_id(user_db_id, telegram_id, telegram_name)
    deactivate_invite_code(code)

    await callback.message.edit_text("✅ **Регистрация успешно завершена!**")
    await callback.message.answer("Теперь вы можете пользоваться меню агента.", reply_markup=agent_menu_keyboard())
    await state.clear()