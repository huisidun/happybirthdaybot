import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
import sqlite3
from datetime import datetime, timedelta
import random
import os
from dotenv import load_dotenv
from flask import Flask  # Импортируем Flask
import threading  # Для запуска Flask в отдельном потоке

# Загружаем переменные из .env
load_dotenv()

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    raise ValueError("Токен не найден. Проверьте файл .env.")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Подключение к базе данных SQLite
conn = sqlite3.connect('birthdays.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблицы для хранения данных
cursor.execute('''
CREATE TABLE IF NOT EXISTS birthdays (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    date TEXT NOT NULL
)
''')
conn.commit()

# Список поздравлений
congratulations = [
    "С днём рождения! Пусть счастье будет бесконечным, а здоровье — крепким! 🎉",
    "Поздравляю! Пусть каждый день приносит радость и вдохновение! 🎂",
    "С днём рождения! Пусть мечты сбываются, а жизнь будет яркой! 🌟",
    "От всей души поздравляю! Пусть удача всегда будет на вашей стороне! 🍀",
    "С днём рождения! Пусть каждый день будет наполнен улыбками и теплом! 😊",
]

# Reply-кнопки
def get_reply_keyboard():
    keyboard = [
        [KeyboardButton("Добавить день рождения")],
        [KeyboardButton("Список дней рождения")],
        [KeyboardButton("Удалить день рождения")],
        [KeyboardButton("Помощь")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Job queue: {context.job_queue}")  # Отладочный вывод
    if not hasattr(context, 'job_queue') or context.job_queue is None:
        await update.message.reply_text("Ошибка: job_queue не инициализирован.")
        return

    # Запускаем напоминания при первом использовании
    if not hasattr(context, 'job_started') or not context.job_started:
        chat_id = update.message.chat_id
        context.job_queue.run_repeating(check_birthdays, interval=86400, first=10, chat_id=chat_id)
        context.job_started = True  # Помечаем, что напоминания запущены

    await update.message.reply_text(
        "Привет! Я бот для напоминаний о днях рождения. Выбери действие:",
        reply_markup=get_reply_keyboard()
    )

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Добавить день рождения":
        await update.message.reply_text("Введите имя и дату рождения в формате ДД-ММ-ГГГГ через пробел\n Например: Иван 15-05-1990")
    elif text == "Список дней рождения":
        await list_birthdays(update, context)
    elif text == "Удалить день рождения":
        await update.message.reply_text("Введите имя человека, чей день рождения нужно удалить:")
    elif text == "Помощь":
        await update.message.reply_text(
            "Я бот для напоминаний о днях рождения\n\n"
            "Используй кнопки для управления:\n"
            "- Добавить день рождения\n"
            "- Список дней рождения\n"
            "- Удалить день рождения\n\n"
            "Для обратной связи:\n"
            "тг: @diiick\n"
            "email: gridasovaa888@gmail.com"
        )
    else:
        # Если текст не является командой, проверяем, может это данные для добавления или удаления
        try:
            args = text.split()
            if len(args) == 2:
                await add_birthday(update, context)
            elif len(args) == 1:
                await delete_birthday(update, context)
        except Exception as e:
            await update.message.reply_text(f"Неизвестная команда. Используйте кнопки для управления.")

# Команда /add_birthday
async def add_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем текст сообщения
        text = update.message.text
        args = text.split()

        if len(args) < 2:
            await update.message.reply_text("Используйте формат: Имя ДД-ММ-ГГГГ\n Например: Иван 15-05-1990")
            return

        name = args[0]
        date_str = args[1]

        # Проверяем корректность даты
        try:
            birth_date = datetime.strptime(date_str, '%d-%m-%Y').date()
        except ValueError:
            await update.message.reply_text("Неверный формат даты. Используйте ДД-ММ-ГГГГ.")
            return

        # Сохраняем данные в базу
        cursor.execute('INSERT INTO birthdays (name, date) VALUES (?, ?)', (name, date_str))
        conn.commit()

        await update.message.reply_text(f"День рождения для {name} ({date_str}) добавлен!")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {e}")

# Команда /list
async def list_birthdays(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем текущую дату
        today = datetime.now().date()

        # Получаем все записи из базы данных
        cursor.execute('SELECT name, date FROM birthdays')
        rows = cursor.fetchall()

        if not rows:
            await update.message.reply_text("Список дней рождения пуст.")
            return

        # Сортируем дни рождения по ближайшей дате
        sorted_rows = sorted(rows, key=lambda x: get_next_birthday(x[1], today))

        # Формируем сообщение со списком
        message = "Список дней рождения (от ближайшего):\n"
        for row in sorted_rows:
            name, date_str = row
            try:
                birth_date = datetime.strptime(date_str, '%d-%m-%Y').date()
                next_birthday = get_next_birthday(date_str, today)
                days_until = (next_birthday - today).days
                message += f"- {name}: {birth_date.strftime('%d-%m-%Y')} (через {days_until} дней)\n"
            except ValueError:
                message += f"- {name}: {date_str} (неверный формат)\n"

        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {e}")

# Функция для вычисления следующего дня рождения
def get_next_birthday(date_str: str, today: datetime.date) -> datetime.date:
    birth_date = datetime.strptime(date_str, '%d-%m-%Y').date()
    next_birthday = birth_date.replace(year=today.year)

    # Если день рождения в этом году уже прошел, переносим на следующий год
    if next_birthday < today:
        next_birthday = next_birthday.replace(year=today.year + 1)

    return next_birthday

# Команда /delete_birthday
async def delete_birthday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        # Получаем текст сообщения
        name = update.message.text.strip()

        # Удаляем запись из базы данных
        cursor.execute('DELETE FROM birthdays WHERE name = ?', (name,))
        conn.commit()

        if cursor.rowcount > 0:
            await update.message.reply_text(f"День рождения для {name} удален!")
        else:
            await update.message.reply_text(f"Человек с именем {name} не найден.")
    except Exception as e:
        await update.message.reply_text(f"Произошла ошибка: {e}")

# Функция для проверки дней рождения
async def check_birthdays(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.now().date()
    tomorrow = today + timedelta(days=1)

    # Ищем дни рождения на завтра
    cursor.execute('SELECT name, date FROM birthdays')
    for row in cursor.fetchall():
        name, date_str = row
        try:
            birth_date = datetime.strptime(date_str, '%d-%m-%Y').date()
            next_birthday = birth_date.replace(year=today.year)

            # Если год уже прошел, переносим на следующий год
            if next_birthday < today:
                next_birthday = next_birthday.replace(year=today.year + 1)

            # Если день рождения завтра
            if next_birthday == tomorrow:
                age = today.year - birth_date.year
                if birth_date.month > today.month or (birth_date.month == today.month and birth_date.day > today.day):
                    age -= 1

                # Выбираем случайное поздравление
                message = (
                    f"Напоминание: завтра день рождения у {name}!\n"
                    f"Исполняется {age} лет.\n"
                    f"{random.choice(congratulations)}"
                )
                await context.bot.send_message(chat_id=context.job.chat_id, text=message)
        except ValueError:
            continue

# Создаем Flask-приложение
app = Flask(__name__)

@app.route('/')
def home():
    return "I'm alive!", 200

# Запускаем Flask в отдельном потоке
def run_flask():
    app.run(host='0.0.0.0', port=10000)

# Основная функция
if __name__ == '__main__':
    # Запускаем Flask в фоновом режиме
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()

    # Создаем приложение для Telegram-бота
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем команды и обработчики
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    application.run_polling()
