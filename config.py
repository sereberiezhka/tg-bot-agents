# config.py
import os
from dotenv import load_dotenv

load_dotenv()  # подтягивает переменные из файла .env

BOT_TOKEN = os.getenv("BOT_TOKEN")

# ID канала для архива фото (должен начинаться с -100)
PHOTO_ARCHIVE_CHANNEL_ID = int(os.getenv("PHOTO_ARCHIVE_CHANNEL_ID", "-1003129591507"))

# Название файла с ключами от Google API
GOOGLE_CREDS_JSON = os.getenv("GOOGLE_CREDS_JSON", "google_creds.json")

# Название твоей Google Таблицы
GOOGLE_SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Отчеты по агентам")

# ID администратора (Директора)
DIRECTOR_ID = int(os.getenv("DIRECTOR_ID", "1669140535"))

# Ссылка на Google Таблицу
GOOGLE_SHEET_URL = os.getenv("GOOGLE_SHEET_URL", "")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Проверь файл .env")