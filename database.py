# database.py

import sqlite3
import pandas as pd
import logging

DATABASE_NAME = 'bot_database.db'
logging.basicConfig(level=logging.INFO)

def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()

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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trade_points (
                point_id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                parent_object TEXT
            )
        """)

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
        
        conn.commit()
    logging.info("База данных инициализирована.")


def get_user_by_telegram_id(telegram_id):
    """Возвращает пользователя по его Telegram ID."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()

def add_user(telegram_id, full_name, role, supervisor_id=None):
    """Добавляет нового пользователя."""
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
    """
    (Вспомогательная функция) Получает ID торговой точки или создает новую.
    Работает с переданным курсором, не создавая нового подключения.
    """
    cursor.execute("SELECT point_id FROM trade_points WHERE name = ?", (name,))
    point = cursor.fetchone()
    if point:
        return point[0]
    else:
        cursor.execute("INSERT INTO trade_points (name, parent_object) VALUES (?, ?)", (name, parent_object))
        logging.info(f"Добавлена торговая точка: {name}")
        return cursor.lastrowid


def save_schedule_from_dataframe(df: pd.DataFrame):
    """
    Сохраняет расписание из DataFrame в базу данных в рамках ОДНОЙ ТРАНЗАКЦИИ.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    
    try:
        # 1. Очищаем старое расписание
        cursor.execute("DELETE FROM schedules")
        logging.info("Таблица schedules очищена.")

        days_of_week = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']

        for index, row in df.iterrows():
            agent_full_name = row['ТМ']
            trade_point_name = row['ТТ']
            parent_object = row.get('Объект Родитель')

            # 2. Получаем или создаем пользователя (агента)
            cursor.execute("SELECT user_id FROM users WHERE full_name = ? AND role = 'agent'", (agent_full_name,))
            agent_db = cursor.fetchone()
            if not agent_db:
                cursor.execute("INSERT INTO users (full_name, role) VALUES (?, 'agent')", (agent_full_name,))
                agent_id = cursor.lastrowid
                logging.info(f"Автоматически добавлен агент: {agent_full_name}")
            else:
                agent_id = agent_db[0]
            
            # 3. Получаем или создаем торговую точку
            point_id = _get_or_create_trade_point(cursor, trade_point_name, parent_object)
            
            # 4. Сохраняем расписание для каждого дня
            for day in days_of_week:
                if pd.notna(row.get(day)) and row[day] == 1:
                    cursor.execute(
                        "INSERT INTO schedules (user_id, point_id, day_of_week) VALUES (?, ?, ?)",
                        (agent_id, point_id, day)
                    )
        
        # 5. Если все прошло без ошибок, сохраняем все изменения
        conn.commit()
        logging.info(f"Расписание для {len(df['ТМ'].unique())} агентов успешно сохранено в базу данных.")

    except Exception as e:
        # 6. Если произошла ошибка, откатываем все изменения
        conn.rollback()
        logging.error(f"Ошибка при сохранении в БД, все изменения отменены: {e}")
        raise # Пробрасываем ошибку дальше, чтобы бот мог на нее отреагировать
    finally:
        # 7. В любом случае закрываем подключение
        conn.close()


def get_agent_schedule_for_day(agent_user_id, day_of_week):
    """
    Возвращает список торговых точек для агента на определенный день.
    """
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
    """Возвращает ID агента по его Telegram ID."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name, role FROM users WHERE telegram_id = ? AND role = 'agent'", (telegram_id,))
        return cursor.fetchone()