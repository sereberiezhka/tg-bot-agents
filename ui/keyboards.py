# ui/keyboards.py (обновленный)

from aiogram.types import InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def main_menu_keyboard(role: str):
    builder = InlineKeyboardBuilder()
    if role == 'director':
        builder.add(InlineKeyboardButton(text="📥 Загрузить расписание", callback_data="director_upload_schedule"))
        builder.add(InlineKeyboardButton(text="🔑 Создать инвайт-код", callback_data="director_create_invite"))
        builder.add(InlineKeyboardButton(text="👨‍💼 Управление персоналом", callback_data="director_manage_staff"))
        builder.add(InlineKeyboardButton(text="📊 Отчеты (Google Sheets)", callback_data="director_get_report_link"))
    elif role == 'supervisor':
        builder.add(InlineKeyboardButton(text="📈 Моя команда: отчет", callback_data="supervisor_get_report"))
        builder.add(InlineKeyboardButton(text="📊 Моя команда: Google Sheets", callback_data="supervisor_get_gsheet"))
    elif role == 'agent':
        builder.add(InlineKeyboardButton(text="🗺️ Мой маршрут на сегодня", callback_data="agent_get_schedule"))
    
    builder.adjust(1)
    return builder.as_markup()

def back_to_main_menu_keyboard(role: str):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="⬅️ Назад в главное меню", callback_data=f"start_menu_{role}"))
    return builder.as_markup()

# Новая клавиатура для выбора типа инвайт-кода
def invite_options_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="Инвайт для Агента", callback_data="create_invite_agent"))
    builder.add(InlineKeyboardButton(text="Инвайт для Супервайзера", callback_data="create_invite_supervisor"))
    builder.add(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="start_menu_director"))
    builder.adjust(1)
    return builder.as_markup()