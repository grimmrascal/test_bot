import os
import asyncio
import logging
import random
import requests
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, ReactionUpdated, DefaultBotProperties
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

# Завантажуємо змінні середовища
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
scheduler = AsyncIOScheduler()

# Підключення до SQLite
DB_PATH = "users.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            first_name TEXT,
            username TEXT
        );
    """)
    conn.commit()
    conn.close()

# Додавання користувача в базу
def add_user(user_id, first_name, username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, first_name, username) 
        VALUES (?, ?, ?);
    """, (user_id, first_name, username))
    conn.commit()
    conn.close()

# Отримання випадкового фото з Pixabay
async def get_random_image():
    query = random.choice(["cute animals", "nature", "happy", "cozy", "love"])  # Теми
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=50"
    response = requests.get(url).json()
    if "hits" in response and response["hits"]:
        return random.choice(response["hits"])["webformatURL"]
    return None

# Отримання випадкового приємного повідомлення
def get_random_message():
    messages = [
        "Нехай цей день буде найкращим для тебе! 😊",
        "Ти чудова людина! 🌟",
        "Сьогодні – чудовий день, щоб посміхнутися! 😄",
        "Не забувай, що ти неймовірний! ❤️",
        "Щастя поруч, просто відкрий для нього серце! 💫"
    ]
    return random.choice(messages)

# Обробник команди /start
@dp.message(Command("start"))
async def start_handler(message: Message):
    add_user(message.from_user.id, message.from_user.first_name, message.from_user.username)
    await message.answer("Вітаю! Я надсилатиму тобі випадкові фото та мотиваційні повідомлення.")

# Функція розсилки
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
            await bot.send_photo(user[0], image_url, caption=text)
            await asyncio.sleep(0.5)  # Уникнення ліміту

# Реакція на реакції користувача
@dp.reaction()
async def reaction_handler(update: ReactionUpdated):
    user_id = update.user.id
    reaction = update.new_reaction  # Нові реакції користувача
    await bot.send_message(user_id, f"Дякую за реакцію {reaction}!")

# Запуск шедулера
async def main():
    init_db()
    scheduler.add_job(send_photos, "interval", hours=6)  # Надсилання кожні 6 годин
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())