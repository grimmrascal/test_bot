import logging
import os
import random
import sqlite3
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv
import asyncio

# Завантаження змінних з .env файлу
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", "user.db")  # Вказуємо шлях до існуючої бази
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

# Ініціалізація об'єктів Bot і Dispatcher
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()  # Dispatcher без передачі bot безпосередньо

# Налаштовуємо логування
logging.basicConfig(level=logging.INFO)

# Ініціалізація бази даних SQLite
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

# Функція додавання користувача до бази даних
def add_user(user_id, first_name, last_name, username):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    INSERT OR IGNORE INTO users (user_id, first_name, last_name, username)
    VALUES (?, ?, ?, ?)
    """, (user_id, first_name, last_name, username))
    conn.commit()
    conn.close()

# Функція для отримання випадкового фото з Pixabay
def get_random_image():
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q=happy&image_type=photo&per_page=3"
    response = requests.get(url)
    data = response.json()
    if data["hits"]:
        image_url = random.choice(data["hits"])["webformatURL"]
        return image_url
    return None

# Список випадкових фраз
random_phrases = [
    "Привіт, друже! Сподіваюсь, у тебе чудовий день! 😊",
    "Час для гарного фото! Надіюсь, воно тобі сподобається! 📸",
    "Бажаю тобі найкращого! Тримай гарне фото! 🌟",
    "Сподіваюся, цей момент зробить твій день краще! 💖"
]

# Функція для відправки випадкового фото з фразою
async def send_random_photo_with_phrase(message: types.Message):
    photo_url = get_random_image()
    phrase = random.choice(random_phrases)
    if photo_url:
        markup = InlineKeyboardMarkup().add(
            InlineKeyboardButton("😍 Лайк", callback_data="like"),
            InlineKeyboardButton("😲 Ух ти!", callback_data="wow")
        )
        await message.answer_photo(photo_url, caption=phrase, reply_markup=markup)
    else:
        await message.answer("Не вдалося знайти фото. Спробуй ще раз пізніше.")

# Команда старт
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    username = message.from_user.username
    add_user(user_id, first_name, last_name, username)
    await message.answer(f"Привіт, {first_name}! Я бот, готовий надсилати тобі рандомні фото.")

# Команда для надсилання фото
async def send_photo_handler(message: types.Message):
    await send_random_photo_with_phrase(message)

# Команда для надсилання фото негайно
async def send_now_handler(message: types.Message):
    await send_random_photo_with_phrase(message)

# Планування регулярної розсилки
scheduler = AsyncIOScheduler()

@scheduler.scheduled_job(IntervalTrigger(hours=1))
async def scheduled_photo_send():
    # Отправка фото всім користувачам
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()
    
    for user in users:
        user_id = user[0]
        try:
            photo_url = get_random_image()
            phrase = random.choice(random_phrases)
            if photo_url:
                await bot.send_photo(user_id, photo_url, caption=phrase)
        except Exception as e:
            logging.error(f"Не вдалося надіслати фото користувачу {user_id}: {e}")

# Обробка натискання кнопок (реакції)
@dp.callback_query_handler(lambda c: c.data in ["like", "wow"])
async def process_callback(callback_query: types.CallbackQuery):
    reaction = callback_query.data
    if reaction == "like":
        await bot.answer_callback_query(callback_query.id, text="Ти лайкнув це фото! ❤️")
    elif reaction == "wow":
        await bot.answer_callback_query(callback_query.id, text="Вау! Це неймовірно! 😲")

# Запуск планувальника в асинхронному циклі
async def on_start():
    create_table()  # Переконатися, що таблиця є в базі даних
    # Запуск планувальника в циклі подій
    scheduler.start()
    await dp.start_polling()

# Регістрація команд
dp.message(commands=["start"])(start_handler)  # Оновлений метод реєстрації
dp.message(commands=["sendphoto"])(send_photo_handler)
dp.message(commands=["sendnow"])(send_now_handler)

# Запуск бота
if __name__ == "__main__":
    # Використовуємо asyncio.run() для запуску асинхронної функції
    asyncio.run(on_start())