import logging
import os
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import requests
import sqlite3
from dotenv import load_dotenv
import random

# Завантаження .env файлу
load_dotenv()

# API ключ від Pixabay та Telegram Bot Token з .env файлу
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Ініціалізація бота та диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Підключення до бази даних SQLite
conn = sqlite3.connect('user.db')
cursor = conn.cursor()

# Створення таблиці користувачів, якщо вона не існує
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER UNIQUE,
        username TEXT
    )
''')
conn.commit()

# Функція для отримання випадкових фото з Pixabay
def get_random_image():
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q=cat&image_type=photo&per_page=3"
    response = requests.get(url)
    data = response.json()
    if data['hits']:
        image_url = random.choice(data['hits'])['webformatURL']
        return image_url
    return None

# Команда /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    # Перевірка, чи є користувач в базі даних
    cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (message.from_user.id,))
    user = cursor.fetchone()

    if user is None:
        # Додавання нового користувача
        cursor.execute("INSERT INTO users (telegram_id, username) VALUES (?, ?)", 
                       (message.from_user.id, message.from_user.username))
        conn.commit()

    # Відповідь користувачу з кнопкою
    keyboard = InlineKeyboardMarkup(row_width=1).add(
        InlineKeyboardButton("Отримати випадкове фото", callback_data="get_image")
    )
    await message.answer("Привіт! Це твій бот. Натисни кнопку, щоб отримати випадкове фото.", reply_markup=keyboard)

# Обробник callback-запитів для кнопки
@dp.callback_query_handler(lambda c: c.data == "get_image")
async def process_callback(callback_query: types.CallbackQuery):
    image_url = get_random_image()
    if image_url:
        await bot.send_photo(callback_query.from_user.id, image_url)
    else:
        await bot.send_message(callback_query.from_user.id, "Не вдалося отримати зображення. Спробуйте ще раз!")

    await callback_query.answer()

# Функція для випадкової відправки фото (задана за розкладом)
async def send_random_photo():
    cursor.execute("SELECT telegram_id FROM users")
    users = cursor.fetchall()
    
    image_url = get_random_image()
    if image_url:
        for user in users:
            await bot.send_photo(user[0], image_url)

# Налаштування планувальника для регулярної відправки фото
scheduler = AsyncIOScheduler()
scheduler.add_job(send_random_photo, 'interval', hours=24)  # Відправка фото кожні 24 години
scheduler.start()

# Запуск бота
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)