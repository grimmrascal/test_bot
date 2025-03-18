import asyncio
import logging
import requests
import sqlite3
import os
import random
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv
from aiogram.filters import Command

# Завантажуємо змінні середовища з .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
DB_PATH = "users.db"

# Логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація бота та диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Ініціалізація планувальника
scheduler = AsyncIOScheduler()

# Функція для створення таблиці користувачів у SQLite
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT
        )
    """)
    conn.commit()
    conn.close()

# Функція для додавання користувачів у БД
async def add_user(user_id, first_name, username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, first_name, username) VALUES (?, ?, ?)",
                   (user_id, first_name, username))
    conn.commit()
    conn.close()

# Функція для отримання рандомного фото з Pixabay
async def get_random_image():
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q=cute&image_type=photo&per_page=50"
    response = requests.get(url).json()
    if "hits" in response and response["hits"]:
        return random.choice(response["hits"])["webformatURL"]
    return None

# Функція для отримання приємного повідомлення
def get_random_message():
    messages = [
        "Нехай твій день буде чудовим! 😊",
        "Ти неймовірний! 🌟",
        "Не забувай усміхатися! 😃",
        "Світ прекрасний, і ти також! 💖",
    ]
    return random.choice(messages)

# Функція для створення клавіатури з реакціями
def get_reaction_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("❤️ Подобається", callback_data="like"),
        InlineKeyboardButton("🔄 Поділитися", callback_data="share"),
        InlineKeyboardButton("➡️ Наступне фото", callback_data="next_photo")
    )
    return keyboard

# Функція для розсилки фото та приємних повідомлень
async def send_photos():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    for user in users:
        image_url = await get_random_image()
        text = get_random_message()
        if image_url:
            await bot.send_photo(user[0], image_url, caption=text, reply_markup=get_reaction_keyboard())
            await asyncio.sleep(0.5)

# Обробка команди /start
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    await add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    await message.answer("Привіт! Я буду надсилати тобі приємні фото та повідомлення! 😊")

# Обробка натискання кнопок реакцій
@dp.callback_query(lambda c: c.data in ["like", "share", "next_photo"])
async def process_callback(callback_query: CallbackQuery):
    if callback_query.data == "like":
        await bot.answer_callback_query(callback_query.id, text="❤️ Дякую за реакцію!")
    elif callback_query.data == "share":
        await bot.answer_callback_query(callback_query.id, text="🔄 Поділись цим з друзями!")
    elif callback_query.data == "next_photo":
        # Надсилаємо нове фото
        new_image_url = await get_random_image()
        if new_image_url:
            await bot.send_photo(callback_query.from_user.id, new_image_url, caption=get_random_message(), reply_markup=get_reaction_keyboard())
        await bot.answer_callback_query(callback_query.id)

# Запуск бота
async def main():
    init_db()
    scheduler.add_job(send_photos, "interval", hours=6)  # Розсилка кожні 6 годин
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())