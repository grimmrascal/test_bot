import asyncio
import logging
import random
import os
import sqlite3
import requests
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")

if not TOKEN:
    raise ValueError("❌ Токен не знайдено! Перевірте файл .env.")
if not PIXABAY_API_KEY:
    raise ValueError("❌ API-ключ Pixabay не знайдено! Перевірте файл .env.")

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ініціалізація бота і диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Часовий пояс Києва
kyiv_tz = timezone("Europe/Kyiv")

# Ваш Telegram user_id для отримання повідомлень від бота
ADMIN_USER_ID = 471637263  # Замініть на ваш реальний user_id

# Підключення до бази даних
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Створення таблиці користувачів
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE,
                    username TEXT,
                    first_name TEXT
                )''')
conn.commit()

# Функція для створення клавіатури з кнопками
def create_reaction_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❤️", callback_data="reaction:like"),
            InlineKeyboardButton(text="🔄", callback_data="reaction:new_photo"),
        ]
    ])
    return keyboard

# Функція для додавання користувача до бази даних
def add_user(user_id, username, first_name):
    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name)
        VALUES (?, ?, ?)
    ''', (user_id, username, first_name))
    conn.commit()
    # Надсилаємо адміністратору повідомлення про додавання користувача
    asyncio.create_task(bot.send_message(
        ADMIN_USER_ID,
        f"✅ Новий користувач доданий:\nID: {user_id}\nІм'я: {first_name}\nНікнейм: @{username if username else 'немає'}"
    ))

# Функція для видалення користувача з бази даних
def remove_user(user_id):
    cursor.execute('SELECT username, first_name FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    # Надсилаємо адміністратору повідомлення про видалення користувача
    if user:
        username, first_name = user
        asyncio.create_task(bot.send_message(
            ADMIN_USER_ID,
            f"❌ Користувач видалений:\nID: {user_id}\nІм'я: {first_name}\nНікнейм: @{username if username else 'немає'}"
        ))

# Функція для отримання всіх користувачів з бази даних
def get_all_users():
    cursor.execute('SELECT user_id, username, first_name FROM users')
    return cursor.fetchall()

# Функція для отримання випадкового зображення за темою
def get_random_image(query="funny, kids, sunset, motivation"):
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=50"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["hits"]:
            return random.choice(data["hits"])["webformatURL"]
    return None

# Обробник команди /start
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    add_user(user_id, username, first_name)
    await message.answer(f"Привіт, {first_name}! Ти додана у список розсилки.")
    logging.info(f"✅ Користувач {user_id} ({username}) доданий у список розсилки.")

# Обробник команди /sendnow для миттєвої розсилки
@dp.message(Command("sendnow"))
async def send_now_handler(message: types.Message):
    await send_random_messages()

# Обробник команди /get_users для отримання списку учасників
@dp.message(Command("get_users"))
async def get_users_handler(message: types.Message):
    if message.from_user.id == ADMIN_USER_ID:  # Перевіряємо, чи це адміністратор
        users = get_all_users()
        if users:
            user_list = "\n".join([f"ID: {user[0]}, Ім'я: {user[2]}, Нікнейм: @{user[1] if user[1] else 'немає'}" for user in users])
            await message.answer(f"📋 Список учасників:\n{user_list}")
        else:
            await message.answer("❌ Список учасників порожній.")
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Функція для розсилки випадкових приємних повідомлень
async def send_random_messages():
    messages = [
        "Ти чудовий!", "Не забувай посміхатися!", "В тебе все вийде!", "Ти особливий!"
    ]

    for user_id, username, first_name in get_all_users():
        try:
            message = random.choice(messages)
            image = get_random_image(query="motivation")  # Задайте тему, наприклад, "motivation"
            if image:
                await bot.send_photo(
                    user_id,
                    photo=image,
                    caption=message,
                    reply_markup=create_reaction_keyboard()  # Додаємо клавіатуру
                )
                logging.info(f"📨 Повідомлення з картинкою надіслано {user_id}")
            else:
                logging.warning("⚠️ Не вдалося отримати зображення з Pixabay.")
        except Exception as e:
            logging.warning(f"⚠️ Не вдалося надіслати {user_id}: {e}")

# Обробник натискань на кнопки
@dp.callback_query()
async def handle_reaction(callback_query: types.CallbackQuery):
    data = callback_query.data  # Отримуємо callback_data
    user_id = callback_query.from_user.id

    if data == "reaction:like":
        await callback_query.answer("❤️ Дякую за сердечко!")
        logging.info(f"Користувач {user_id} натиснув 'Сердечко'.")
    elif data == "reaction:new_photo":
        # Відправляємо нове фото
        new_image = get_random_image(query="motivation")
        if new_image:
            await bot.send_photo(
                user_id,
                photo=new_image,
                caption="Ось нове фото для тебе!",
                reply_markup=create_reaction_keyboard()
            )
        await callback_query.answer("🔄 Ось нове фото!")
        logging.info(f"Користувач {user_id} запросив нове фото.")

# Планувальник для щоденних повідомлень (1 раз на день)
scheduler = AsyncIOScheduler()
scheduler.add_job(send_random_messages, CronTrigger(hour=18, minute=0, timezone=kyiv_tz))  # 18:00

# Основна функція запуску бота
async def main():
    scheduler.start()  # Запускаємо планувальник
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
