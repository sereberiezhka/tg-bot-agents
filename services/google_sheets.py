import gspread
import logging
from datetime import datetime, timedelta
import pytz

from config import GOOGLE_CREDS_JSON, GOOGLE_SHEET_NAME
from database import get_report_details_for_gsheet, get_daily_stats

# УКАЖИ СВОЙ ЧАСОВОЙ ПОЯС (тот же, что и в scheduler.py)
TIMEZONE = 'Asia/Almaty'

def get_worksheet(sheet_name="Журнал отчетов"):
    """Подключается к Google Sheets и возвращает нужный лист по имени."""
    try:
        gc = gspread.service_account(filename=GOOGLE_CREDS_JSON)
        spreadsheet = gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet(sheet_name)
        return worksheet
    except gspread.exceptions.WorksheetNotFound:
        logging.error(f"Лист с именем '{sheet_name}' не найден в таблице.")
        return None
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None
    
def update_daily_summary():
    """Обновляет лист 'Сводка за день' актуальными данными."""
    worksheet = get_worksheet("Сводка за день")
    if not worksheet: return

    # Получаем полную статистику по всем
    _, _, _, full_stats = get_daily_stats()

    if not full_stats:
        worksheet.clear()
        worksheet.update_cell(1, 1, "На сегодня нет данных.")
        return

    # Готовим данные для записи
    header = ["Агент", "План", "Факт", "% Выполнения", "Начало работы", "Конец работы", "Часов отработано", "Среднее время на точку (мин)"]
    rows_to_insert = [header]

    local_tz = pytz.timezone(TIMEZONE)

    for agent in full_stats:
        completion_percentage = (agent['fact'] / agent['plan']) * 100 if agent['plan'] > 0 else 0
        
        start_time_str = "-"
        end_time_str = "-"
        work_hours_str = "-"
        avg_time_per_point_str = "-"

        if agent['start_time'] and agent['end_time']:
            start_time_utc = datetime.strptime(agent['start_time'], '%Y-%m-%d %H:%M:%S')
            end_time_utc = datetime.strptime(agent['end_time'], '%Y-%m-%d %H:%M:%S')
            
            start_time_local = pytz.utc.localize(start_time_utc).astimezone(local_tz)
            end_time_local = pytz.utc.localize(end_time_utc).astimezone(local_tz)

            start_time_str = start_time_local.strftime('%H:%M:%S')
            end_time_str = end_time_local.strftime('%H:%M:%S')

            work_duration = end_time_local - start_time_local
            work_hours = work_duration.total_seconds() / 3600
            work_hours_str = f"{work_hours:.2f}"

            if agent['fact'] > 0:
                avg_minutes = (work_duration.total_seconds() / 60) / agent['fact']
                avg_time_per_point_str = f"{avg_minutes:.1f}"

        row = [
            agent['name'], agent['plan'], agent['fact'], f"{completion_percentage:.1f}%",
            start_time_str, end_time_str, work_hours_str, avg_time_per_point_str
        ]
        rows_to_insert.append(row)

    try:
        worksheet.clear()
        worksheet.update(rows_to_insert, value_input_option='USER_ENTERED')
        worksheet.format("A1:H1", {'textFormat': {'bold': True}})
        logging.info("Лист 'Сводка за день' в Google Sheets обновлен.")
    except Exception as e:
        logging.error(f"Не удалось обновить сводку в Google Sheets: {e}")

def add_report_to_sheet(report_id):
    """Добавляет строку с данными отчета в Google Таблицу."""
    worksheet = get_worksheet()
    if not worksheet:
        logging.error("Не удалось получить доступ к листу 'Журнал отчетов'.")
        return

    details = get_report_details_for_gsheet(report_id)
    if not details:
        logging.error(f"Не удалось получить детали для отчета id={report_id}.")
        return

    report_time_utc = datetime.strptime(details[0].split('.')[0], '%Y-%m-%d %H:%M:%S')
    local_tz = pytz.timezone(TIMEZONE)
    report_time_local = pytz.utc.localize(report_time_utc).astimezone(local_tz)

    date_str = report_time_local.strftime('%Y-%m-%d')
    time_str = report_time_local.strftime('%H:%M:%S')
    agent_name = details[1]
    point_name = details[2]
    parent_object = details[3]
    coords = f"{details[4]}, {details[5]}"
    # Пока не делаем ссылку на фото, просто пишем "Да"
    photos_link = "Фото в архиве" 

    row_to_insert = [date_str, time_str, agent_name, point_name, parent_object, coords, photos_link]
    
    try:
        worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        logging.info(f"Отчет id={report_id} успешно добавлен в Google Таблицу.")
    except Exception as e:
        logging.error(f"Не удалось добавить строку в Google Таблицу: {e}")