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
from ui.keyboards import director_menu_keyboard, agent_menu_keyboard

router = Router()

class Registration(StatesGroup):
    waiting_for_code = State()
    waiting_for_fio = State() # Новое состояние для ожидания ФИО

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

    # Сохраняем код, он нам еще понадобится
    await state.update_data(code=code)
    await message.answer(
        "Код принят! ✅\n\n"
        "Теперь, пожалуйста, введите свои <b>Фамилию Имя Отчество</b>.\n"
        "<i>(Важно: введите их точно так же, как они указаны в рабочем расписании)</i>"
    )
    await state.set_state(Registration.waiting_for_fio)

@router.message(Registration.waiting_for_fio)
async def process_fio(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    
    # Ищем агента в БД по введенному ФИО
    agent_user_id = find_unregistered_agent_by_name(fio)
    
    if agent_user_id:
        # Агент найден! Завершаем регистрацию.
        telegram_id = message.from_user.id
        link_agent_to_telegram_id(agent_user_id, telegram_id)
        
        # Деактивируем инвайт-код
        state_data = await state.get_data()
        deactivate_invite_code(state_data.get('code'))

        await message.answer("✅ **Регистрация успешно завершена!**\n\nТеперь вы можете пользоваться меню агента.", reply_markup=agent_menu_keyboard())
        await state.clear()
    else:
        # Агент не найден
        await message.answer(
            "❌ Агент с таким ФИО не найден среди незарегистрированных.\n\n"
            "Пожалуйста, проверьте правильность написания и попробуйте еще раз. "
            "Обратите внимание на заглавные буквы и пробелы."
        )