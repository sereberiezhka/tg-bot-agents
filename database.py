# database.py

import sqlite3
import pandas as pd
import logging

DATABASE_NAME = 'bot_database.db'
logging.basicConfig(level=logging.INFO)

def init_db():
    """Инициализирует базу данных и создает таблицы, если они не существуют."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    # Таблица для пользователей (агенты, супервайзеры, директор)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL, -- 'agent', 'supervisor', 'director'
            is_active BOOLEAN DEFAULT TRUE,
            supervisor_id INTEGER, -- Для агентов, ссылка на user_id супервайзера
            telegram_id INTEGER UNIQUE -- ID пользователя в Telegram
        )
    """)

    # Таблица для торговых точек
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_points (
            point_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, -- Название ТТ (из колонки ТТ)
            parent_object TEXT -- Объект Родитель
        )
    """)

    # Таблица для расписания (маршрутов)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            schedule_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL, -- Ссылка на пользователя (агента)
            point_id INTEGER NOT NULL, -- Ссылка на торговую точку
            day_of_week TEXT NOT NULL, -- 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС' (для будущей поддержки)
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (point_id) REFERENCES trade_points(point_id)
        )
    """)
    
    # Таблица для фото-отчетов
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            point_id INTEGER NOT NULL,
            report_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            photo_file_ids TEXT, -- JSON-строка с file_id фоток
            latitude REAL,
            longitude REAL,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (point_id) REFERENCES trade_points(point_id)
        )
    """)

    conn.commit()
    conn.close()
    logging.info("База данных инициализирована.")


def get_user_by_telegram_id(telegram_id):
    """Возвращает пользователя по его Telegram ID."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    user = cursor.fetchone()
    conn.close()
    return user

def add_user(telegram_id, full_name, role, supervisor_id=None):
    """Добавляет нового пользователя."""
    conn = sqlite3.connect(DATABASE_NAME)
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
    finally:
        conn.close()

def update_user_role(telegram_id, new_role):
    """Обновляет роль пользователя."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE telegram_id = ?", (new_role, telegram_id))
    conn.commit()
    conn.close()
    logging.info(f"Обновлена роль пользователя {telegram_id} на {new_role}")

def get_or_create_trade_point(name, parent_object=None):
    """Получает ID торговой точки или создает новую, если её нет."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT point_id FROM trade_points WHERE name = ?", (name,))
    point = cursor.fetchone()
    if point:
        conn.close()
        return point[0]
    else:
        cursor.execute("INSERT INTO trade_points (name, parent_object) VALUES (?, ?)", (name, parent_object))
        conn.commit()
        point_id = cursor.lastrowid
        conn.close()
        logging.info(f"Добавлена торговая точка: {name}")
        return point_id

def clear_schedules():
    """Очищает всю таблицу расписаний перед загрузкой нового."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM schedules")
    conn.commit()
    conn.close()
    logging.info("Таблица schedules очищена.")

def save_schedule_from_dataframe(df: pd.DataFrame):
    """
    Сохраняет расписание из DataFrame в базу данных.
    Перед сохранением очищает старое расписание.
    Создает/обновляет пользователей и торговые точки.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    clear_schedules() # Очищаем старые расписания

    # Список для хранения данных о точках, чтобы избежать дубликатов в памяти
    all_trade_points = {} # {point_name: (point_id, parent_object)}

    # Дни недели, которые мы ожидаем в Excel
    days_of_week = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ'] # 'ВС' можно добавить позже

    for index, row in df.iterrows():
        agent_full_name = row['ТМ']
        trade_point_name = row['ТТ']
        parent_object = row.get('Объект Родитель') # Используем .get() на случай, если столбца нет

        # Получаем или создаем пользователя (агента)
        # Для простоты пока используем заглушку user_id=1, так как реальных telegram_id агентов еще нет
        # В будущем здесь будет поиск по telegram_id агента
        cursor.execute("SELECT user_id FROM users WHERE full_name = ? AND role = 'agent'", (agent_full_name,))
        agent_db = cursor.fetchone()
        if not agent_db:
            cursor.execute("INSERT INTO users (full_name, role) VALUES (?, 'agent')", (agent_full_name,))
            agent_id = cursor.lastrowid
            logging.info(f"Автоматически добавлен агент: {agent_full_name}")
        else:
            agent_id = agent_db[0]
        
        # Получаем или создаем торговую точку
        if trade_point_name not in all_trade_points:
            point_id = get_or_create_trade_point(trade_point_name, parent_object)
            all_trade_points[trade_point_name] = (point_id, parent_object)
        else:
            point_id = all_trade_points[trade_point_name][0]
        
        # Сохраняем расписание для каждого дня
        for day in days_of_week:
            if pd.notna(row.get(day)) and row[day] == 1:
                cursor.execute(
                    "INSERT INTO schedules (user_id, point_id, day_of_week) VALUES (?, ?, ?)",
                    (agent_id, point_id, day)
                )
    
    conn.commit()
    conn.close()
    logging.info(f"Расписание для {len(df['ТМ'].unique())} агентов успешно сохранено в базу данных.")

def get_agent_schedule_for_day(agent_user_id, day_of_week):
    """
    Возвращает список торговых точек для агента на определенный день.
    """
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tp.name, tp.parent_object
        FROM schedules s
        JOIN trade_points tp ON s.point_id = tp.point_id
        WHERE s.user_id = ? AND s.day_of_week = ?
        ORDER BY tp.name
    """, (agent_user_id, day_of_week))
    schedule = cursor.fetchall()
    conn.close()
    return schedule

def get_agent_by_telegram_id(telegram_id):
    """Возвращает ID агента по его Telegram ID."""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, full_name, role FROM users WHERE telegram_id = ? AND role = 'agent'", (telegram_id,))
    user_data = cursor.fetchone()
    conn.close()
    return user_data # Возвращает (user_id, full_name, role) или None