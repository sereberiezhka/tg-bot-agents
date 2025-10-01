# ui/keyboards.py (полностью обновленный)
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_keyboard(role: str):
    """Возвращает клавиатуру главного меню в зависимости от роли."""
    builder = InlineKeyboardBuilder()
    if role == 'director':
        builder.add(InlineKeyboardButton(text="📥 Загрузить расписание", callback_data="director_upload_schedule"))
        builder.add(InlineKeyboardButton(text="🔑 Создать инвайт-код", callback_data="director_create_invite"))
    elif role == 'agent':
        builder.add(InlineKeyboardButton(text="🗺️ Мой маршрут на сегодня", callback_data="agent_get_schedule"))
    
    builder.adjust(1)
    return builder.as_markup()