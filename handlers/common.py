# handlers/common.py (полностью обновленный)
from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import DIRECTOR_ID
from database import (
    get_user_by_telegram_id, add_user, get_invite_code, 
    deactivate_invite_code, find_unregistered_agent_by_name, link_agent_to_telegram_id
)
from ui.keyboards import main_menu_keyboard

router = Router()

class Registration(StatesGroup):
    waiting_for_code = State()
    waiting_for_fio = State()

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    db_user = get_user_by_telegram_id(user_id)

    # Принудительно убираем старую Reply-клавиатуру
    await message.answer("Перезагрузка меню...", reply_markup=types.ReplyKeyboardRemove())

    if user_id == DIRECTOR_ID and not db_user:
        add_user(user_id, message.from_user.full_name, 'director')
        db_user = get_user_by_telegram_id(user_id)

    if db_user:
        role = db_user[2]
        await message.answer(f"Добро пожаловать! Ваша роль: {role.capitalize()}", reply_markup=main_menu_keyboard(role))
    else:
        await message.answer(f"Привет, {message.from_user.full_name}! 👋\nДля начала работы введите свой инвайт-код.")
        await state.set_state(Registration.waiting_for_code)

@router.message(Registration.waiting_for_code)
async def process_invite_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    code_data = get_invite_code(code)
    
    if not code_data or not code_data[1]:
        await message.answer("Неверный или уже использованный инвайт-код."); return

    await state.update_data(code=code)
    await message.answer("Код принят! ✅\n\nТеперь, пожалуйста, введите свои <b>Фамилию Имя Отчество</b>.")
    await state.set_state(Registration.waiting_for_fio)

@router.message(Registration.waiting_for_fio)
async def process_fio(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    agent_user_id = find_unregistered_agent_by_name(fio)
    
    if agent_user_id:
        state_data = await state.get_data()
        link_agent_to_telegram_id(agent_user_id, message.from_user.id)
        deactivate_invite_code(state_data.get('code'))

        await message.answer("✅ **Регистрация успешно завершена!**", reply_markup=main_menu_keyboard('agent'))
        await state.clear()
    else:
        await message.answer("❌ Агент с таким ФИО не найден. Проверьте правильность написания и попробуйте еще раз.")