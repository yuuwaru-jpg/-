import asyncio
import logging
import os
import urllib.parse
from datetime import datetime, timedelta
import asyncpg
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.client.session.aiohttp import AiohttpSession

# Включаем логирование, чтобы видеть запуск в консоли
logging.basicConfig(level=logging.INFO)

# --- ⚙️ КОНФИГУРАЦИЯ БОТА (ТВОИ РАБОЧИЕ ДАННЫЕ) ---
BOT_TOKEN = ""
ADMIN_USERNAME = "yuuwaru"          # Твой юзернейм без @
PRICE_AMOUNT = 200.00               # Цена подписки в рублях

# --- ⚙️ НАСТРОЙКИ POSTGRESQL (ТВОИ РАБОЧИЕ ДАННЫЕ) ---
DB_USER = ""
DB_PASSWORD = ""
DB_NAME = ""
DB_HOST = ""
DB_PORT = 

# --- 💳 НАСТРОЙКИ КОШЕЛЬКА ЮMONEY ---
# Замени на свой номер кошелька ЮMoney (начинается на 41001...), когда он у тебя появится
YUMONEY_WALLET = "" 

# Намертво заворачиваем трафик к Телеграму в твой запущенный Hiddify (порт 12334)
session = AiohttpSession(proxy="")
bot = Bot(token=BOT_TOKEN, session=session)
dp = Dispatcher()
db_pool = None

# --- 🗄️ РАБОТА С БАЗОЙ ДАННЫХ ---
async def init_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        user=DB_USER, password=DB_PASSWORD, database=DB_NAME, host=DB_HOST, port=DB_PORT
    )
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                tg_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                expire_date DATE
            )
        """)
    logging.info("🐘 База PostgreSQL успешно инициализирована.")

async def get_user_status(tg_id: int) -> str:
    async with db_pool.acquire() as connection:
        row = await connection.fetchrow("SELECT expire_date FROM users WHERE tg_id = $1", tg_id)
    if row is None or row['expire_date'] is None:
        return "❌ Подписка отсутствует"
    expire_date = row['expire_date']
    today = datetime.now().date()
    if expire_date >= today:
        return f"🟢 Активна до {expire_date.strftime('%d.%m.%Y')}"
    return f"🔴 Истекла {expire_date.strftime('%d.%m.%Y')}"

async def extend_subscription(tg_id: int, username: str, days: int = 30):
    async with db_pool.acquire() as connection:
        row = await connection.fetchrow("SELECT expire_date FROM users WHERE tg_id = $1", tg_id)
        today = datetime.now().date()
        if row and row['expire_date']:
            current_expire = row['expire_date']
            start_date = current_expire if current_expire > today else today
        else:
            start_date = today
        new_expire = start_date + timedelta(days=days)
        await connection.execute("""
            INSERT INTO users (tg_id, username, expire_date) VALUES ($1, $2, $3)
            ON CONFLICT (tg_id) DO UPDATE SET username = $2, expire_date = $3
        """, tg_id, username, new_expire)

# --- ⏰ АВТОМАТИЧЕСКАЯ НАПОМИНАЛКА ДОЛЖНИКАМ ---
async def scheduler_loop():
    while True:
        await asyncio.sleep(86400) # Проверка базы раз в 24 часа
        logging.info("⏳ Запуск автоматической проверки подписок...")
        today = datetime.now().date()
        three_days_later = today + timedelta(days=3)
        async with db_pool.acquire() as connection:
            # 1. Напоминание тем, у кого конец через 3 дня
            rows_warn = await connection.fetch("SELECT tg_id FROM users WHERE expire_date = $1", three_days_later)
            for row in rows_warn:
                try:
                    await bot.send_message(
                        chat_id=row['tg_id'],
                        text="⚠️ **Внимание!** Ваш доступ к IT-поддержке заканчивается через **3 дня**.\nПродлите подписку кнопкой `💳 Продлить доступ`.",
                        parse_mode="Markdown"
                    )
                except Exception: pass
            # 2. Блокировка тех, у кого подписка кончилась сегодня
            rows_expired = await connection.fetch("SELECT tg_id FROM users WHERE expire_date = $1", today)
            for row in rows_expired:
                try:
                    await bot.send_message(
                        chat_id=row['tg_id'],
                        text="🔴 **Ваша подписка на IT-поддержку истекла.**\nДля возобновления нажмите кнопку `💳 Продлить доступ`.",
                        parse_mode="Markdown"
                    )
                except Exception: pass

# --- 🎮 ИНТЕРФЕЙС БОТА ---
def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="💎 Мой кабинет"), types.KeyboardButton(text="💳 Продлить доступ")],
        [types.KeyboardButton(text="📚 Правила и Оферта"), types.KeyboardButton(text="👨‍💻 Поддержка")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    await extend_subscription(user_id, username, days=0) # Авто-регистрация в Postgres с 0 дней доступа
    
    welcome_text = (
        f"👋 **Приветствуем, {message.from_user.first_name}!**\n\n"
        "Добро пожаловать в закрытый сервис персональной IT-поддержки.\n"
        "Вы успешно внесены в систему ИТ-услуг.\n\n"
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
        "Если ваша подписка активна, вы можете запрашивать конфигурации у админа в ЛС."
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "💳 Продлить доступ")
async def menu_pay(message: types.Message):
    user_id = message.from_user.id
    
    # Автоматически собираем параметры платежной формы Яндекса / ЮMoney (Quickpay)
    params = {
        'receiver': YUMONEY_WALLET,
        'quickpay-form': 'button',
        'targets': 'Оплата персональных IT-услуг',
        'paymentType': 'SB',  # Разрешает оплату по картам и СБП
        'sum': PRICE_AMOUNT,
        'label': f'pay_{user_id}'  # В этот маркер намертво зашивается ID клиента для чека!
    }
    
    # Формируем прямую ссылку на оплату
    pay_url = f"https://yoomoney.ru?{urllib.parse.urlencode(params)}"
    
    kb = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="💳 Оплатить (СБП / Карты)", url=pay_url)],
        [types.InlineKeyboardButton(text="👨‍💻 Написать админу после оплаты", url=f"https://t.me/{ADMIN_USERNAME}")]
    ])
    
    await message.answer(
        "🏷 **Продление доступа к IT-сервису**\n\n"
        f"Стоимость подписки на 30 дней: **{PRICE_AMOUNT} руб.**\n\n"
        "Нажмите на кнопку ниже, чтобы перейти к безопасной оплате картой любого банка или СБП.\n\n"
        "⚠️ **После успешного перевода** напишите администратору в ЛС, и он сразу выдаст вам свежие конфигурации софта.",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message(F.text == "📚 Правила и Оферта")
async def menu_rules(message: types.Message):
    text = (
        "📜 **Правовая информация**\n\n"
        "Оплачивая услуги сервиса, вы соглашаетесь с условиями публичной оферты.\n\n"
        "🔗 [Читать оферту](https://telegram.org)\n"
        "🔗 [Политика конфиденциальности](https://telegram.org)"
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

# Секретная команда для тебя (админа), чтобы вручную активировать пользователей по ID из чека
# Формат команды в чате бота: /add_user 123456789 30
@dp.message(Command("add_user"))
async def cmd_add_user(message: types.Message):
    try:
        args = message.text.split()
        target_id = int(args[1])  
        days = int(args[2])       
        await extend_subscription(target_id, "ManualAdded", days=days)
        await message.answer(f"✅ Пользователь `{target_id}` успешно продлен в PostgreSQL на {days} дней.")
        try:
            await bot.send_message(target_id, f"🎉 Администратор активировал вам доступ на {days} дней!")
        except Exception: pass
    except Exception:
        await message.answer("Ошибка. Формат: `/add_user ID ДНИ` \nПример: `/add_user 53123456 30`")

# --- 🏁 ЗАПУСК БОТА ---
async def main():
    # Отключаем прокси Hiddify для локального подключения к PostgreSQL
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"
    await init_db()
    # Запускаем фоновый планировщик проверки дат
    asyncio.create_task(scheduler_loop())
    print("🚀 Бот успешно запущен и готов к работе!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
