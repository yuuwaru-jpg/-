import asyncio
import logging
from datetime import datetime, timedelta
import asyncpg  # Асинхронная библиотека для PostgreSQL
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command

logging.basicConfig(level=logging.INFO)

# --- ⚙️ КОНФИГУРАЦИЯ БОТА ---
BOT_TOKEN = "8854797738:AAF_YdTULmfd88XVz4xMeovghimv3l2ZW_I"
PAYMENT_TOKEN = "ТОКЕН_ПЛАТЕЖА_ИЗ_BOTFATHER"  
ADMIN_USERNAME = "yuuwaru"    
PRICE_AMOUNT = 30000                           

# --- ⚙️ КОНФИГУРАЦИЯ ПОДКЛЮЧЕНИЯ POSTGRESQL ---
# Измени данные ниже на свои
DB_USER = "
DB_PASSWORD = ""
DB_NAME = ""
DB_HOST = ""  # или IP-адрес, если база на другом сервере
DB_PORT = 

from aiogram.client.session.aiohttp import AiohttpSession

# Намертво привязываем бота к рабочему порту Hiddify (12334)
session = AiohttpSession(proxy="http://127.0.0.1:12334") 

# Передаем эту сессию в инициализацию бота
bot = Bot(token=BOT_TOKEN, session=session)

dp = Dispatcher()

# Глобальная переменная для пула соединений
db_pool = None

# --- 🗄️ РАБОТА С БАЗОЙ ДАННЫХ (POSTGRESQL) ---
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST, port=DB_PORT
    )
    async with db_pool.acquire() as connection:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                expire_date DATE
            )
        """)
    logging.info("🐘 База данных PostgreSQL успешно инициализирована.")

async def get_user_status(tg_id: int) -> str:
    async with db_pool.acquire() as connection:
        row = await connection.fetchrow(r"SELECT expire_date FROM users WHERE tg_id = \$1", tg_id)
    if not row:
        return "❌ Подписка отсутствует"
    expire_date = row['expire_date']
    today = datetime.now().date()
    if expire_date >= today:
        return f"🟢 Активна до {expire_date.strftime('%d.%m.%Y')}"
    return f"🔴 Истекла {expire_date.strftime('%d.%m.%Y')}"

async def extend_subscription(tg_id: int, username: str, days: int = 30):
    async with db_pool.acquire() as connection:
        row = await connection.fetchrow(r"SELECT expire_date FROM users WHERE tg_id = \$1", tg_id)
        today = datetime.now().date()
        if row and row['expire_date']:
            current_expire = row['expire_date']
            start_date = current_expire if current_expire > today else today
        else:
            start_date = today
        new_expire = start_date + timedelta(days=days)
        await connection.execute(r"""
            INSERT INTO users (tg_id, username, expire_date) VALUES (\$1, \$2, \$3)
            ON CONFLICT (tg_id) DO UPDATE SET username = \$2, expire_date = \$3
        """, tg_id, username, new_expire)

async def scheduler_loop():
    while True:
        await asyncio.sleep(86400)
        logging.info("⏳ Запуск автоматической проверки подписок...")
        today = datetime.now().date()
        three_days_later = today + timedelta(days=3)
        async with db_pool.acquire() as connection:
            rows_warn = await connection.fetch(r"SELECT tg_id FROM users WHERE expire_date = \$1", three_days_later)
            for row in rows_warn:
                user_id = row['tg_id']
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text="⚠️ **Внимание!** Ваш доступ к IT-поддержке заканчивается через **3 дня**.\n"
                             "Чтобы софт продолжал работать без сбоев, пожалуйста, продлите подписку в меню бота (кнопка `💳 Продлить доступ`).",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")
            rows_expired = await connection.fetch(r"SELECT tg_id FROM users WHERE expire_date = \$1", today)
            for row in rows_expired:
                user_id = row['tg_id']
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text="🔴 **Ваша подписка на IT-поддержку истекла.**\n"
                             "Доступ к конфигурациям и техподдержке временно ограничен. "
                             "Для возобновления нажмите кнопку `💳 Продлить доступ`.",
                        parse_mode="Markdown"
                    )
                except Exception as e:
                    logging.error(f"Не удалось отправить уведомление пользователю {user_id}: {e}")


# --- 🎮 ИНТЕРФЕЙС БОТА ---
def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="💎 Мой кабинет"), types.KeyboardButton(text="💳 Продлить доступ")],
        [types.KeyboardButton(text="📚 Правила и Оферта"), types.KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    welcome_text = (
        f"👋 **Приветствуем, {message.from_user.first_name}!**\n\n"
        "Добро пожаловать в закрытый сервис персональной IT-поддержки.\n"
        "Здесь вы можете управлять своей подпиской на технические консультации, "
        "оптимизацию сетевого трафика и удаленную настройку ПО.\n\n"
        "Используйте нижнее меню для навигации 👇"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@dp.message(F.text == "💎 Мой кабинет")
async def menu_cabinet(message: types.Message):
    status = await get_user_status(message.from_user.id)
    text = (
        "👤 **Ваш личный кабинет**\n\n"
        f"• **Ваш ID:** `{message.from_user.id}`\n"
        f"• **Статус ИТ-поддержки:** {status}\n\n"
        "Если ваша подписка активна, вы можете запросить актуальные конфигурации софта у администратора в ЛС."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💳 Продлить доступ")
async def menu_pay(message: types.Message):
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Подписка на IT-поддержку",
        description="Технические консультации, оптимизация трафика и помощь с ПО на 30 дней.",
        payload="monthly_sub",
        provider_token=PAYMENT_TOKEN,
        currency="RUB",
        prices=[types.LabeledPrice(label="Тариф 'Оптимальный'", amount=PRICE_AMOUNT)],
        start_parameter="pay_sub"
    )

@dp.message(F.text == "📚 Правила и Оферта")
async def menu_rules(message: types.Message):
    text = (
        "📜 **Правовая информация**\n\n"
        "Оплачивая услуги сервиса, вы полностью соглашаетесь с условиями публичной оферты "
        "на оказание информационно-технических услуг.\n\n"
        "🔗 [Читать публичную оферту](https://drive.google.com/drive/folders/1OHzXgawxvMl74kKe2NM3SW1wD8qWr5UB?usp=drive_link)\n"
        "🔗 [Политика конфиденциальности](https://telegram.org)\n\n"
        "Сервис предоставляется официально. Чеки формируются автоматически."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "👨‍💻 Поддержка")
async def menu_support(message: types.Message):
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💬 Написать администратору", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    text = (
        "🛠 **Служба поддержки**\n\n"
        "Возникли трудности с настройкой софта или оплатой?\n"
        "Нажмите кнопку ниже, чтобы связаться с техническим специалистом в личных сообщениях."
    )
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# --- 💳 ТЕХНИЧЕСКАЯ ОБРАБОТКА ПЛАТЕЖА ---
@dp.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@dp.message(lambda message: message.successful_payment is not None)
async def success_payment_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # Продлеваем подписку в PostgreSQL
    await extend_subscription(user_id, username, days=30)
    
    success_text = (
        "🎉 **Оплата успешно подтверждена!**\n\n"
        "💰 Сумма зачислена. Ваша подписка на IT-поддержку успешно продлена на **30 дней**.\n\n"
        f"👉 Теперь напишите администратору в ЛС [@{ADMIN_USERNAME}], отправьте ему ваш ID (`{user_id}`) "
        "и он выдаст вам актуальные конфигурационные файлы или ключи."
    )
    await message.answer(success_text, parse_mode="Markdown")

# --- 🏁 ЗАПУСК БОТА ---
async def main():
    # Говорим Python НЕ пускать локальную базу данных PostgreSQL через прокси Hiddify
    import os
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    
    # Важно: Сначала запускаем подключение к PostgreSQL
    await init_db()
    
    # Запускаем фоновый планировщик напоминаний
    asyncio.create_task(scheduler_loop())
    print("🚀 Бот запущен на PostgreSQL и планировщик активирован!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
