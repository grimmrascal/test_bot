import logging
import os
import random
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from dotenv import load_dotenv
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio

# Завантаження змінних з .env файлу
load_dotenv()

# Отримуємо значення змінних середовища
BOT_TOKEN = os.getenv("BOT_TOKEN")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

# Ініціалізація об'єктів Bot і Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher.from_entry(bot)  # Використовуємо from_entry() для ініціалізації Dispatcher

# Налаштовуємо логування
logging.basicConfig(level=logging.INFO)

# Підключення до SQLite бази даних
def init_db():
    conn = sqlite3.connect('user.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        full_name TEXT
                    )''')
    conn.commit()
    conn.close()

# Додаємо користувача в базу даних
def add_user_to_db(user_id, username, full_name):
    conn = sqlite3.connect('user.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)', 
                   (user_id, username, full_name))
    conn.commit()
    conn.close()

# Отримуємо випадкове фото з Pixabay API
def get_random_photo():
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q=nature&image_type=photo&per_page=10"
    response = requests.get(url)
    data = response.json()
    hits = data.get('hits', [])
    if hits:
        return random.choice(hits)['webformatURL']
    return None

# Кнопки
def get_inline_buttons():
    keyboard = InlineKeyboardMarkup(row_width=2)
    like_button = InlineKeyboardButton("👍 Like", callback_data="like")
    wow_button = InlineKeyboardButton("😲 Wow", callback_data="wow")
    keyboard.add(like_button, wow_button)
    return keyboard

# Обробник команди /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    # Додаємо користувача в базу даних
    add_user_to_db(user_id, username, full_name)

    # Отримуємо випадкове фото
    photo_url = get_random_photo()

    # Відправляємо повідомлення з кнопками
    if photo_url:
        await message.answer_photo(photo_url, caption="Ось твоє випадкове фото!", reply_markup=get_inline_buttons())
    else:
        await message.answer("Не вдалося отримати фото.")

# Обробник callback query (реакції на кнопки)
@dp.callback_query_handler(lambda c: c.data in ["like", "wow"])
async def handle_reaction(callback_query: types.CallbackQuery):
    reaction = callback_query.data
    user_id = callback_query.from_user.id
    # Записуємо реакцію користувача в базу даних чи інше місце для подальшого використання

    # Відправляємо повідомлення користувачу
    await bot.answer_callback_query(callback_query.id, text=f"Ти натиснув {reaction}")
    await bot.send_message(user_id, f"Ти вибрав реакцію: {reaction}")

# Команда для миттєвої розсилки
@dp.message_handler(commands=["sendnow"])
async def sendnow_handler(message: types.Message):
    # Відправляємо випадкові фото всім користувачам, які є в базі
    conn = sqlite3.connect('user.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()

    for user in users:
        user_id = user[0]
        photo_url = get_random_photo()
        if photo_url:
            await bot.send_photo(user_id, photo_url, caption="Це твоє нове фото!")
        else:
            await bot.send_message(user_id, "Не вдалося отримати фото.")

# Планування відправки фото кожні 30 хвилин
async def scheduled_send_photos():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_photos, 'interval', minutes=30)
    scheduler.start()

async def send_photos():
    conn = sqlite3.connect('user.db')
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM users')
    users = cursor.fetchall()
    conn.close()

    for user in users:
        user_id = user[0]
        photo_url = get_random_photo()
        if photo_url:
            await bot.send_photo(user_id, photo_url, caption="Це твоє випадкове фото!")
        else:
            await bot.send_message(user_id, "Не вдалося отримати фото.")

# Запуск планувальника
async def on_start():
    init_db()
    await scheduled_send_photos()
    await dp.start_polling()

if __name__ == "__main__":
    asyncio.run(on_start())