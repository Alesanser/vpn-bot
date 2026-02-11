import asyncio
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

import asyncpg

# ─────────────────────
# НАСТРОЙКИ
# ─────────────────────
TOKEN = "ТОКЕН_СЮДА"
ADMIN_ID = 935010023
PHONE_NUMBER = "+7 XXX XXX-XX-XX"

DB_CONFIG = {
    "user": "nn",
    "password": "nn",
    "database": "nn",
    "host": "nn"
}

bot = Bot(TOKEN)
dp = Dispatcher()

# ─────────────────────
# ТАРИФЫ
# ─────────────────────
TARIFFS = {
    30: (100, "💎 1 месяц — 100₽"),
    60: (200, "🔥 2 месяца — 200₽"),
    90: (300, "🚀 3 месяца — 300₽"),
    120: (400, "⚡ 4 месяца — 400₽"),
    150: (500, "👑 5 месяцев — 500₽"),
}

# ─────────────────────
# БАЗА ДАННЫХ
# ─────────────────────
async def init_db():
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            vpn_key TEXT,
            paid_until TIMESTAMP
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS keys (
            key TEXT PRIMARY KEY,
            used BOOLEAN DEFAULT FALSE
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id SERIAL PRIMARY KEY,
            user_id BIGINT,
            days INT,
            price INT,
            status TEXT,
            start_date TIMESTAMP,
            is_extend BOOLEAN DEFAULT FALSE
        )
    """)
    await conn.close()

# ─────────────────────
# КЛЮЧИ
# ─────────────────────
async def get_unused_key():
    conn = await asyncpg.connect(**DB_CONFIG)
    row = await conn.fetchrow("SELECT key FROM keys WHERE used=FALSE LIMIT 1")
    await conn.close()
    return row["key"] if row else None

async def mark_key_used(key):
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute("UPDATE keys SET used=TRUE WHERE key=$1", key)
    await conn.close()

async def add_new_key(key):
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute(
        "INSERT INTO keys(key, used) VALUES($1,FALSE) ON CONFLICT DO NOTHING",
        key
    )
    await conn.close()

async def list_all_keys():
    conn = await asyncpg.connect(**DB_CONFIG)
    rows = await conn.fetch("SELECT key, used FROM keys")
    await conn.close()
    return rows

async def delete_key(key):
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute("DELETE FROM keys WHERE key=$1", key)
    await conn.close()

# ─────────────────────
# ПЛАТЕЖИ
# ─────────────────────
async def add_payment(user_id, days, price, is_extend=False):
    conn = await asyncpg.connect(**DB_CONFIG)
    pid = await conn.fetchval(
        "INSERT INTO payments(user_id, days, price, status, start_date, is_extend) "
        "VALUES($1,$2,$3,'pending',$4,$5) RETURNING payment_id",
        user_id, days, price, datetime.now(), is_extend
    )
    await conn.close()
    return pid

async def approve_payment(payment_id):
    conn = await asyncpg.connect(**DB_CONFIG)
    row = await conn.fetchrow(
        "SELECT user_id, days, status, start_date, is_extend FROM payments WHERE payment_id=$1",
        payment_id
    )
    if not row or row["status"] != "pending":
        await conn.close()
        return None, None, None

    key = await get_unused_key()
    if not key:
        await conn.close()
        return None, None, None

    if row["is_extend"]:
        # Продление
        current = await conn.fetchrow("SELECT paid_until FROM users WHERE user_id=$1", row["user_id"])
        start_date = max(current["paid_until"], row["start_date"])
    else:
        start_date = row["start_date"]

    paid_until = start_date + timedelta(days=row["days"])

    await conn.execute("UPDATE payments SET status='approved' WHERE payment_id=$1", payment_id)
    await conn.execute(
        "INSERT INTO users(user_id,vpn_key,paid_until) VALUES($1,$2,$3) "
        "ON CONFLICT(user_id) DO UPDATE SET vpn_key=$2, paid_until=$3",
        row["user_id"], key, paid_until
    )
    await mark_key_used(key)
    await conn.close()
    return row["user_id"], key, paid_until

# ─────────────────────
# КНОПКИ
# ─────────────────────
def main_menu(is_admin=False):
    kb = InlineKeyboardBuilder()
    kb.button(text="💎 Тарифы", callback_data="tariffs")
    kb.button(text="👤 Профиль", callback_data="profile")
    if is_admin:
        kb.button(text="🛠 Админка", callback_data="admin")
    kb.adjust(2)
    return kb.as_markup()

def profile_buttons():
    kb = InlineKeyboardBuilder()
    kb.button(text="⏩ Продлить", callback_data="extend")
    kb.button(text="⬅ Назад", callback_data="start")
    kb.adjust(2)
    return kb.as_markup()

# ─────────────────────
# START / RESTART
# ─────────────────────
@dp.message(Command("start", "restart"))
async def start_cmd(message: Message):
    await message.answer(
        "👋 Добро пожаловать в VPN сервис!",
        reply_markup=main_menu(message.from_user.id == ADMIN_ID)
    )

# ─────────────────────
# ТАРИФЫ
# ─────────────────────
@dp.message(Command("tariffs"))
@dp.callback_query(F.data == "tariffs")
async def tariffs(event):
    kb = InlineKeyboardBuilder()
    for days, (_, text) in TARIFFS.items():
        kb.button(text=text, callback_data=f"buy_{days}")
    kb.adjust(1)
    text = "💳 Выберите тариф:"
    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb.as_markup())
    else:
        await event.answer(text, reply_markup=kb.as_markup())

# ─────────────────────
# ПОКУПКА
# ─────────────────────
@dp.callback_query(F.data.startswith("buy_"))
async def buy_tariff(call: CallbackQuery):
    days = int(call.data.split("_")[1])
    price, text = TARIFFS[days]

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Я оплатил", callback_data=f"paid_{days}")
    kb.button(text="⬅ Назад", callback_data="tariffs")
    kb.adjust(2)

    await call.message.edit_text(
        f"{text}\n\n📱 Оплата на номер:\n{PHONE_NUMBER}",
        reply_markup=kb.as_markup()
    )

@dp.callback_query(F.data.startswith("paid_"))
async def paid(call: CallbackQuery):
    days = int(call.data.split("_")[1])
    price, text = TARIFFS[days]

    pid = await add_payment(call.from_user.id, days, price)
    await call.message.edit_text("⏳ Ожидайте подтверждения администратора")
    await bot.send_message(
        ADMIN_ID,
        f"💰 Платеж #{pid}\n👤 {call.from_user.id}\n{text}\n/approve_{pid} | /reject_{pid}"
    )

# ─────────────────────
# ПРОФИЛЬ
# ─────────────────────
@dp.message(Command("profile"))
@dp.callback_query(F.data == "profile")
async def profile(event):
    user_id = event.from_user.id
    conn = await asyncpg.connect(**DB_CONFIG)
    row = await conn.fetchrow("SELECT vpn_key, paid_until FROM users WHERE user_id=$1", user_id)
    await conn.close()

    if not row:
        text = "❌ У вас нет активной подписки"
        markup = main_menu(user_id == ADMIN_ID)
    else:
        days_left = (row["paid_until"] - datetime.now()).days
        text = f"👤 Профиль\n\n🔑 Ключ:\n{row['vpn_key']}\n⏳ Осталось дней: {days_left}"
        markup = profile_buttons()

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=markup)
    else:
        await event.answer(text, reply_markup=markup)

# ─────────────────────
# ПРОДЛЕНИЕ
# ─────────────────────
@dp.callback_query(F.data == "extend")
async def extend_buy(call: CallbackQuery):
    kb = InlineKeyboardBuilder()
    for days, (_, text) in TARIFFS.items():
        kb.button(text=text, callback_data=f"extend_buy_{days}")
    kb.button(text="⬅ Назад", callback_data="profile")
    kb.adjust(2)
    await call.message.edit_text("💎 Выберите тариф для продления:", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("extend_buy_"))
async def extend_buy_confirm(call: CallbackQuery):
    days = int(call.data.split("_")[2])
    price, text = TARIFFS[days]
    pid = await add_payment(call.from_user.id, days, price, is_extend=True)
    await call.message.edit_text("⏳ Ожидайте подтверждения администратора")
    await bot.send_message(
        ADMIN_ID,
        f"💰 Продление #{pid}\n👤 {call.from_user.id}\n{text}\n/approve_{pid} | /reject_{pid}"
    )

# ─────────────────────
# АДМИНКА
# ─────────────────────
@dp.callback_query(F.data == "admin")
async def admin_panel(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        return

    kb = InlineKeyboardBuilder()
    kb.button(text="➕ Добавить ключ", callback_data="add_key_info")
    kb.button(text="📄 Список ключей", callback_data="list_keys")
    kb.button(text="⬅ Назад", callback_data="start")
    kb.adjust(1)
    await call.message.edit_text("🛠 Админ-панель", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "add_key_info")
async def add_key_info(call: CallbackQuery):
    await call.message.edit_text("➕ Добавить ключ:\nИспользуй команду:\n/add ss://KEY")

@dp.callback_query(F.data == "list_keys")
async def list_keys_cb(call: CallbackQuery):
    rows = await list_all_keys()
    text = "📄 Ключи:\n\n"
    for i, r in enumerate(rows, start=1):
        text += f"{i}. {r['key']} — {'❌ свободен' if not r['used'] else '✅ использован'}\n"
    await call.message.edit_text(text)

# ─────────────────────
# АДМИН-КОМАНДЫ
# ─────────────────────
@dp.message(Command("add"))
async def add_key_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    key = message.text.split(maxsplit=1)
    if len(key) != 2:
        await message.reply("❗ Используй: /add ss://KEY")
        return
    await add_new_key(key[1])
    await message.reply("✅ Ключ добавлен")

@dp.message(Command("del"))
async def del_key_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("❗ Используй: /del НОМЕР_КЛЮЧА")
        return
    index = int(parts[1]) - 1
    keys = await list_all_keys()
    if index < 0 or index >= len(keys):
        await message.reply("❌ Неверный номер ключа")
        return
    key = keys[index]["key"]
    await delete_key(key)
    await message.reply(f"❌ Ключ {key} удалён")

@dp.message(F.text.startswith("/approve_"))
async def approve_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    pid = int(message.text.split("_")[1])
    uid, key, until = await approve_payment(pid)
    if not key:
        await message.reply("❌ Ошибка")
        return
    await message.reply("✅ Платеж подтверждён")
    await bot.send_message(uid, f"🔑 {key}\n⏳ До {until}")

@dp.message(F.text.startswith("/reject_"))
async def reject_cmd(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    pid = int(message.text.split("_")[1])
    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute("UPDATE payments SET status='rejected' WHERE payment_id=$1", pid)
    await conn.close()
    await message.reply("❌ Платеж отклонён")

# ─────────────────────
# СВЯЗЬ С АДМИНОМ
# ─────────────────────
@dp.message(Command("support"))
async def support_cmd(message: Message):
    await message.answer(f"📩 Свяжитесь с администратором: {ADMIN_ID}")

# ─────────────────────
# ЗАПУСК
# ─────────────────────
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

