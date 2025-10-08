# ui/keyboards.py (полностью обновленный)
from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_keyboard(role: str):
    """Возвращает клавиатуру главного меню в зависимости от роли."""
    builder = InlineKeyboardBuilder()
    if role == 'director':
        builder.add(InlineKeyboardButton(text="📥 Загрузить расписание", callback_data="director_upload_schedule"))
        builder.add(InlineKeyboardButton(text="🔑 Создать инвайт-код", callback_data="director_create_invite"))
        builder.add(InlineKeyboardButton(text="📊 Отчеты (Google Sheets)", callback_data="director_get_report_link"))
    elif role == 'agent':
        builder.add(InlineKeyboardButton(text="🗺️ Мой маршрут на сегодня", callback_data="agent_get_schedule"))
    
    builder.adjust(1)
    return builder.as_markup()

def back_to_main_menu_keyboard(role: str):
    """Возвращает клавиатуру с одной кнопкой "Назад в меню"."""
    builder = InlineKeyboardBuilder()
    # Мы используем callback_data 'start_menu', чтобы вызвать главное меню
    builder.add(InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data=f"start_menu_{role}"))
    return builder.as_markup()
