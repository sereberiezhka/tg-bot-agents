# database.py

import sqlite3
import pandas as pd
import logging
import uuid

DATABASE_NAME = 'bot_database.db'
logging.basicConfig(level=logging.INFO)

# --- ФУНКЦИИ ИНИЦИАЛИЗАЦИИ И ПОЛУЧЕНИЯ ДАННЫХ (остаются почти без изменений) ---

def init_db():
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
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invite_codes (
                code_id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                role TEXT NOT NULL,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        conn.commit()
    logging.info("База данных инициализирована.")

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
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            return None

# --- !!! НОВЫЕ И ИЗМЕНЕННЫЕ ФУНКЦИИ !!! ---

def get_full_schedule_map():
    """
    Возвращает словарь-карту текущего расписания.
    Формат: { 'ФИО Агента': {'ПН': {'Точка1', 'Точка2'}, 'ВТ': {...}}, ... }
    """
    schedule_map = {}
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.full_name, s.day_of_week, tp.name
            FROM schedules s
            JOIN users u ON s.user_id = u.user_id
            JOIN trade_points tp ON s.point_id = tp.point_id
        """)
        for full_name, day, point_name in cursor.fetchall():
            if full_name not in schedule_map:
                schedule_map[full_name] = {}
            if day not in schedule_map[full_name]:
                schedule_map[full_name][day] = set()
            schedule_map[full_name][day].add(point_name)
    return schedule_map

def get_agent_telegram_id_map():
    """Возвращает словарь { 'ФИО Агента': telegram_id } для зарегистрированных агентов."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, telegram_id FROM users WHERE role = 'agent' AND telegram_id IS NOT NULL")
        return {name: tid for name, tid in cursor.fetchall()}

def save_schedule_from_dataframe(df: pd.DataFrame):
    """
    Сохраняет новое расписание и возвращает список telegram_id агентов,
    у которых маршрут изменился.
    """
    # 1. Получаем карту старого расписания ДО изменений
    old_schedule_map = get_full_schedule_map()
    
    # 2. Формируем карту нового расписания из Excel-файла
    new_schedule_map = {}
    days_of_week = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
    for _, row in df.iterrows():
        agent_name = row['ТМ']
        point_name = row['ТТ']
        if agent_name not in new_schedule_map:
            new_schedule_map[agent_name] = {}
        for day in days_of_week:
            if pd.notna(row.get(day)) and row[day] == 1:
                if day not in new_schedule_map[agent_name]:
                    new_schedule_map[agent_name][day] = set()
                new_schedule_map[agent_name][day].add(point_name)
    
    # 3. Сохраняем новое расписание в БД (полная перезапись)
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules")
        for agent_name, days in new_schedule_map.items():
            # Находим или создаем агента
            cursor.execute("SELECT user_id FROM users WHERE full_name = ? AND role = 'agent'", (agent_name,))
            agent_db = cursor.fetchone()
            agent_id = agent_db[0] if agent_db else cursor.execute("INSERT INTO users (full_name, role) VALUES (?, 'agent')", (agent_name,)).lastrowid
            
            for day, points in days.items():
                for point_name in points:
                    # Находим или создаем торговую точку
                    cursor.execute("SELECT point_id FROM trade_points WHERE name = ?", (point_name,))
                    point_db = cursor.fetchone()
                    point_id = point_db[0] if point_db else cursor.execute("INSERT INTO trade_points (name, parent_object) VALUES (?, ?)", (point_name, df[df['ТТ'] == point_name]['Объект Родитель'].iloc[0])).lastrowid
                    
                    cursor.execute("INSERT INTO schedules (user_id, point_id, day_of_week) VALUES (?, ?, ?)", (agent_id, point_id, day))
        conn.commit()
    except Exception as e:
        conn.rollback()
        logging.error(f"Ошибка при сохранении в БД: {e}")
        raise
    finally:
        conn.close()

    # 4. Сравниваем старое и новое расписание и находим затронутых агентов
    telegram_id_map = get_agent_telegram_id_map()
    affected_telegram_ids = []
    
    all_agent_names = set(old_schedule_map.keys()) | set(new_schedule_map.keys())
    
    for name in all_agent_names:
        # Сравниваем расписания. Если они не равны, значит были изменения.
        if old_schedule_map.get(name) != new_schedule_map.get(name):
            # Если у измененного агента есть telegram_id, добавляем его в список для уведомления
            if name in telegram_id_map:
                affected_telegram_ids.append(telegram_id_map[name])
                
    logging.info(f"Найдено {len(affected_telegram_ids)} агентов для уведомления об изменениях.")
    return affected_telegram_ids

# --- Остальные функции (для инвайтов, получения маршрута и т.д.) оставляем без изменений ---
# ... (здесь должен быть остальной код из предыдущей версии database.py) ...
# Копирую его сюда для полноты

def create_invite_code(role='agent'):
    code = f"{role.upper()}-{uuid.uuid4().hex[:6].upper()}"
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invite_codes (code, role) VALUES (?, ?)", (code, role))
        conn.commit()
    return code

def get_invite_code(code):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT role, is_active FROM invite_codes WHERE code = ?", (code,))
        return cursor.fetchone()

def deactivate_invite_code(code):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE invite_codes SET is_active = FALSE WHERE code = ?", (code,))
        conn.commit()

def get_unregistered_agents():
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'agent' AND telegram_id IS NULL")
        return cursor.fetchall()

def link_agent_to_telegram_id(user_id, telegram_id):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET telegram_id = ? WHERE user_id = ?", (telegram_id, user_id))
        conn.commit()
    logging.info(f"Агент (user_id={user_id}) успешно привязан к telegram_id={telegram_id}")

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
    
def get_all_users_for_debug():
    """Возвращает ВСЕХ пользователей для отладки."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # Выбираем user_id, full_name, role, telegram_id
        cursor.execute("SELECT user_id, full_name, role, telegram_id FROM users")
        return cursor.fetchall()
    
def find_unregistered_agent_by_name(full_name):
    """
    Ищет агента по полному имени среди тех, у кого нет telegram_id.
    Возвращает user_id, если найден, иначе None.
    """
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # strip() и lower() для нечувствительности к регистру и пробелам
        cursor.execute(
            "SELECT user_id FROM users WHERE trim(lower(full_name)) = ? AND role = 'agent' AND telegram_id IS NULL",
            (full_name.strip().lower(),)
        )
        result = cursor.fetchone()
        return result[0] if result else None