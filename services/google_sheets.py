import gspread
import logging
from datetime import datetime
import pytz

from config import GOOGLE_CREDS_JSON, GOOGLE_SHEET_NAME
from database import get_report_details_for_gsheet

# УКАЖИ СВОЙ ЧАСОВОЙ ПОЯС (тот же, что и в scheduler.py)
TIMEZONE = 'Asia/Almaty'

def get_worksheet():
    """Подключается к Google Sheets и возвращает нужный лист."""
    try:
        gc = gspread.service_account(filename=GOOGLE_CREDS_JSON)
        spreadsheet = gc.open(GOOGLE_SHEET_NAME)
        worksheet = spreadsheet.worksheet("Журнал отчетов")
        return worksheet
    except Exception as e:
        logging.error(f"Ошибка подключения к Google Sheets: {e}")
        return None

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