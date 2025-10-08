# handlers/supervisor.py

from aiogram import Router, F, types, Bot
from services.scheduler import send_daily_report # Мы будем вызывать отчет вручную

router = Router()
# Фильтр, чтобы эти хэндлеры работали только для роли 'supervisor'
router.callback_query.filter(lambda c: get_user_by_telegram_id(c.from_user.id) and get_user_by_telegram_id(c.from_user.id)[2] == 'supervisor')

from database import get_user_by_telegram_id # Импортируем здесь, чтобы избежать циклического импорта

@router.callback_query(F.data == "supervisor_get_report")
async def get_supervisor_report(callback: types.CallbackQuery, bot: Bot):
    # Вызываем ту же функцию, что и планировщик, но с ID супервайзера
    await send_daily_report(bot, "Отчет по вашей команде", supervisor_id=callback.from_user.id)
    await callback.answer("Отчет формируется...")

@router.callback_query(F.data == "supervisor_get_gsheet")
async def get_supervisor_gsheet(callback: types.CallbackQuery):
    # В будущем здесь можно будет генерировать ссылку на отфильтрованный лист
    await callback.answer("Эта функция в разработке.", show_alert=True)