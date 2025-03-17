import asyncio
import logging
import random
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("❌ Токен не знайдено! Перевірте файл .env.")

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ініціалізація бота і диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Часовий пояс Києва
kyiv_tz = timezone("Europe/Kyiv")

# Підключення до бази даних
conn = sqlite3.connect('users.db')
cursor = conn.cursor()

# Створення таблиці користувачів
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER UNIQUE
                )''')
conn.commit()

# Функція для додавання користувача до бази даних
def add_user(user_id):
    cursor.execute('INSERT OR IGNORE INTO users (user_id) VALUES (?)', (user_id,))
    conn.commit()

# Функція для видалення користувача з бази даних
def remove_user(user_id):
    cursor.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()

# Функція для отримання всіх користувачів з бази даних
def get_all_users():
    cursor.execute('SELECT user_id FROM users')
    return [row[0] for row in cursor.fetchall()]

# Обробник команди /start
@dp.message(Command("start"))
async def start_handler(message: types.Message):
    add_user(message.from_user.id)
    await message.answer(f"Привіт, {message.from_user.first_name}! Ти додана у список розсилки.")
    logging.info(f"✅ Користувач {message.from_user.id} доданий у список розсилки.")

# Обробник команди /sendnow для миттєвої розсилки
@dp.message(Command("sendnow"))
async def send_now_handler(message: types.Message):
    await send_random_messages()

# Функція для розсилки випадкових приємних повідомлень
async def send_random_messages():
    messages = [
        "Ти чудовий!", "Не забувай посміхатися!", "В тебе все вийде!", "Ти особливий!"
    ]
    images = [
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSDUZqyAjDc-cVBLEZ-ulHqYeNrLzvTyheolw&s",
        "https://i.pinimg.com/236x/8f/4b/5b/8f4b5b5adc5c25e6b54e91de257eb5bc.jpg",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcTjHIhkA1YZs-XYX1XfGPn_vbQNLkqxVK4Z1g&s",
        "https://lux.fm/uploads/640_DIR/media_news/2017/10/4e56b2abdbb88fb6b46f74850844fd2a94745d82.jpg?w=400&fit=cover&output=webp&q=85",
        "https://img.novosti-n.org/upload/ukraine/1146173.jpg",
        "https://st2.depositphotos.com/2927537/7025/i/450/depositphotos_70253417-stock-photo-funny-monkey-with-a-red.jpg",
        "https://st.depositphotos.com/1146092/4555/i/450/depositphotos_45550465-stock-photo-cocktail-dog.jpg",
        "https://static.nv.ua/shared/system/MediaPhoto/images/000/107/490/original/f7a5e08ed77f458574a589653bfe6d65.png?q=85&stamp=20211210195055&f=jpg",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRSSlokAPuDGtjvJl-cHQ0QvOvyxSVh5ED3nA&s",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQoSRIRImLia1fY1vzabQsfGEDFfYVXLi5q-w&s",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQd6_ca5sSXIv9NvcMJTJL9NbeZlsg_Pi_2q2nDmmckhcpEucUrK5bragnlnPtDqg2l7kQ&usqp=CAU",
        "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRTXcTRddhiOgd0tBJILScBTzwQv_Ci4HT2NQ&s",
        "https://www.5.ua/media/pictures/original/196599.jpg?t=1601905263",
    ]

    for user_id in get_all_users():
        try:
            message = random.choice(messages)
            image = random.choice(images)
            await bot.send_photo(user_id, photo=image, caption=message)
            logging.info(f"📨 Повідомлення з картинкою надіслано {user_id}")
        except Exception as e:
            logging.warning(f"⚠️ Не вдалося надіслати {user_id}: {e}")

# Логування всіх оновлень (для діагностики)
@dp.update()
async def all_updates_handler(update: types.Update):
    logging.info(f"📥 Отримано оновлення: {update}")

# Обробник виходу користувача з чату
@dp.chat_member()
async def chat_member_handler(update: types.ChatMemberUpdated):
    user_id = update.from_user.id
    new_status = update.new_chat_member.status

    if new_status in ["kicked", "left"]:
        remove_user(user_id)
        logging.info(f"❌ Користувач {user_id} вийшов або був видалений з чату.")

# Планувальник для щоденних повідомлень (2 рази на день)
scheduler = AsyncIOScheduler()
scheduler.add_job(send_random_messages, CronTrigger(hour=10, minute=0, timezone=kyiv_tz))  # 10:00
scheduler.add_job(send_random_messages, CronTrigger(hour=18, minute=0, timezone=kyiv_tz))  # 18:00

# Основна функція запуску бота
async def main():
    scheduler.start()  # Запускаємо планувальник
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())