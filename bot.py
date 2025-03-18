import logging
import random
import sqlite3
import requests
from aiogram import Bot, Dispatcher, types, ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils import executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import CallbackQuery
from aiogram.utils.emoji import emojize
from aiohttp import ClientSession
import os
from dotenv import load_dotenv

# Завантажуємо змінні середовища з .env файлу
load_dotenv()

# Налаштування логування
logging.basicConfig(level=logging.INFO)

# Зчитуємо токен бота та API ключ для Pixabay з .env
BOT_TOKEN = os.getenv('BOT_TOKEN')
PIXABAY_API_KEY = os.getenv('PIXABAY_API_KEY')

# Ініціалізація бота і диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# Підключення до SQLite
conn = sqlite3.connect('user.db')
cursor = conn.cursor()

# Створення таблиці, якщо її ще немає
cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)''')

# Ініціалізація планувальника
scheduler = AsyncIOScheduler()

# Функція для відправки рандомних фото
def get_random_image():
    # Використовуємо Pixabay API для отримання рандомного фото
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q=nature&image_type=photo"
    response = requests.get(url)
    data = response.json()
    random_image = random.choice(data['hits'])['webformatURL']
    return random_image

# Функція для збереження користувачів у базі даних
def save_user(user_id, username, first_name):
    cursor.execute("INSERT OR IGNORE INTO users (id, username, first_name) VALUES (?, ?, ?)",
                   (user_id, username, first_name))
    conn.commit()

# Функція для надсилання фотографії
async def send_photo(message, photo_url):
    await message.answer_photo(photo_url)

# Обробник команди /start
@dp.message_handler(commands=["start"])
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    # Збереження користувача у базі даних
    save_user(user_id, username, first_name)

    # Вітальне повідомлення
    welcome_message = f"Привіт, {first_name}! Я твій помічник. Щоб отримати фото, натисни кнопку нижче."
    
    keyboard = InlineKeyboardMarkup().add(InlineKeyboardButton("Отримати фото", callback_data="get_photo"))
    await message.answer(welcome_message, reply_markup=keyboard)

# Обробник натискання кнопки
@dp.callback_query_handler(lambda c: c.data == 'get_photo')
async def process_callback_photo(callback_query: CallbackQuery):
    photo_url = get_random_image()  # Отримуємо URL рандомного фото
    await send_photo(callback_query.message, photo_url)  # Надсилаємо фото
    await callback_query.answer()

# Функція для розсилки фото через задані інтервали
def send_scheduled_photos():
    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()
    
    for user in users:
        user_id = user[0]
        photo_url = get_random_image()  # Отримуємо URL рандомного фото
        try:
            bot.send_photo(user_id, photo_url)
        except Exception as e:
            logging.error(f"Error sending photo to {user_id}: {e}")

# Планувальник для відправки фото
scheduler.add_job(
    send_scheduled_photos,
    IntervalTrigger(hours=1),  # Викликається кожну годину
    id='send_photos_job',
    name='Send photos to users every hour',
    replace_existing=True
)

# Функція для відправки повідомлень
async def send_random_messages():
    cursor.execute("SELECT id FROM users")
    users = cursor.fetchall()
    
    messages = [
        "Твій день буде чудовим!",
        "Не забувай посміхатись!",
        "Ти можеш все, якщо хочеш!",
        "Час для нових досягнень!"
    ]
    
    for user in users:
        user_id = user[0]
        message = random.choice(messages)
        try:
            await bot.send_message(user_id, message)
        except Exception as e:
            logging.error(f"Error sending message to {user_id}: {e}")

# Планувальник для відправки повідомлень
scheduler.add_job(
    send_random_messages,
    IntervalTrigger(hours=3),  # Викликається кожні 3 години
    id='send_messages_job',
    name='Send random messages to users every 3 hours',
    replace_existing=True
)

# Запуск планувальника
scheduler.start()

# Запуск бота
if __name__ == "__main__":
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)