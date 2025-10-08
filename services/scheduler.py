# services/scheduler.py

import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

from config import DIRECTOR_ID
from database import get_daily_stats

# Например: 'Europe/Moscow', 'Asia/Almaty', 'Asia/Yekaterinburg'
TIMEZONE = 'Asia/Almaty'

async def send_daily_report(bot: Bot, report_type: str):
    """Формирует и отправляет ежедневный отчет Директору."""
    
    total_plan, total_fact, laggards = get_daily_stats()

    if total_plan == 0:
        text = f"📈 **{report_type} отчет**\n\nНа сегодня нет запланированных визитов."
    else:
        completion_percentage = (total_fact / total_plan) * 100 if total_plan > 0 else 0
        text = (
            f"📈 **{report_type} отчет** за {datetime.now().strftime('%d.%m.%Y')}\n\n"
            f"🔹 **Общий прогресс:** {total_fact} из {total_plan} ({completion_percentage:.1f}%)\n\n"
        )
        if laggards:
            text += "🔻 **Отстающие агенты:**\n"
            for agent in laggards:
                text += f"— {agent['name']}: {agent['fact']} из {agent['plan']}\n"
        else:
            text += "✅ **Все агенты выполнили план!**"
            
    try:
        await bot.send_message(chat_id=DIRECTOR_ID, text=text)
        logging.info(f"Отправлен {report_type} отчет Директору.")
    except Exception as e:
        logging.error(f"Не удалось отправить {report_type} отчет Директору: {e}")


def setup_scheduler(bot: Bot):
    """Настраивает и запускает задачи по расписанию."""
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Добавляем задачу для утреннего отчета (в 11:00)
    scheduler.add_job(
        send_daily_report,
        trigger='cron',
        hour=11,
        minute=0,
        kwargs={'bot': bot, 'report_type': 'Промежуточный'}
    )
    
    # Добавляем задачу для вечернего отчета (в 19:00)
    scheduler.add_job(
        send_daily_report,
        trigger='cron',
        hour=17,
        minute=23,
        kwargs={'bot': bot, 'report_type': 'Итоговый'}
    )

    scheduler.start()
    logging.info("Планировщик задач запущен.")