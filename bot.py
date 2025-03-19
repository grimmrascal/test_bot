import asyncio
import logging
import random
import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from dotenv import load_dotenv

# Завантаження змінних середовища
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

if not TOKEN:
    raise ValueError("❌ Токен не знайдено! Перевірте файл .env.")
if not PIXABAY_API_KEY:
    raise ValueError("❌ API-ключ Pixabay не знайдено! Перевірте файл .env.")
if not DATABASE_URL:
    raise ValueError("❌ URL бази даних не знайдено! Перевірте файл .env.")

# Налаштування логування
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Ініціалізація бота і диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# Ініціалізація Router
router = Router()
dp.include_router(router)

# Часовий пояс Києва
kyiv_tz = timezone("Europe/Kyiv")

# Список Telegram user_id для отримання повідомлень від бота
ADMIN_USER_IDS = [471637263, 5142786008, 646146668]  # Замініть на список реальних user_id

# Підключення до бази даних PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cursor = conn.cursor(cursor_factory=RealDictCursor)

# Створення таблиці користувачів
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        user_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        first_name TEXT
    )
''')
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
    try:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
        ''', (user_id, username, first_name))
        conn.commit()
        logging.info(f"Користувач {user_id} доданий до бази даних.")
    except Exception as e:
        conn.rollback()  # Скасовуємо транзакцію у разі помилки
        logging.error(f"Помилка при додаванні користувача {user_id}: {e}")

# Функція для видалення користувача з бази даних
def remove_user(user_id):
    try:
        cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
        conn.commit()
        logging.info(f"Користувач {user_id} видалений із бази даних.")
    except Exception as e:
        conn.rollback()  # Скасовуємо транзакцію у разі помилки
        logging.error(f"Помилка при видаленні користувача {user_id}: {e}")

# Функція для отримання всіх користувачів з бази даних
def get_all_users():
    try:
        cursor.execute('SELECT user_id, username, first_name FROM users')
        return cursor.fetchall()
    except Exception as e:
        conn.rollback()  # Скасовуємо транзакцію у разі помилки
        logging.error(f"Помилка при отриманні списку користувачів: {e}")
        return []

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
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        await send_random_messages()
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Обробник команди /t для розсилки тексту або фото всім користувачам, крім відправника
@dp.message(Command("t"))
async def broadcast_handler(message: types.Message):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        try:
            users = get_all_users()  # Отримуємо список усіх користувачів

            if not users:
                await message.answer("❌ Немає користувачів для розсилки.")
                return

            # Якщо повідомлення містить фото
            if message.photo:
                photo_id = message.photo[-1].file_id  # Найкраща якість фото
                caption = message.caption  # Отримуємо підпис (None, якщо немає)

                for user in users:
                    if user['user_id'] == message.from_user.id:
                        continue  # Пропускаємо відправника

                    try:
                        await bot.send_photo(
                            chat_id=user['user_id'],
                            photo=photo_id,
                            caption=caption  # Додаємо лише підпис, якщо є
                        )
                        logging.info(f"📨 Фото надіслано користувачу {user['user_id']}")
                    except Exception as e:
                        logging.warning(f"⚠️ Не вдалося надіслати фото користувачу {user['user_id']}: {e}")

                await message.answer("✅ Фото успішно розіслано всім користувачам!")
                return  # Завершуємо функцію, щоб не обробляти текст далі

            # Якщо фото немає, розсилаємо лише текст (без команди "/t")
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.answer("❌ Неправильний формат. Надішліть фото або використовуйте: /t <текст повідомлення>.")
                return

            broadcast_message = command_parts[1]  # Беремо текст без команди

            for user in users:
                if user['user_id'] == message.from_user.id:
                    continue  # Пропускаємо відправника

                try:
                    await bot.send_message(user['user_id'], broadcast_message)
                    logging.info(f"📨 Повідомлення надіслано користувачу {user['user_id']}")
                except Exception as e:
                    logging.warning(f"⚠️ Не вдалося надіслати повідомлення користувачу {user['user_id']}: {e}")

            await message.answer("✅ Повідомлення успішно розіслано всім користувачам!")

        except Exception as e:
            await message.answer(f"❌ Помилка при розсилці: {e}")
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")


        
# Обробник команди /get_users для отримання списку учасників
@dp.message(Command("get_users"))
async def get_users_handler(message: types.Message):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        users = get_all_users()
        if users:
            user_list = "\n".join([f"ID: {user['user_id']}, Ім'я: {user['first_name']}, Нікнейм: @{user['username'] if user['username'] else 'немає'}" for user in users])
            await message.answer(f"📋 Список учасників:\n{user_list}")
        else:
            await message.answer("❌ Список учасників порожній.")
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Обробник команди /add_user для ручного додавання користувача
@dp.message(Command("add_user"))
async def add_user_handler(message: types.Message):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        try:
            # Розділяємо текст команди на частини
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.answer("❌ Неправильний формат. Використовуйте: /add_user <user_id>")
                return

            # Отримуємо user_id
            user_id = int(command_parts[1])

            # Перевіряємо, чи користувач вже існує
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            existing_user = cursor.fetchone()
            if existing_user:
                await message.answer(f"❌ Користувач із ID {user_id} вже існує в базі даних.")
                return

            # Отримуємо інформацію про користувача через Telegram API
            try:
                user = await bot.get_chat(user_id)
                username = user.username if user.username else "немає"
                first_name = user.first_name if user.first_name else "немає"
            except Exception as e:
                await message.answer(f"❌ Не вдалося отримати інформацію про користувача з ID {user_id}: {e}")
                return

            # Додаємо користувача до бази даних
            add_user(user_id, username, first_name)
            await message.answer(f"✅ Користувач доданий:\nID: {user_id}\nІм'я: {first_name}\nНікнейм: @{username}")
        except ValueError:
            await message.answer("❌ Неправильний формат. user_id має бути числом.")
        except Exception as e:
            await message.answer(f"❌ Помилка при додаванні користувача: {e}")
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Обробник команди /remove_user для ручного видалення користувача
@dp.message(Command("remove_user"))
async def remove_user_handler(message: types.Message):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        try:
            # Розділяємо текст команди на частини
            command_parts = message.text.split(maxsplit=1)
            if len(command_parts) < 2:
                await message.answer("❌ Неправильний формат. Використовуйте: /remove_user <user_id>")
                return

            # Отримуємо user_id
            user_id = int(command_parts[1])

            # Перевіряємо, чи користувач існує
            cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
            existing_user = cursor.fetchone()
            if not existing_user:
                await message.answer(f"❌ Користувача з ID {user_id} не знайдено в базі даних.")
                return

            # Видаляємо користувача
            remove_user(user_id)
            await message.answer(f"✅ Користувач із ID {user_id} успішно видалений.")
        except ValueError:
            await message.answer("❌ Неправильний формат. user_id має бути числом.")
        except Exception as e:
            await message.answer(f"❌ Помилка при видаленні користувача: {e}")
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

@router.callback_query(lambda callback: callback.data.startswith("reaction:"))
async def reaction_handler(callback: types.CallbackQuery):
    if callback.data == "reaction:like":
        await callback.answer("❤️ Дякую за твою реакцію!")
        logging.info(f"Користувач {callback.from_user.id} натиснув ❤️")
    elif callback.data == "reaction:new_photo":
        await callback.answer("🔄 Завантажую нове фото...")
        logging.info(f"Користувач {callback.from_user.id} запросив нове фото")

        # Завантажуємо нове фото
        image = get_random_image(query="motivation")
        if image:
            await bot.send_photo(
                callback.from_user.id,
                photo=image,
                caption="Ось нове фото для вас!",
                reply_markup=create_reaction_keyboard()
            )
        else:
            await callback.message.answer("⚠️ Не вдалося отримати нове фото.")

# Функція для розсилки випадкових приємних повідомлень
async def send_random_messages():
    messages = [
        "Ти чудовий!", "Не забувай посміхатися!", "В тебе все вийде!", "Ти особливий!"
    ]

    for user in get_all_users():
        try:
            message = random.choice(messages)
            image = get_random_image(query="motivation")
            if image:
                await bot.send_photo(
                    user['user_id'],
                    photo=image,
                    caption=message,
                    reply_markup=create_reaction_keyboard()
                )
                logging.info(f"📨 Повідомлення з картинкою надіслано {user['user_id']}")
            else:
                logging.warning("⚠️ Не вдалося отримати зображення з Pixabay.")
        except Exception as e:
            logging.warning(f"⚠️ Не вдалося надіслати {user['user_id']}: {e}")

# Планувальник для щоденних повідомлень
scheduler = AsyncIOScheduler()
scheduler.add_job(send_random_messages, CronTrigger(hour=18, minute=0, timezone=kyiv_tz))

# Основна функція запуску бота
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
