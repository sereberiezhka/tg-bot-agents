# bot.py

import asyncio
import logging
import pandas as pd

from database import init_db, get_user_by_telegram_id, add_user, save_schedule_from_dataframe, get_agent_by_telegram_id, get_agent_schedule_for_day
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command

# Импортируем наши настройки
from config import BOT_TOKEN, DIRECTOR_ID

# Включаем логирование
logging.basicConfig(level=logging.INFO)

# Создаем объекты Бота и Диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Хэндлер на команду /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    user_full_name = message.from_user.full_name
    
    # Пытаемся найти пользователя в базе
    db_user = get_user_by_telegram_id(user_id)

    if not db_user:
        # Если пользователя нет в базе, он еще не зарегистрирован/не получил инвайт
        await message.answer(
            f"Привет, {user_full_name}! 👋\n"
            f"Для начала работы введите свой инвайт-код." # Инвайт-коды будут реализованы позже
        )
        # Для тестирования пока временно добавим Директора
        if user_id == DIRECTOR_ID:
            add_user(user_id, user_full_name, 'director')
            await message.answer("Вы зарегистрированы как Директор.")
            # Отправляем Директору его меню
            await send_director_menu(message)
        return

    # Если пользователь найден, определяем его роль и отправляем соответствующее меню
    user_role = db_user[3] # role хранится в 3-й колонке users (0-user_id, 1-full_name, 2-role...)
    
    if user_role == 'director':
        await message.answer(f"С возвращением, Директор {user_full_name}!")
        await send_director_menu(message)
    elif user_role == 'agent':
        await message.answer(f"С возвращением, Агент {user_full_name}! 👋")
        await send_agent_menu(message)
    # Здесь можно добавить другие роли

# Функция для отправки меню Директора
async def send_director_menu(message: types.Message):
    kb = [
        [types.KeyboardButton(text="Загрузить расписание (Excel)")],
        # [types.KeyboardButton(text="Создать инвайт-код")] # Будет реализовано позже
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )
    await message.answer("Меню Директора:", reply_markup=keyboard)


# Функция для отправки меню Агента
async def send_agent_menu(message: types.Message):
    kb = [
        [types.KeyboardButton(text="Мой маршрут на сегодня")]
    ]
    keyboard = types.ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Что хотите сделать?"
    )
    await message.answer("Меню Агента:", reply_markup=keyboard)


# Хэндлер для кнопки "Мой маршрут на сегодня" (для агентов)
@dp.message(F.text == "Мой маршрут на сегодня")
async def get_my_schedule(message: types.Message):
    user_telegram_id = message.from_user.id
    
    # Получаем данные агента из БД
    agent_data = get_agent_by_telegram_id(user_telegram_id)
    if not agent_data:
        await message.answer("Вы не зарегистрированы как агент. Обратитесь к Директору.")
        return
    
    agent_db_id, agent_full_name, _ = agent_data
    
    # Определяем текущий день недели (для SQLite мы используем текстовое название дня)
    # Пример: Python's weekday() возвращает 0 для ПН, 1 для ВТ и т.д.
    # Нам нужно преобразовать это в 'ПН', 'ВТ' и т.д.
    current_day_num = pd.Timestamp.now().weekday()
    day_mapping = {
        0: 'ПН', 1: 'ВТ', 2: 'СР', 3: 'ЧТ', 4: 'ПТ', 5: 'СБ', 6: 'ВС' # Пока 'ВС' не используется
    }
    current_day_of_week = day_mapping.get(current_day_num, 'Н/Д')

    schedule = get_agent_schedule_for_day(agent_db_id, current_day_of_week)

    if not schedule:
        await message.answer(f"Бро, {agent_full_name}, на **{current_day_of_week}** у тебя нет запланированных визитов. Отдыхай! 🏖️", parse_mode="HTML")
        return

    response_text = f"Бро, {agent_full_name}, твой маршрут на **{current_day_of_week}**:\n\n"
    for i, point in enumerate(schedule, 1):
        point_name, parent_object = point
        response_text += f"{i}. **{point_name}** ({parent_object or 'Нет района'})\n"
    
    response_text += "\nНажми на точку, когда будешь готов отправить фотоотчет." # Эта часть будет реализована позже
    await message.answer(response_text, parse_mode="HTML")


# Хэндлер на загрузку документа (Excel-файла)
# Срабатывает, только если сообщение прислал Директор
@dp.message(F.document & (F.from_user.id == DIRECTOR_ID))
async def handle_schedule_file(message: types.Message):
    document = message.document
    
    # Проверяем, что это Excel файл
    if not document.file_name.endswith(('.xlsx', '.xls')):
        await message.answer("Это не похоже на Excel-файл. Пожалуйста, загрузи файл в формате .xlsx")
        return

    await message.answer("Получил файл. Начинаю обработку...")

    try:
        file_info = await bot.get_file(document.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        
        df = pd.read_excel(downloaded_file, engine='openpyxl', header=1)

        required_columns = ['ТМ', 'ТТ', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ']
        # Также проверяем, что столбец 'Объект Родитель' есть, но не делаем его обязательным для работы
        if not all(col in df.columns for col in required_columns):
            await message.answer(
                f"Ошибка! В файле отсутствуют обязательные колонки: 'ТМ', 'ТТ', 'ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ'.\n"
                f"Я нашел вот такие: {list(df.columns)}"
            )
            return

        # --- НОВЫЙ КОД ЗДЕСЬ ---
        # Сохраняем расписание из DataFrame в базу данных
        save_schedule_from_dataframe(df)

        num_rows = len(df)
        num_agents = len(df['ТМ'].unique())
        
        await message.answer(
            f"✅ Расписание успешно загружено и обработано и **сохранено в базу данных**!\n\n"
            f"📊 **Статистика по файлу:**\n"
            f"- Всего строк (маршрутов): {num_rows}\n"
            f"- Уникальных торговых агентов: {num_agents}",
            parse_mode="HTML"
        )
        # --- КОНЕЦ НОВОГО КОДА ---

        # Здесь в будущем будет код для сохранения этого расписания в базу данных

    except Exception as e:
        logging.error(f"Ошибка при обработке файла: {e}")
        await message.answer(f"Ой, произошла ошибка при обработке файла. Подробности: {e}")


# Хэндлер для всех остальных сообщений от Директора
@dp.message(F.from_user.id == DIRECTOR_ID)
async def any_message_from_director(message: types.Message):
    await message.answer("Я вас слушаю, Директор. Чтобы обновить расписание, просто пришлите мне Excel-файл.")


# Основная функция для запуска бота
async def main():
    init_db() # Инициализируем базу данных при запуске бота
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())