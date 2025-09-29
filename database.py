# database.py

import sqlite3
import pandas as pd
import logging
import uuid # Для генерации уникальных кодов

DATABASE_NAME = 'bot_database.db'
logging.basicConfig(level=logging.INFO)

def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()

        # Таблица пользователей (оставим как есть)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                role TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE,
                supervisor_id INTEGER,
                telegram_id INTEGER UNIQUE
            )
        """)
        # Таблица торговых точек (оставим как есть)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_points (
                point_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                parent_object TEXT
            )
        """)
        # Таблица расписаний (оставим как есть)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                point_id INTEGER NOT NULL,
                day_of_week TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (point_id) REFERENCES trade_points(point_id)
            )
        """)
        # Таблица отчетов (оставим как есть)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                report_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                point_id INTEGER NOT NULL,
                report_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                photo_file_ids TEXT,
                latitude REAL,
                longitude REAL,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (point_id) REFERENCES trade_points(point_id)
            )
        """)

        # !!! НОВАЯ ТАБЛИЦА ДЛЯ ИНВАЙТ-КОДОВ !!!
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                code_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL, -- 'agent', 'supervisor'
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        conn.commit()
    logging.info("База данных инициализирована.")

# --- Старые функции оставляем, добавляем новые ---

def get_user_by_telegram_id(telegram_id):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()

def add_user(telegram_id, full_name, role, supervisor_id=None):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO users (telegram_id, full_name, role, supervisor_id) VALUES (?, ?, ?, ?)",
                (telegram_id, full_name, role, supervisor_id)
            )
            conn.commit()
            logging.info(f"Добавлен пользователь: {full_name} ({role})")
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            logging.warning(f"Пользователь с Telegram ID {telegram_id} уже существует.")
            return None

def _get_or_create_trade_point(cursor, name, parent_object=None):
    cursor.execute("SELECT point_id FROM trade_points WHERE name = ?", (name,))
    point = cursor.fetchone()
    if point:
        return point[0]
    else:
        cursor.execute("INSERT INTO trade_points (name, parent_object) VALUES (?, ?)", (name, parent_object))
        logging.info(f"Добавлена торговая точка: {name}")
        return cursor.lastrowid

def save_schedule_from_dataframe(df: pd.DataFrame):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules")
        logging.info("Таблица schedules очищена.")
        days_of_week = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
        for index, row in df.iterrows():
            agent_full_name = row['ТМ']
            trade_point_name = row['ТТ']
            parent_object = row.get('Объект Родитель')
            cursor.execute("SELECT user_id FROM users WHERE full_name = ? AND role = 'agent'", (agent_full_name,))
            agent_db = cursor.fetchone()
            if not agent_db:
                cursor.execute("INSERT INTO users (full_name, role) VALUES (?, 'agent')", (agent_full_name,))
                agent_id = cursor.lastrowid
                logging.info(f"Автоматически добавлен агент: {agent_full_name}")
            else:
                agent_id = agent_db[0]
            point_id = _get_or_create_trade_point(cursor, trade_point_name, parent_object)
            for day in days_of_week:
                if pd.notna(row.get(day)) and row[day] == 1:
                    cursor.execute(
                        "INSERT INTO schedules (user_id, point_id, day_of_week) VALUES (?, ?, ?)",
                        (agent_id, point_id, day)
                    )
        conn.commit()
        logging.info(f"Расписание для {len(df['ТМ'].unique())} агентов успешно сохранено в базу данных.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при сохранении в БД, все изменения отменены: {e}")
        raise
    finally:
        conn.close()

def get_agent_schedule_for_day(agent_user_id, day_of_week):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tp.name, tp.parent_object
            FROM schedules s
            JOIN trade_points tp ON s.point_id = tp.point_id
            WHERE s.user_id = ? AND s.day_of_week = ?
            ORDER BY tp.name
        """, (agent_user_id, day_of_week))
        return cursor.fetchall()

def get_agent_by_telegram_id(telegram_id):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name, role FROM users WHERE telegram_id = ? AND role = 'agent'", (telegram_id,))
        return cursor.fetchone()

# --- !!! НОВЫЕ ФУНКЦИИ ДЛЯ ИНВАЙТ-КОДОВ !!! ---

def create_invite_code(role='agent'):
    """Генерирует новый инвайт-код и сохраняет в БД."""
    code = f"{role.upper()}-{uuid.uuid4().hex[:6].upper()}"
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invite_codes (code, role) VALUES (?, ?)", (code, role))
        conn.commit()
    logging.info(f"Создан инвайт-код: {code} для роли {role}")
    return code

def get_invite_code(code):
    """Проверяет инвайт-код в БД."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role, is_active FROM invite_codes WHERE code = ?", (code,))
        return cursor.fetchone() # Вернет (role, is_active) или None

def deactivate_invite_code(code):
    """Деактивирует инвайт-код после использования."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invite_codes SET is_active = FALSE WHERE code = ?", (code,))
        conn.commit()
    logging.info(f"Инвайт-код {code} деактивирован.")

def get_unregistered_agents():
    """Возвращает список агентов, у которых еще нет telegram_id."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'agent' AND telegram_id IS NULL")
        return cursor.fetchall()

def link_agent_to_telegram_id(user_id, telegram_id, full_name):
    """Привязывает telegram_id к существующему в БД агенту."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET telegram_id = ?, full_name = ? WHERE user_id = ?", (telegram_id, full_name, user_id))
        conn.commit()
    logging.info(f"Агент (user_id={user_id}) привязан к telegram_id={telegram_id}")