# handlers/agent.py
import pandas as pd
from aiogram import Router, F, types

from database import get_agent_by_telegram_id, get_agent_schedule_for_day

router = Router()
# Здесь можно добавить фильтр по роли 'agent', но пока для простоты оставим так

@router.message(F.text == "Мой маршрут на сегодня")
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