import asyncio
import logging
import random
import os
import requests
import psycopg2
from psycopg2.extras import RealDictCursor
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram import Router
from aiogram.types import ContentType
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from dotenv import load_dotenv
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Завантаження змінних середовища
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")
BOT_PASSWORD = os.getenv("BOT_PASSWORD")

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
dp = Dispatcher(storage=MemoryStorage())

# Ініціалізація Router
router = Router()
dp.include_router(router)

# Часовий пояс Києва
kyiv_tz = timezone("Europe/Kyiv")

# Список Telegram user_id для отримання повідомлень від бота
ADMIN_USER_IDS = [471637263, 646146668]  # Замініть на список реальних user_id

# Підключення до бази даних PostgreSQL
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
cursor = conn.cursor(cursor_factory=RealDictCursor)

# Створення таблиці користувачів
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,               -- Унікальний ідентифікатор запису
        user_id BIGINT UNIQUE NOT NULL,      -- Унікальний Telegram ID користувача
        username TEXT,                       -- Ім'я користувача (нікнейм)
        first_name TEXT,                     -- Ім'я користувача
        last_active TIMESTAMP DEFAULT NOW()  -- Час останньої активності користувача
    )
''')
conn.commit()

# Стани для кожної групи станів
class AddUserState(StatesGroup):
    waiting_for_user_id = State()

class BroadcastState(StatesGroup):
    waiting_for_message = State()

class RemoveUserState(StatesGroup):
    waiting_for_user_id = State()

# Додавання стовпця last_active до таблиці users
cursor.execute('''
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS last_active TIMESTAMP DEFAULT NOW();
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

# Функція для створення клавіатури для звичайного користувача
def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Перезапустити"), KeyboardButton(text="📤 Розсилка")],
            [KeyboardButton(text="✉️ Своє повідомлення")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# Функція для створення клавіатури для адміністратора
def create_admin_keyboard():
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Список користувачів")],
            [KeyboardButton(text="➕ Додати користувача"), KeyboardButton(text="➖ Видалити користувача")],
            [KeyboardButton(text="📤 Розсилка"), KeyboardButton(text="✉️ Своє повідомлення")]
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard

# Функція для додавання користувача до бази даних
def add_user(user_id, username, first_name):
    try:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, last_active)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE SET last_active = NOW()
        ''', (user_id, username, first_name))
        conn.commit()
        logging.info(f"Користувач {user_id} доданий або оновлений у базі даних.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Помилка при додаванні користувача {user_id}: {e}")

# Функція для оновлення часу останньої активності користувача
def update_last_active(user_id):
    try:
        cursor.execute('''
            UPDATE users
            SET last_active = NOW()
            WHERE user_id = %s
        ''', (user_id,))
        conn.commit()
        logging.info(f"Оновлено час останньої активності для користувача {user_id}.")
    except Exception as e:
        conn.rollback()
        logging.error(f"Помилка при оновленні активності користувача {user_id}: {e}")

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
def get_random_image(query="cute, funny, kids, sunset, flowers"):
    url = f"https://pixabay.com/api/?key={PIXABAY_API_KEY}&q={query}&image_type=photo&per_page=50"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data["hits"]:
            return random.choice(data["hits"])["webformatURL"]
    return None

# Обробник тексту для клавіатури
@dp.message(lambda message: message.text == "🔄 Перезапустити")
async def restart_handler(message: types.Message):
    await start_handler(message)

@dp.message(lambda message: message.text == "📤 Розсилка")
async def sendnow_handler_button(message: types.Message):
    await send_now_handler(message)

@dp.message(lambda message: message.text == "✉️ Своє повідомлення")
async def t_handler_button(message: types.Message, state: FSMContext):
    await t_handler(message, state)

@dp.message(lambda message: message.text == "📊 Статистика")
async def stats_handler_button(message: types.Message):
    await stats_handler(message)

@dp.message(lambda message: message.text == "👥 Список користувачів")
async def get_users_handler_button(message: types.Message):
    await get_users_handler(message)

@dp.message(lambda message: message.text == "➕ Додати користувача")
async def add_user_handler_button(message: types.Message, state: FSMContext):
    await add_user_start(message, state)

@dp.message(lambda message: message.text == "➖ Видалити користувача")
async def remove_user_handler_button(message: types.Message, state: FSMContext):
    await remove_user_start(message, state)

# Обробник команди /start
@router.message(Command("start"))
async def start_handler(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name

    update_last_active(user_id)  # Оновлюємо активність

    # Вибір клавіатури залежно від ролі
    if user_id in ADMIN_USER_IDS:
        keyboard = create_admin_keyboard()
    else:
        keyboard = create_main_keyboard()

    # Відправляємо привітання та клавіатуру
    await message.answer(
        "🔒 Введіть пароль для доступу до бота:",
        reply_markup=keyboard
    )

# Окремий обробник для перевірки пароля
@router.message()
async def password_handler(message: Message):
    entered_password = message.text.strip()  # Видаляємо зайві пробіли
    correct_password = os.getenv("BOT_PASSWORD")  # Завантажуємо пароль із .env

    if not correct_password:
        await message.answer("❌ Пароль не налаштований. Зверніться до адміністратора.")
        logging.error("❌ Пароль не завантажено з файлу .env.")
        return

    if entered_password == correct_password:
        user_id = message.from_user.id
        username = message.from_user.username
        first_name = message.from_user.first_name

        add_user(user_id, username, first_name)  # Додаємо користувача до бази даних

        await message.answer(f"✅ Пароль правильний! Привіт, {first_name}! Ви отримали доступ до бота.")
        logging.info(f"✅ Користувач {user_id} ({username}) успішно ввів пароль.")

        # Повідомляємо адміністраторів про нового користувача
        new_user_text = (
            f"🆕 Новий користувач!\n"
            f"👤 Ім'я: {first_name}\n"
            f"🆔 ID: {user_id}\n"
            f"🔗 @{username if username else 'немає'}"
        )
        for admin_id in ADMIN_USER_IDS:
            try:
                await bot.send_message(admin_id, new_user_text)
            except Exception as e:
                logging.warning(f"⚠️ Не вдалося повідомити адміна {admin_id}: {e}")
    else:
        await message.answer("❌ Неправильний пароль. Спробуйте ще раз.")
        logging.warning(f"❌ Невдала спроба доступу користувача {message.from_user.id} ({message.from_user.username}).")

# Обробник команди /sendnow для миттєвої розсилки
@dp.message(Command("sendnow"))
async def send_now_handler(message: types.Message):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        await send_random_messages()
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Універсальний обробник для необроблених повідомлень
@router.message()
async def handle_unhandled_messages(message: types.Message):
    logging.info(f"Необроблене повідомлення: {message.text}")
    await message.answer("❌ Вибачте, я не розумію цю команду.")

# Обробник команди /t
@dp.message(Command("t"))
async def t_handler(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_USER_IDS:  # Перевірка на адміністратора
        await message.answer("❌ У вас немає прав для виконання цієї команди.")
        return

    await message.answer("📩 Надішліть текст або фото для розсилки.")
    await state.set_state(BroadcastState.waiting_for_message)  # Встановлюємо стан очікування

# Обробник введення тексту або фото для розсилки
@dp.message(BroadcastState.waiting_for_message)
async def process_broadcast_message(message: types.Message, state: FSMContext):
    try:
        users = get_all_users()

        if not users:
            await message.answer("❌ Немає користувачів для розсилки.")
            await state.clear()  # Очищаємо стан
            return

        # Виключаємо відправника з розсилки
        users = [user for user in users if user['user_id'] != message.from_user.id]

        if not users:
            await message.answer("❌ Немає інших користувачів для розсилки.")
            await state.clear()  # Очищаємо стан
            return

        # **Обробка фото**
        if message.content_type == ContentType.PHOTO:
            photo_id = message.photo[-1].file_id  # Отримуємо фото у найкращій якості
            caption = message.caption if message.caption else ""

            for user in users:
                try:
                    await bot.send_photo(chat_id=user['user_id'], photo=photo_id, caption=caption or None)
                    logging.info(f"📨 Фото надіслано користувачу {user['user_id']}")
                except Exception as e:
                    logging.warning(f"⚠️ Не вдалося надіслати фото користувачу {user['user_id']}: {e}")

            await message.answer("✅ Фото успішно розіслано всім користувачам!")
        # **Обробка тексту**
        elif message.content_type == ContentType.TEXT:
            text_content = message.text.strip()

            if not text_content:
                await message.answer("❌ Ви не написали текст для розсилки!")
                return

            for user in users:
                try:
                    await bot.send_message(chat_id=user['user_id'], text=text_content)
                    logging.info(f"📨 Повідомлення надіслано користувачу {user['user_id']}")
                except Exception as e:
                    logging.warning(f"⚠️ Не вдалося надіслати повідомлення користувачу {user['user_id']}: {e}")

            await message.answer("✅ Повідомлення успішно розіслано всім користувачам!")

    except Exception as e:
        await message.answer(f"❌ Помилка при розсилці: {e}")
    finally:
        await state.clear()  # Очищаємо стан після завершення

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

@dp.message(Command("stats"))
async def stats_handler(message: types.Message):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        try:
            # Отримуємо кількість користувачів
            cursor.execute('SELECT COUNT(*) AS total_users FROM users')
            total_users = cursor.fetchone()
            if not total_users:
                total_users = {'total_users': 0}

            # Отримуємо останню активність
            cursor.execute('''
                SELECT username, first_name, last_active
                FROM users
                ORDER BY last_active DESC
                LIMIT 5
            ''')
            recent_activity = cursor.fetchall()

            # Формуємо повідомлення
            stats_message = f"📊 Статистика:\n\n"
            stats_message += f"👥 Загальна кількість користувачів: {total_users['total_users']}\n\n"
            stats_message += "🕒 Остання активність:\n"
            if recent_activity:
                for user in recent_activity:
                    username = f"@{user['username']}" if user['username'] else "немає"
                    stats_message += f"👤 {user['first_name']} ({username}) - {user['last_active']}\n"
            else:
                stats_message += "Немає даних про активність.\n"

            await message.answer(stats_message)
        except Exception as e:
            logging.error(f"Помилка при отриманні статистики: {e}")
            await message.answer("❌ Помилка при отриманні статистики.")
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Обробник команди /add_user для ручного додавання користувача
@dp.message(Command("add_user"))
async def add_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        await message.answer("Введіть ID користувача, якого потрібно додати:")
        await state.set_state(AddUserState.waiting_for_user_id)  # Встановлюємо стан очікування user_id
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Обробник введення user_id після команди /add_user
@dp.message(AddUserState.waiting_for_user_id)
async def process_add_user(message: types.Message, state: FSMContext):
    try:
        # Отримуємо user_id
        user_id = int(message.text)

        # Перевіряємо, чи користувач вже існує
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        existing_user = cursor.fetchone()
        if existing_user:
            await message.answer(f"❌ Користувач із ID {user_id} вже існує в базі даних.")
        else:
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
        await message.answer("❌ ID має бути числом. Спробуйте ще раз.")
    except Exception as e:
        await message.answer(f"❌ Помилка при додаванні користувача: {e}")
    finally:
        await state.clear()  # Очищаємо стан після завершення

# Обробник команди /remove_user для ручного видалення користувача
@dp.message(Command("remove_user"))
async def remove_user_start(message: types.Message, state: FSMContext):
    if message.from_user.id in ADMIN_USER_IDS:  # Перевіряємо, чи це адміністратор
        await message.answer("Введіть ID користувача, якого потрібно видалити:")
        await state.set_state(RemoveUserState.waiting_for_user_id)  # Встановлюємо стан очікування user_id
    else:
        await message.answer("❌ У вас немає прав для виконання цієї команди.")

# Обробник введення user_id після команди /remove_user
@dp.message(RemoveUserState.waiting_for_user_id)
async def process_remove_user(message: types.Message, state: FSMContext):
    try:
        # Отримуємо user_id
        user_id = int(message.text)

        # Перевіряємо, чи користувач існує
        cursor.execute('SELECT * FROM users WHERE user_id = %s', (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            await message.answer(f"❌ Користувача з ID {user_id} не знайдено в базі даних.")
        else:
            # Видаляємо користувача
            remove_user(user_id)
            await message.answer(f"✅ Користувач із ID {user_id} успішно видалений.")
    except ValueError:
        await message.answer("❌ ID має бути числом. Спробуйте ще раз.")
    except Exception as e:
        await message.answer(f"❌ Помилка при видаленні користувача: {e}")
    finally:
        await state.clear()  # Очищаємо стан після завершення

# Обробник команди для інлайн кнопок
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
        "Ти чудова!", "Не забувай посміхатися!", "В тебе все вийде!", "Ти особлива!", "Ти супер!"
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
