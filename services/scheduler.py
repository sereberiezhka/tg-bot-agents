# services/scheduler.py

import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime

from config import DIRECTOR_ID
from database import get_daily_stats
from services.google_sheets import update_daily_summary

# Например: 'Europe/Moscow', 'Asia/Almaty', 'Asia/Yekaterinburg'
TIMEZONE = 'Asia/Almaty'

async def send_daily_report(bot: Bot, report_type: str, supervisor_db_id=None):
    """Формирует и отправляет отчет. Если есть supervisor_db_id - только ему и по его команде."""
    
    # 1. Получаем РАСШИРЕННЫЕ данные из get_daily_stats (теперь она возвращает 4 значения)
    # Нам не нужны full_stats здесь, поэтому используем _ для пропуска
    total_plan, total_fact, laggards, _ = get_daily_stats(supervisor_db_id)
    
    report_date = datetime.now().strftime('%d.%m.%Y')

    # 2. Логика формирования текста остается такой же, как ты и написал (она правильная)
    if total_plan == 0:
        text = f"📈 <b>{report_type} отчет за {report_date}</b>\n\nНа сегодня нет запланированных визитов."
    else:
        completion_percentage = (total_fact / total_plan) * 100 if total_plan > 0 else 0
        text = (
            f"📈 <b>{report_type} отчет за {report_date}</b>\n\n"
            f"🔹 <b>Общий прогресс:</b> {total_fact} из {total_plan} ({completion_percentage:.1f}%)\n\n"
        )
        if laggards:
            text += "🔻 <b>Отстающие агенты:</b>\n"
            for agent in laggards:
                text += f"— <i>{agent['name']}</i>: {agent['fact']} из {agent['plan']}\n"
        else:
            text += "✅ <b>Все агенты выполнили план!</b>"
    
    # 3. Определяем, кому отправлять. Важно: для супервайзера мы используем telegram_id, а не user_id из базы.
    # Но так как наш хэндлер супервайзера передает user_id, мы пока оставим как есть,
    # но в будущем это надо будет улучшить. Пока для Директора это будет работать.
    chat_id_to_send = supervisor_db_id if supervisor_db_id else DIRECTOR_ID
    
    try:
        await bot.send_message(chat_id=chat_id_to_send, text=text)
        logging.info(f"Отправлен {report_type} отчет.")
    except Exception as e:
        logging.error(f"Не удалось отправить {report_type} отчет: {e}")

    # 4. НОВЫЙ БЛОК: Обновляем Google-сводку, если это итоговый отчет для Директора
    if report_type == 'Итоговый' and not supervisor_db_id:
        try:
            update_daily_summary()
        except Exception as e:
            logging.error(f"Ошибка при обновлении сводки Google Sheets из планировщика: {e}")

         


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
        hour=21,
        minute=43,
        kwargs={'bot': bot, 'report_type': 'Итоговый'}
    )

    scheduler.start()
    logging.info("Планировщик задач запущен.")