# ui/keyboards.py

from aiogram import types

def director_menu_keyboard():
    """Возвращает клавиатуру для меню Директора."""
    kb = [
        [types.KeyboardButton(text="Загрузить расписание")],
        [types.KeyboardButton(text="Создать инвайт-код")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def agent_menu_keyboard():
    """Возвращает клавиатуру для меню Агента."""
    kb = [[types.KeyboardButton(text="Мой маршрут на сегодня")]]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)