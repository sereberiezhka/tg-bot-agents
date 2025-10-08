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

# handlers/common.py - заменяем эту функцию

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name # Получаем имя из Telegram
    db_user = get_user_by_telegram_id(user_id)

    await message.answer("Перезагрузка меню...", reply_markup=types.ReplyKeyboardRemove())

    if user_id == DIRECTOR_ID and not db_user:
        add_user(user_id, user_full_name, 'director')
        db_user = get_user_by_telegram_id(user_id)

    if db_user:
        # Теперь db_user это кортеж (user_id, full_name, role, ...)
        # Берем ФИО из базы данных, оно может быть более полным, чем в Telegram
        db_full_name = db_user[1] 
        role = db_user[2]
        
        # --- НОВОЕ ПРИВЕТСТВИЕ ---
        welcome_text = (
            f"Здравствуйте, <b>{db_full_name}</b>!\n"
            f"Ваша роль: <b>{role.capitalize()}</b>"
        )
        await message.answer(welcome_text, reply_markup=main_menu_keyboard(role))
    else:
        await message.answer(f"Добро пожаловать, {user_full_name}! 👋\nДля начала работы введите свой инвайт-код.")
        await state.set_state(Registration.waiting_for_code)

# Обновляем process_invite_code, чтобы он понимал разные роли
@router.message(Registration.waiting_for_code)
async def process_invite_code(message: types.Message, state: FSMContext):
    code = message.text.strip()
    code_data = get_invite_code(code)
    
    if not code_data or not code_data[1]:
        await message.answer("Неверный код."); return

    role = code_data[0]
    await state.update_data(code=code, role=role)

    if role == 'agent':
        await message.answer("Код принят! Введите ФИО, как в расписании.")
        await state.set_state(Registration.waiting_for_fio)
    elif role == 'supervisor':
        # Супервайзеру не нужно выбирать ФИО, он регистрируется под именем из Telegram
        add_user(message.from_user.id, message.from_user.full_name, 'supervisor')
        deactivate_invite_code(code)
        await message.answer("✅ Регистрация супервайзера успешно завершена!", reply_markup=main_menu_keyboard('supervisor'))
        await state.clear()

@router.message(Registration.waiting_for_fio)
async def process_fio(message: types.Message, state: FSMContext):
    fio = message.text.strip()
    agent_user_id = find_unregistered_agent_by_name(fio)
    
    if agent_user_id:
        state_data = await state.get_data()
        link_agent_to_telegram_id(agent_user_id, message.from_user.id)
        deactivate_invite_code(state_data.get('code'))

        await message.answer("✅ Регистрация успешно завершена!", reply_markup=main_menu_keyboard('agent'))
        await state.clear()
    else:
        await message.answer("❌ Агент с таким ФИО не найден. Проверьте правильность написания и попробуйте еще раз.")

# Этот хэндлер будет ловить все нажатия на кнопки "Назад в меню"
@router.callback_query(F.data.startswith("start_menu_"))
async def back_to_main_menu_handler(callback: types.CallbackQuery, state: FSMContext):
    await state.clear() # Очищаем состояние на всякий случай
    role = callback.data.split("_")[2]
    
    # Редактируем сообщение, убирая старые кнопки и текст
    await callback.message.edit_text(
        f"Главное меню. Ваша роль: {role.capitalize()}",
        reply_markup=main_menu_keyboard(role)
    )
    await callback.answer()