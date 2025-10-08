# database.py (Версия "Железобетон")

import sqlite3
import pandas as pd
import logging
import uuid

DATABASE_NAME = 'bot_database.db'
logging.basicConfig(level=logging.INFO)

def init_db():
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, role TEXT NOT NULL, 
                is_active BOOLEAN DEFAULT TRUE, supervisor_id INTEGER, telegram_id INTEGER UNIQUE
            )""")
        # Уникальный индекс, нечувствительный к регистру, чтобы нельзя было создать "Ivan" и "ivan"
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_full_name_nocase ON users (full_name COLLATE NOCASE)")
        cursor.execute("CREATE TABLE IF NOT EXISTS trade_points (point_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, parent_object TEXT)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schedules (
                schedule_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, point_id INTEGER NOT NULL, day_of_week TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id), FOREIGN KEY (point_id) REFERENCES trade_points(point_id)
            )""")
        cursor.execute("CREATE TABLE IF NOT EXISTS reports (report_id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, point_id INTEGER NOT NULL, report_time DATETIME DEFAULT CURRENT_TIMESTAMP, photo_file_ids TEXT, latitude REAL, longitude REAL, FOREIGN KEY (user_id) REFERENCES users(user_id), FOREIGN KEY (point_id) REFERENCES trade_points(point_id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS invite_codes (code_id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, role TEXT NOT NULL, is_active BOOLEAN DEFAULT TRUE)")
        conn.commit()
    logging.info("База данных инициализирована.")

def add_user(telegram_id, full_name, role, supervisor_id=None):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (telegram_id, full_name, role, supervisor_id) VALUES (?, ?, ?, ?)", (telegram_id, full_name, role, supervisor_id))
            conn.commit(); return cursor.lastrowid
        except sqlite3.IntegrityError: return None

# --- НОВЫЕ ФУНКЦИИ ДЛЯ УПРАВЛЕНИЯ ПЕРСОНАЛОМ ---

def get_all_supervisors():
    """Возвращает список всех супервайзеров (user_id, full_name)."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'supervisor'")
        return cursor.fetchall()

def get_agents_without_supervisor():
    """Возвращает список агентов, у которых нет супервайзера."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'agent' AND supervisor_id IS NULL")
        return cursor.fetchall()

def assign_agents_to_supervisor(supervisor_id, agent_ids):
    """Присваивает список агентов супервайзеру."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # agent_ids - это список, например [1, 2, 5]
        # Для каждого id в списке выполняем UPDATE
        cursor.executemany("UPDATE users SET supervisor_id = ? WHERE user_id = ?", [(supervisor_id, agent_id) for agent_id in agent_ids])
        conn.commit()
    logging.info(f"Супервайзеру {supervisor_id} назначено {len(agent_ids)} агентов.")


def get_supervisor_team_agents(supervisor_id):
    """Возвращает список ID и имен агентов в команде супервайзера."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name FROM users WHERE supervisor_id = ?", (supervisor_id,))
        return cursor.fetchall()

def get_full_schedule_map():
    schedule_map = {}
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT u.full_name, s.day_of_week, tp.name FROM schedules s JOIN users u ON s.user_id = u.user_id JOIN trade_points tp ON s.point_id = tp.point_id")
        for full_name, day, point_name in cursor.fetchall():
            if full_name not in schedule_map: schedule_map[full_name] = {}
            if day not in schedule_map[full_name]: schedule_map[full_name][day] = set()
            schedule_map[full_name][day].add(point_name)
    return schedule_map

def get_agent_telegram_id_map():
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT full_name, telegram_id FROM users WHERE role = 'agent' AND telegram_id IS NOT NULL")
        return {name: tid for name, tid in cursor.fetchall()}

def save_schedule_from_dataframe(df: pd.DataFrame):
    old_schedule_map = get_full_schedule_map()
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM schedules")
        agents_cache = {name: user_id for user_id, name in cursor.execute("SELECT user_id, full_name FROM users WHERE role = 'agent'").fetchall()}
        points_cache = {name: point_id for point_id, name in cursor.execute("SELECT point_id, name FROM trade_points").fetchall()}

        for _, row in df.iterrows():
            agent_name = ' '.join(str(row['ТМ']).split())
            point_name = ' '.join(str(row['ТТ']).split())
            parent_object = str(row.get('Объект Родитель', ''))

            if agent_name.lower() not in (k.lower() for k in agents_cache.keys()):
                cursor.execute("INSERT INTO users (full_name, role) VALUES (?, 'agent')", (agent_name,))
                agent_id = cursor.lastrowid
                agents_cache[agent_name] = agent_id
                logging.info(f"Создан новый агент: {agent_name}")
            else:
                # Находим правильный ID в кеше, игнорируя регистр
                for name_in_cache, user_id in agents_cache.items():
                    if name_in_cache.lower() == agent_name.lower():
                        agent_id = user_id
                        break
            
            if point_name not in points_cache:
                cursor.execute("INSERT INTO trade_points (name, parent_object) VALUES (?, ?)", (point_name, parent_object))
                point_id = cursor.lastrowid
                points_cache[point_name] = point_id
            else:
                point_id = points_cache[point_name]

            for day in ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']:
                if pd.notna(row.get(day)) and row[day] == 1:
                    cursor.execute("INSERT INTO schedules (user_id, point_id, day_of_week) VALUES (?, ?, ?)", (agent_id, point_id, day))
        conn.commit()
    except Exception as e:
        conn.rollback(); logging.error(f"Ошибка при сохранении в БД: {e}"); raise
    finally:
        conn.close()

    new_schedule_map = get_full_schedule_map()
    telegram_id_map = get_agent_telegram_id_map()
    affected_telegram_ids = []
    all_agent_names = set(old_schedule_map.keys()) | set(new_schedule_map.keys())
    for name in all_agent_names:
        if old_schedule_map.get(name) != new_schedule_map.get(name):
            if name in telegram_id_map: affected_telegram_ids.append(telegram_id_map[name])
    logging.info(f"Найдено {len(affected_telegram_ids)} агентов для уведомления об изменениях.")
    return affected_telegram_ids

def find_unregistered_agent_by_name(full_name):
    """Ищет агента по ФИО, используя нечувствительный к регистру поиск."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # COLLATE NOCASE - это команда SQLite для поиска без учета регистра
        cursor.execute(
            "SELECT user_id FROM users WHERE full_name = ? COLLATE NOCASE AND role = 'agent' AND telegram_id IS NULL",
            (full_name.strip(),)
        )
        result = cursor.fetchone()
        return result[0] if result else None

def link_agent_to_telegram_id(user_id, telegram_id):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET telegram_id = ? WHERE user_id = ?", (telegram_id, user_id))
        conn.commit()
    logging.info(f"Агент (user_id={user_id}) успешно привязан к telegram_id={telegram_id}")

# --- Остальные функции (для инвайтов и т.д.) ---
def create_invite_code(role='agent'):
    code = f"{role.upper()}-{uuid.uuid4().hex[:6].upper()}"
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO invite_codes (code, role) VALUES (?, ?)", (code, role))
        conn.commit()
    return code

def get_user_by_telegram_id(telegram_id):
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
        return cursor.fetchone()

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

def get_agent_schedule_for_day(agent_user_id, day_of_week):
    """Возвращает список (ID точки, Имя точки, Район) для агента на день."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tp.point_id, tp.name, tp.parent_object
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
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, full_name, role, telegram_id FROM users")
        return cursor.fetchall()
    
def save_report(user_id, point_id, photo_file_ids_json, latitude, longitude):
    """Сохраняет данные отчета и возвращает ID этого отчета."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO reports (user_id, point_id, photo_file_ids, latitude, longitude) VALUES (?, ?, ?, ?, ?)",
            (user_id, point_id, photo_file_ids_json, latitude, longitude)
        )
        report_id = cursor.lastrowid
        conn.commit()
        logging.info(f"Сохранен отчет (id={report_id}) от user_id={user_id}")
        return report_id # <-- ВОЗВРАЩАЕМ ID```

def get_point_id_by_name(point_name):
    """Находит ID торговой точки по ее точному названию."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT point_id FROM trade_points WHERE name = ?", (point_name,))
        result = cursor.fetchone()
        return result[0] if result else None

def get_visited_points_today(user_id):
    """Возвращает множество ID точек, по которым агент отчитался сегодня."""
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        # date('now', 'localtime') - получает текущую дату по локальному времени сервера
        cursor.execute(
            "SELECT DISTINCT point_id FROM reports WHERE user_id = ? AND date(report_time, 'localtime') = date('now', 'localtime')",
            (user_id,)
        )
        # Возвращаем set для быстрой проверки (point_id in visited_ids)
        return {row[0] for row in cursor.fetchall()}
    

# --- Обновляем функцию для статистики, чтобы она могла работать и для супервайзера ---

def get_daily_stats(supervisor_id=None):
    """
    Собирает статистику. Если передан supervisor_id, то только по его команде.
    """
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        day_mapping = {0: 'ПН', 1: 'ВТ', 2: 'СР', 3: 'ЧТ', 4: 'ПТ', 5: 'СБ', 6: 'ВС'}
        current_day_key = day_mapping.get(pd.Timestamp.now().weekday())

        if not current_day_key or current_day_key == 'ВС': return 0, 0, []

        # Базовые запросы
        plan_query = "SELECT u.full_name, COUNT(s.point_id) FROM schedules s JOIN users u ON s.user_id = u.user_id WHERE s.day_of_week = ? AND u.role = 'agent'"
        fact_query = "SELECT COUNT(report_id) FROM reports WHERE date(report_time, 'localtime') = date('now', 'localtime')"
        agents_fact_query = "SELECT u.full_name, COUNT(r.report_id) FROM reports r JOIN users u ON r.user_id = u.user_id WHERE date(r.report_time, 'localtime') = date('now', 'localtime')"
        
        params_plan = [current_day_key]
        params_fact = []

        if supervisor_id:
            # Если есть ID супервайзера, добавляем фильтр в запросы
            plan_query += " AND u.supervisor_id = ?"
            fact_query += " AND user_id IN (SELECT user_id FROM users WHERE supervisor_id = ?)"
            agents_fact_query += " AND u.supervisor_id = ?"
            params_plan.append(supervisor_id)
            params_fact.append(supervisor_id)

        plan_query += " GROUP BY u.full_name"
        agents_fact_query += " GROUP BY u.full_name"

        cursor.execute(plan_query, params_plan)
        plan_data = cursor.fetchall()
        total_plan = sum(count for _, count in plan_data)
        
        cursor.execute(fact_query, params_fact)
        total_fact = cursor.fetchone()[0]

        agents_plan = {name: count for name, count in plan_data}
        cursor.execute(agents_fact_query, params_fact)
        agents_fact = {name: count for name, count in cursor.fetchall()}

        laggards = []
        for agent_name, plan_count in agents_plan.items():
            fact_count = agents_fact.get(agent_name, 0)
            if fact_count < plan_count:
                laggards.append({'name': agent_name, 'plan': plan_count, 'fact': fact_count})
        
        return total_plan, total_fact, laggards
    

def get_report_details_for_gsheet(report_id):
    """
    Возвращает все детали отчета для записи в Google Таблицу.
    """
    with sqlite3.connect(DATABASE_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                r.report_time,
                u.full_name,
                tp.name,
                tp.parent_object,
                r.latitude,
                r.longitude,
                r.photo_file_ids
            FROM reports r
            JOIN users u ON r.user_id = u.user_id
            JOIN trade_points tp ON r.point_id = tp.point_id
            WHERE r.report_id = ?
        """, (report_id,))
        return cursor.fetchone()