import gspread
import logging
from datetime import datetime, timedelta
import pytz
from datetime import date, timedelta

from config import GOOGLE_CREDS_JSON, GOOGLE_SHEET_NAME
from database import get_report_details_for_gsheet, get_daily_stats, get_stats_for_period

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
    worksheet = get_worksheet("Журнал отчетов")
    if not worksheet:
        logging.error("Не удалось добавить в журнал: лист 'Журнал отчетов' не найден.")
        return

    details = get_report_details_for_gsheet(report_id)
    if not details:
        logging.error(f"Не удалось получить детали для отчета id={report_id}.")
        return

    # Теперь мы получаем 7 значений, включая ссылку
    report_time_utc_str, agent_name, point_name, parent_object, lat, lon, archive_link = details
    
    report_time_utc = datetime.strptime(report_time_utc_str.split('.')[0], '%Y-%m-%d %H:%M:%S')
    local_tz = pytz.timezone(TIMEZONE)
    report_time_local = pytz.utc.localize(report_time_utc).astimezone(local_tz)

    date_str = report_time_local.strftime('%Y-%m-%d')
    time_str = report_time_local.strftime('%H:%M:%S')
    coords = f"{lat}, {lon}"

    # --- НОВАЯ ЛОГИКА ДЛЯ ССЫЛКИ ---
    # Если ссылка есть, создаем формулу HYPERLINK, если нет - пишем "Нет фото"
    if archive_link:
        photos_cell_value = f'=HYPERLINK("{archive_link}"; "Открыть фото")'
    else:
        photos_cell_value = "Нет фото в архиве"
    # --------------------------------

    row_to_insert = [date_str, time_str, agent_name, point_name, parent_object, coords, photos_cell_value]
    
    try:
        worksheet.append_row(row_to_insert, value_input_option='USER_ENTERED')
        logging.info(f"Отчет id={report_id} успешно добавлен в Google Таблицу.")
    except Exception as e:
        logging.error(f"Не удалось добавить строку в Google Таблицу: {e}")

# services/google_sheets.py - заменяем эту функцию

def generate_period_report(sheet_name: str, start_date: date, end_date: date):
    """Генерирует и записывает в Google Таблицу сводный отчет за период."""
    worksheet = get_worksheet(sheet_name)
    if not worksheet:
        logging.error(f"Не удалось сгенерировать отчет: лист '{sheet_name}' не найден.")
        return

    stats = get_stats_for_period(start_date, end_date)

    if not stats:
        worksheet.clear()
        worksheet.update_cell(1, 1, f"Нет данных за период с {start_date.strftime('%d.%m')} по {end_date.strftime('%d.%m')}.")
        return

    header = ["Агент", "Всего посещений", "Всего часов отработано", "Среднее время на точку (мин)"]
    rows_to_insert = [header]
    
    for agent in stats:
        total_hours = agent.get('duration_seconds', 0) / 3600
        total_visits = agent.get('visits', 0)
        
        work_hours_str = f"{total_hours:.2f}"
        avg_time_per_point_str = "-"

        if total_visits > 0 and total_hours > 0:
            avg_minutes = (agent.get('duration_seconds', 0) / 60) / total_visits
            avg_time_per_point_str = f"{avg_minutes:.1f}"

        row = [agent['name'], total_visits, work_hours_str, avg_time_per_point_str]
        rows_to_insert.append(row)

    try:
        worksheet.clear()
        worksheet.update(rows_to_insert, value_input_option='USER_ENTERED')
        worksheet.format(f"A1:D1", {'textFormat': {'bold': True}})
        logging.info(f"Отчет '{sheet_name}' успешно сгенерирован.")
    except Exception as e:
        logging.error(f"Не удалось обновить лист '{sheet_name}': {e}")