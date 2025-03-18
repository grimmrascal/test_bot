import logging
import os
import random
import sqlite3
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()

# Читаємо токен і налаштування з .env файлу
TOKEN = os.getenv("TOKEN")
DB_PATH = os.getenv("DB_PATH", "users.db")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# Налаштовуємо логування
logging.basicConfig(level=logging.INFO)

# Ініціалізуємо базу даних SQLite
def create_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER UNIQUE,
        first_name TEXT,
        last_name TEXT,
        username TEXT
    )
    """)
    conn.commit()
    conn.close()

create_table()

# Функція для додавання користувача до бази
async def add_user(user_id, first_name, last_name, username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO users (user_id, first_name, last_name, username) 
    VALUES (?, ?, ?, ?)
    """, (user_id, first_name, last_name, username))
    conn.commit()
    conn.close()

# Функція для отримання всіх користувачів
def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    return [user[0] for user in users]

# Функція для отримання фото з Pixabay
def get_random_photo():
    url = "https://pixabay.com/api/"
    api_key = PIXABAY_API_KEY
    params = {
        "key": api_key,
        "q": "cute",
        "image_type": "photo",
        "per_page": 3,
        "safesearch": "true"
    }
    response = requests.get(url, params=params).json()
    if response["hits"]:
        return random.choice(response["hits"])["webformatURL"]
    return None

# Розсилка фото з приємними повідомленнями
async def send_photos():
    users = get_all_users()
    photo_url = get_random_photo()
    if photo_url:
        message = "Here's a random cute photo for you! 😊"
        for user_id in users:
            try:
                await bot.send_photo(user_id, photo_url, caption=message)
            except Exception as e:
                logging.error(f"Error sending photo to {user_id}: {e}")

# Налаштовуємо планувальник
scheduler = AsyncIOScheduler()
scheduler.add_job(send_photos, IntervalTrigger(hours=6))
scheduler.start()

# Обробник команди /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    user = message.from_user
    await add_user(user.id, user.first_name, user.last_name, user.username)
    await message.reply("Hello! Welcome to the bot. 😊")

# Обробник команди sendnow
@dp.message_handler(commands=["sendnow"])
async def send_now_handler(message: types.Message):
    users = get_all_users()
    photo_url = get_random_photo()
    if photo_url:
        message_text = "Here’s a random cute photo right now! Enjoy! 😊"
        for user_id in users:
            try:
                await bot.send_photo(user_id, photo_url, caption=message_text)
            except Exception as e:
                logging.error(f"Error sending photo to {user_id}: {e}")
        await message.reply("I’ve sent photos to everyone!")

# Обробник кнопки "Next Photo"
@dp.callback_query_handler(lambda c: c.data == 'next_photo')
async def process_next_photo(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    photo_url = get_random_photo()
    if photo_url:
        await bot.send_photo(user_id, photo_url, caption="Here’s the next photo! 😊")
        await callback_query.answer()

# Обробник для генерації наступного фото
@dp.message_handler(commands=["nextphoto"])
async def next_photo_handler(message: types.Message):
    photo_url = get_random_photo()
    if photo_url:
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Next Photo", callback_data="next_photo")
        )
        await message.reply("Here’s a photo for you! 😊", reply_markup=keyboard)
        await bot.send_photo(message.chat.id, photo_url)

# Запуск бота
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)