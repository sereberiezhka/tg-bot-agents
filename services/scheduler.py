# services/scheduler.py (полностью исправленный)

import logging
from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, date, timedelta

from config import DIRECTOR_ID
from database import get_daily_stats
from services.google_sheets import update_daily_summary, generate_period_report

TIMEZONE = 'Asia/Almaty'

# --- ФУНКЦИИ-ОБЕРТКИ для отчетов ---
# Мы вынесли их из setup_scheduler, чтобы их можно было вызывать для теста

def run_weekly_report():
    """Запускает генерацию отчета за текущую неделю."""
    logging.info("Запускаю генерацию еженедельного отчета...")
    today = date.today()
    # weekday() Понедельник=0, Воскресенье=6
    start_of_week = today - timedelta(days=today.weekday())
    generate_period_report("Отчет за неделю", start_of_week, today)

def run_monthly_report():
    """Запускает генерацию отчета за текущий месяц."""
    logging.info("Запускаю генерацию ежемесячного отчета...")
    today = date.today()
    start_of_month = today.replace(day=1)
    generate_period_report("Отчет за месяц", start_of_month, today)


# --- ОСНОВНЫЕ ФУНКЦИИ ПЛАНИРОВЩИКА ---

async def send_daily_report(bot: Bot, report_type: str, supervisor_db_id=None):
    total_plan, total_fact, laggards, _ = get_daily_stats(supervisor_db_id)
    report_date = datetime.now().strftime('%d.%m.%Y')
    
    if total_plan == 0:
        text = f"📈 <b>{report_type} отчет за {report_date}</b>\n\nНа сегодня нет запланированных визитов."
    else:
        completion_percentage = (total_fact / total_plan) * 100 if total_plan > 0 else 0
        text = (f"📈 <b>{report_type} отчет за {report_date}</b>\n\n"
                f"🔹 <b>Общий прогресс:</b> {total_fact} из {total_plan} ({completion_percentage:.1f}%)\n\n")
        if laggards:
            text += "🔻 <b>Отстающие агенты:</b>\n"
            for agent in laggards:
                text += f"— <i>{agent['name']}</i>: {agent['fact']} из {agent['plan']}\n"
        else:
            text += "✅ <b>Все агенты выполнили план!</b>"
    
    chat_id_to_send = supervisor_db_id if supervisor_db_id else DIRECTOR_ID
    try:
        await bot.send_message(chat_id=chat_id_to_send, text=text)
        logging.info(f"Отправлен {report_type} отчет.")
    except Exception as e:
        logging.error(f"Не удалось отправить {report_type} отчет: {e}")

    if report_type == 'Итоговый' and not supervisor_db_id:
        try:
            update_daily_summary()
        except Exception as e:
            logging.error(f"Ошибка при обновлении сводки Google Sheets: {e}")

def setup_scheduler(bot: Bot):
    scheduler = AsyncIOScheduler(timezone=TIMEZONE)

    # Ежедневные отчеты
    scheduler.add_job(send_daily_report, trigger='cron', hour=11, minute=0, kwargs={'bot': bot, 'report_type': 'Промежуточный'})
    scheduler.add_job(send_daily_report, trigger='cron', hour=22, minute=43, kwargs={'bot': bot, 'report_type': 'Итоговый'})

    # Еженедельный отчет (теперь вызываем функцию, которая определена снаружи)
    scheduler.add_job(run_weekly_report, trigger='cron', day_of_week='sat', hour=20, minute=0)

    # Ежемесячный отчет
    scheduler.add_job(run_monthly_report, trigger='cron', day='last', hour=20, minute=5)
    
    scheduler.start()
    logging.info("Планировщик задач запущен с 4 задачами (дневные, недельная, месячная).")

    # --- ТЕСТОВЫЙ ЗАПУСК ---
    # Если нужно протестировать прямо сейчас - раскомментируй эти строки
    #logging.info("Запускаю тестовую генерацию отчетов...")
    #run_weekly_report()
    #run_monthly_report()
    # -----------------------