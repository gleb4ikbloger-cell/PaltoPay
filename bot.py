import asyncio
import sqlite3
from datetime import datetime

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import CommandStart
from aiogram.types import (
    Message,
    CallbackQuery,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)


# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = "8947272227:AAFLewDd6XO9GUklPNbQfk7B5One0LQMAJ8"

MODERATOR_ID = 8878805596

DB_NAME = "paltopay.db"

MIN_DEPOSIT = 3.0
MIN_WITHDRAW = 5.0

# =========================================================
# КУПИТЬ / ПРОДАТЬ — НАСТРОЙКИ
# =========================================================
# Курс задаётся в гривнах за 1 единицу криптовалюты.
BUY_SELL_RATES = {
    "USDT": 48.00,
    "TON": 67.00,
}

# Карта/реквизиты, на которые пользователь платит при покупке.
BUY_CARD_NUMBER = "5355 5732 5012 2898"
BUY_CARD_NAME = "SenseBank"

# Адреса, куда пользователь отправляет крипту при продаже.
# Для USDT используется сеть TRC20; TON — сеть TON.
SELL_USDT_ADDRESS = ""
SELL_TON_ADDRESS = ""



# =========================================================
# АДРЕСА
# =========================================================

USDT_TRC20_ADDRESS = "TFaPn86mJdp7nebZSCMUMqTSZ2itEPYw6f"

USDT_ERC20_ADDRESS = ""
USDT_BEP20_ADDRESS = ""
USDT_TON_ADDRESS = ""

TON_ADDRESS = ""


# =========================================================
# BOT
# =========================================================

if not BOT_TOKEN or BOT_TOKEN == "НОВЫЙ_ТОКЕН":
    raise RuntimeError("Вставь новый токен в BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


# =========================================================
# DATABASE
# =========================================================

db = sqlite3.connect(DB_NAME, check_same_thread=False)
cursor = db.cursor()


cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    balance_usdt REAL DEFAULT 0,
    balance_ton REAL DEFAULT 0,
    created_at TEXT,
    blocked INTEGER DEFAULT 0
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    currency TEXT,
    amount REAL,
    description TEXT,
    created_at TEXT
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    currency TEXT,
    amount REAL,
    address TEXT,
    network TEXT,
    status TEXT,
    created_at TEXT,
    receipt_file_id TEXT,
    fee_percent REAL DEFAULT 0,
    fee_amount REAL DEFAULT 0,
    net_amount REAL DEFAULT 0
)
""")


cursor.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")


# =========================================================
# МИГРАЦИИ
# =========================================================

def add_column_if_missing(table, column, column_type):

    cursor.execute(f"PRAGMA table_info({table})")
    columns = [row[1] for row in cursor.fetchall()]

    if column not in columns:
        cursor.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {column_type}"
        )


add_column_if_missing("users", "username", "TEXT")
add_column_if_missing("users", "full_name", "TEXT")
add_column_if_missing("users", "balance_usdt", "REAL DEFAULT 0")
add_column_if_missing("users", "balance_ton", "REAL DEFAULT 0")
add_column_if_missing("users", "created_at", "TEXT")
add_column_if_missing("users", "blocked", "INTEGER DEFAULT 0")

add_column_if_missing("transactions", "currency", "TEXT")
add_column_if_missing("transactions", "description", "TEXT")
add_column_if_missing("transactions", "created_at", "TEXT")

add_column_if_missing("requests", "currency", "TEXT")
add_column_if_missing("requests", "amount", "REAL")
add_column_if_missing("requests", "address", "TEXT")
add_column_if_missing("requests", "network", "TEXT")
add_column_if_missing("requests", "status", "TEXT")
add_column_if_missing("requests", "created_at", "TEXT")
add_column_if_missing("requests", "receipt_file_id", "TEXT")
add_column_if_missing("requests", "fee_percent", "REAL DEFAULT 0")
add_column_if_missing("requests", "fee_amount", "REAL DEFAULT 0")
add_column_if_missing("requests", "net_amount", "REAL DEFAULT 0")
add_column_if_missing("requests", "operation", "TEXT")
add_column_if_missing("requests", "country", "TEXT")
add_column_if_missing("requests", "bank", "TEXT")
add_column_if_missing("requests", "rate", "REAL DEFAULT 0")
add_column_if_missing("requests", "fiat_amount", "REAL DEFAULT 0")
add_column_if_missing("requests", "crypto_amount", "REAL DEFAULT 0")
add_column_if_missing("requests", "card_details", "TEXT")


cursor.execute("""
INSERT OR IGNORE INTO settings (key, value)
VALUES ('withdraw_fee_percent', '0')
""")

db.commit()


# =========================================================
# СОСТОЯНИЯ
# =========================================================

deposit_data = {}
withdraw_data = {}

deposit_amount_state = set()
deposit_waiting_receipt = set()

withdraw_amount_state = set()
withdraw_address_state = set()

support_state = set()

moderator_reply_to = {}

admin_balance_user_state = set()
admin_balance_amount_state = {}

admin_user_card_state = set()
admin_commission_state = set()

trade_data = {}
trade_amount_state = set()
trade_card_state = set()
trade_receipt_state = set()



# =========================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================================

def now():
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def escape_html(text):
    if text is None:
        return ""

    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def clear_user_state(user_id):

    deposit_data.pop(user_id, None)
    withdraw_data.pop(user_id, None)

    deposit_amount_state.discard(user_id)
    deposit_waiting_receipt.discard(user_id)

    withdraw_amount_state.discard(user_id)
    withdraw_address_state.discard(user_id)

    support_state.discard(user_id)

    trade_data.pop(user_id, None)
    trade_amount_state.discard(user_id)
    trade_card_state.discard(user_id)
    trade_receipt_state.discard(user_id)


def get_setting(key, default="0"):

    cursor.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,)
    )

    result = cursor.fetchone()

    if not result:
        return default

    return result[0]


def set_setting(key, value):

    cursor.execute("""
    INSERT INTO settings (key, value)
    VALUES (?, ?)
    ON CONFLICT(key)
    DO UPDATE SET value = excluded.value
    """, (
        key,
        str(value)
    ))

    db.commit()


def get_withdraw_fee_percent():

    try:
        return float(
            get_setting(
                "withdraw_fee_percent",
                "0"
            )
        )
    except ValueError:
        return 0.0


def ensure_user(message: Message):

    user_id = message.from_user.id

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    )

    if cursor.fetchone():

        cursor.execute("""
        UPDATE users
        SET username = ?, full_name = ?
        WHERE user_id = ?
        """, (
            message.from_user.username,
            message.from_user.full_name,
            user_id
        ))

    else:

        cursor.execute("""
        INSERT INTO users (
            user_id,
            username,
            full_name,
            balance_usdt,
            balance_ton,
            created_at,
            blocked
        )
        VALUES (?, ?, ?, 0, 0, ?, 0)
        """, (
            user_id,
            message.from_user.username,
            message.from_user.full_name,
            now()
        ))

    db.commit()


def ensure_user_by_id(user_id):

    cursor.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user_id,)
    )

    return cursor.fetchone() is not None


def is_blocked(user_id):

    if user_id == MODERATOR_ID:
        return False

    cursor.execute(
        "SELECT blocked FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cursor.fetchone()

    if not result:
        return False

    return bool(result[0])


def get_balance(user_id, currency):

    if currency == "USDT":
        column = "balance_usdt"

    elif currency == "TON":
        column = "balance_ton"

    else:
        return 0.0

    cursor.execute(
        f"SELECT {column} FROM users WHERE user_id = ?",
        (user_id,)
    )

    result = cursor.fetchone()

    if not result:
        return 0.0

    return float(result[0] or 0)


def get_deposit_address(currency, network):

    if currency == "USDT":

        if network == "TRC20":
            return USDT_TRC20_ADDRESS

        if network == "ERC20":
            return USDT_ERC20_ADDRESS

        if network == "BEP20":
            return USDT_BEP20_ADDRESS

        if network == "TON":
            return USDT_TON_ADDRESS

    if currency == "TON" and network == "TON":
        return TON_ADDRESS

    return ""


def is_moderator(user_id):
    return user_id == MODERATOR_ID


def format_amount(currency, amount):

    if currency == "TON":
        return f"{amount:.4f}"

    return f"{amount:.2f}"


def calculate_fee(amount):

    percent = get_withdraw_fee_percent()

    fee = amount * percent / 100
    net = amount - fee

    return percent, fee, net


# =========================================================
# BLOCK MIDDLEWARE
# =========================================================

class BlockedUserMiddleware(BaseMiddleware):

    async def __call__(
        self,
        handler,
        event,
        data
    ):

        user = getattr(event, "from_user", None)

        if user:

            user_id = user.id

            if user_id != MODERATOR_ID and is_blocked(user_id):

                if isinstance(event, CallbackQuery):

                    await event.answer(
                        "🚫 Ваш аккаунт заблокирован.",
                        show_alert=True
                    )

                elif isinstance(event, Message):

                    await event.answer(
                        "🚫 <b>Ваш аккаунт заблокирован.</b>\n\n"
                        "Вы не можете создавать операции "
                        "или пользоваться ботом.\n\n"
                        "Если вы считаете, что это ошибка — "
                        "обратитесь в поддержку.",
                        parse_mode="HTML"
                    )

                return

        return await handler(event, data)


dp.message.middleware(BlockedUserMiddleware())
dp.callback_query.middleware(BlockedUserMiddleware())


# =========================================================
# КЛАВИАТУРЫ
# =========================================================

def main_menu(user_id=None):

    keyboard = [
        [
            KeyboardButton(text="💰 Кошелёк"),
            KeyboardButton(text="➕ Пополнить"),
        ],
        [
            KeyboardButton(text="➖ Вывести"),
            KeyboardButton(text="🟢 Купить"),
        ],
        [
            KeyboardButton(text="🔴 Продать"),
            KeyboardButton(text="📜 История"),
        ],
        [
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="🆘 Поддержка"),
        ],
    ]

    if user_id == MODERATOR_ID:
        keyboard.append([
            KeyboardButton(text="👨‍💻 Админ-панель")
        ])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )


def only_main_menu():

    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🏠 Главное меню")
            ]
        ],
        resize_keyboard=True
    )


def currency_keyboard(action):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💵 USDT",
                    callback_data=f"{action}_USDT"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 TON",
                    callback_data=f"{action}_TON"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ]
        ]
    )


def usdt_network_keyboard(action):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔵 TRC20",
                    callback_data=f"{action}_USDT_TRC20"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🟣 ERC20",
                    callback_data=f"{action}_USDT_ERC20"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🟡 BEP20",
                    callback_data=f"{action}_USDT_BEP20"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💎 TON",
                    callback_data=f"{action}_USDT_TON"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ]
        ]
    )


def ton_network_keyboard(action):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💎 TON",
                    callback_data=f"{action}_TON_TON"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ]
        ]
    )


def paid_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Я оплатил",
                    callback_data="deposit_paid"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_operation"
                )
            ]
        ]
    )


def withdraw_confirm_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data="withdraw_confirm"
                )
            ],
            [
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="withdraw_cancel"
                )
            ]
        ]
    )


def moderator_request_keyboard(request_id, user_id):

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Подтвердить",
                    callback_data=f"approve:{request_id}"
                ),
                InlineKeyboardButton(
                    text="❌ Отклонить",
                    callback_data=f"reject:{request_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💬 Ответить пользователю",
                    callback_data=f"reply:{user_id}"
                )
            ]
        ]
    )


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start_handler(message: Message):

    ensure_user(message)
    clear_user_state(message.from_user.id)

    await message.answer(
        "🔥 <b>Добро пожаловать в PaltoPay!</b>\n\n"
        "💼 Ваш криптовалютный кошелёк.\n\n"
        "Выберите действие:",
        reply_markup=main_menu(message.from_user.id),
        parse_mode="HTML"
    )


# =========================================================
# ГЛАВНОЕ МЕНЮ
# =========================================================

@dp.message(F.text == "🏠 Главное меню")
async def main_menu_text(message: Message):

    clear_user_state(message.from_user.id)

    await message.answer(
        "🏠 <b>Главное меню</b>\n\n"
        "Выберите действие:",
        reply_markup=main_menu(message.from_user.id),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):

    await callback.answer()

    clear_user_state(callback.from_user.id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "🏠 <b>Главное меню</b>\n\n"
        "Выберите действие:",
        reply_markup=main_menu(callback.from_user.id),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "cancel_operation")
async def cancel_operation(callback: CallbackQuery):

    await callback.answer()

    clear_user_state(callback.from_user.id)

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "❌ Операция отменена.",
        reply_markup=main_menu(callback.from_user.id)
    )


# =========================================================
# КОШЕЛЁК
# =========================================================

@dp.message(F.text == "💰 Кошелёк")
async def wallet_handler(message: Message):

    ensure_user(message)

    usdt = get_balance(message.from_user.id, "USDT")
    ton = get_balance(message.from_user.id, "TON")

    await message.answer(
        "💰 <b>Ваш кошелёк</b>\n\n"
        f"💵 USDT: <b>{usdt:.2f}</b>\n"
        f"💎 TON: <b>{ton:.4f}</b>",
        reply_markup=only_main_menu(),
        parse_mode="HTML"
    )


# =========================================================
# ПОПОЛНЕНИЕ
# =========================================================

@dp.message(F.text == "➕ Пополнить")
async def deposit_start(message: Message):

    clear_user_state(message.from_user.id)

    await message.answer(
        "➕ <b>Пополнение</b>\n\n"
        f"Минимальная сумма: <b>{MIN_DEPOSIT:g}</b>\n\n"
        "Выберите криптовалюту:",
        reply_markup=currency_keyboard("deposit"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "deposit_USDT")
async def deposit_usdt(callback: CallbackQuery):

    await callback.answer()

    deposit_data[callback.from_user.id] = {
        "currency": "USDT"
    }

    await callback.message.edit_text(
        "💵 <b>USDT</b>\n\n"
        "Выберите сеть:",
        reply_markup=usdt_network_keyboard("deposit"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "deposit_TON")
async def deposit_ton(callback: CallbackQuery):

    await callback.answer()

    deposit_data[callback.from_user.id] = {
        "currency": "TON"
    }

    await callback.message.edit_text(
        "💎 <b>TON</b>\n\n"
        "Выберите сеть:",
        reply_markup=ton_network_keyboard("deposit"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("deposit_USDT_"))
async def deposit_usdt_network(callback: CallbackQuery):

    await callback.answer()

    network = callback.data.replace("deposit_USDT_", "")
    user_id = callback.from_user.id

    deposit_data[user_id] = {
        "currency": "USDT",
        "network": network
    }

    deposit_amount_state.add(user_id)

    await callback.message.edit_text(
        "💵 <b>USDT</b>\n\n"
        f"🌐 Сеть: <b>{network}</b>\n"
        f"📌 Минимум: <b>{MIN_DEPOSIT:g} USDT</b>\n\n"
        "Введите сумму пополнения:",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "deposit_TON_TON")
async def deposit_ton_network(callback: CallbackQuery):

    await callback.answer()

    user_id = callback.from_user.id

    deposit_data[user_id] = {
        "currency": "TON",
        "network": "TON"
    }

    deposit_amount_state.add(user_id)

    await callback.message.edit_text(
        "💎 <b>TON</b>\n\n"
        "🌐 Сеть: <b>TON</b>\n"
        f"📌 Минимум: <b>{MIN_DEPOSIT:g} TON</b>\n\n"
        "Введите сумму пополнения:",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "deposit_paid")
async def deposit_paid(callback: CallbackQuery):

    await callback.answer()

    user_id = callback.from_user.id

    if user_id not in deposit_data:

        await callback.message.answer(
            "❌ Операция не найдена.",
            reply_markup=only_main_menu()
        )

        return

    deposit_waiting_receipt.add(user_id)

    await callback.message.answer(
        "📸 <b>Теперь отправьте чек или скриншот оплаты.</b>\n\n"
        "Без подтверждения оплаты заявка модератору "
        "не отправится.",
        reply_markup=only_main_menu(),
        parse_mode="HTML"
    )


# =========================================================
# ВЫВОД
# =========================================================

@dp.message(F.text == "➖ Вывести")
async def withdraw_start(message: Message):

    clear_user_state(message.from_user.id)

    fee_percent = get_withdraw_fee_percent()

    await message.answer(
        "➖ <b>Вывод</b>\n\n"
        f"📌 Минимальная сумма вывода: "
        f"<b>{MIN_WITHDRAW:g}</b>\n\n"
        f"💸 Комиссия: <b>{fee_percent:g}%</b>\n\n"
        "⚠️ <b>Внимание:</b> при выводе может взиматься "
        "комиссия.\n\n"
        "Выберите криптовалюту:",
        reply_markup=currency_keyboard("withdraw"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "withdraw_USDT")
async def withdraw_usdt(callback: CallbackQuery):

    await callback.answer()

    fee_percent = get_withdraw_fee_percent()

    await callback.message.edit_text(
        "💵 <b>USDT</b>\n\n"
        f"💸 Комиссия: <b>{fee_percent:g}%</b>\n\n"
        "⚠️ При выводе может взиматься комиссия.\n\n"
        "Выберите сеть:",
        reply_markup=usdt_network_keyboard("withdraw"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "withdraw_TON")
async def withdraw_ton(callback: CallbackQuery):

    await callback.answer()

    fee_percent = get_withdraw_fee_percent()

    await callback.message.edit_text(
        "💎 <b>TON</b>\n\n"
        f"💸 Комиссия: <b>{fee_percent:g}%</b>\n\n"
        "⚠️ При выводе может взиматься комиссия.\n\n"
        "Выберите сеть:",
        reply_markup=ton_network_keyboard("withdraw"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("withdraw_USDT_"))
async def withdraw_usdt_network(callback: CallbackQuery):

    await callback.answer()

    network = callback.data.replace("withdraw_USDT_", "")
    user_id = callback.from_user.id

    withdraw_data[user_id] = {
        "currency": "USDT",
        "network": network
    }

    withdraw_amount_state.add(user_id)

    balance = get_balance(user_id, "USDT")
    fee_percent = get_withdraw_fee_percent()

    await callback.message.edit_text(
        "➖ <b>Вывод USDT</b>\n\n"
        f"🌐 Сеть: <b>{network}</b>\n"
        f"💰 Доступно: <b>{balance:.2f} USDT</b>\n"
        f"📌 Минимум: <b>{MIN_WITHDRAW:g} USDT</b>\n"
        f"💸 Комиссия: <b>{fee_percent:g}%</b>\n\n"
        "⚠️ При выводе может взиматься комиссия.\n\n"
        "Введите сумму:",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "withdraw_TON_TON")
async def withdraw_ton_network(callback: CallbackQuery):

    await callback.answer()

    user_id = callback.from_user.id

    withdraw_data[user_id] = {
        "currency": "TON",
        "network": "TON"
    }

    withdraw_amount_state.add(user_id)

    balance = get_balance(user_id, "TON")
    fee_percent = get_withdraw_fee_percent()

    await callback.message.edit_text(
        "➖ <b>Вывод TON</b>\n\n"
        "🌐 Сеть: <b>TON</b>\n"
        f"💰 Доступно: <b>{balance:.4f} TON</b>\n"
        f"📌 Минимум: <b>{MIN_WITHDRAW:g} TON</b>\n"
        f"💸 Комиссия: <b>{fee_percent:g}%</b>\n\n"
        "⚠️ При выводе может взиматься комиссия.\n\n"
        "Введите сумму:",
        parse_mode="HTML"
    )


# =========================================================
# ПОДТВЕРЖДЕНИЕ ВЫВОДА
# =========================================================

@dp.callback_query(F.data == "withdraw_confirm")
async def withdraw_confirm(callback: CallbackQuery):

    user_id = callback.from_user.id
    data = withdraw_data.get(user_id)

    if not data:

        await callback.answer(
            "❌ Данные вывода не найдены.",
            show_alert=True
        )

        return

    currency = data["currency"]
    network = data["network"]
    amount = data["amount"]
    address = data["address"]

    if amount < MIN_WITHDRAW:

        await callback.answer(
            f"Минимум — {MIN_WITHDRAW:g} {currency}",
            show_alert=True
        )

        clear_user_state(user_id)
        return

    balance = get_balance(user_id, currency)

    if amount > balance:

        await callback.answer(
            "❌ Недостаточно средств.",
            show_alert=True
        )

        clear_user_state(user_id)
        return

    fee_percent, fee_amount, net_amount = calculate_fee(amount)

    cursor.execute("""
    INSERT INTO requests (
        user_id,
        type,
        currency,
        amount,
        address,
        network,
        status,
        created_at,
        fee_percent,
        fee_amount,
        net_amount
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        "withdraw",
        currency,
        amount,
        address,
        network,
        "pending",
        now(),
        fee_percent,
        fee_amount,
        net_amount
    ))

    request_id = cursor.lastrowid

    db.commit()

    username = callback.from_user.username
    username_text = (
        f"@{username}"
        if username
        else "нет username"
    )

    try:

        await bot.send_message(
            MODERATOR_ID,
            "➖ <b>НОВАЯ ЗАЯВКА НА ВЫВОД</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"👤 {escape_html(callback.from_user.full_name)}\n"
            f"🔗 {escape_html(username_text)}\n"
            f"🆔 <code>{user_id}</code>\n\n"
            f"💰 Валюта: <b>{currency}</b>\n"
            f"🌐 Сеть: <b>{network}</b>\n\n"
            f"💵 Сумма вывода: "
            f"<b>{format_amount(currency, amount)}</b>\n"
            f"💸 Комиссия ({fee_percent:g}%): "
            f"<b>{format_amount(currency, fee_amount)}</b>\n"
            f"💳 К получению: "
            f"<b>{format_amount(currency, net_amount)}</b>\n\n"
            f"📍 Адрес:\n"
            f"<code>{escape_html(address)}</code>",
            reply_markup=moderator_request_keyboard(
                request_id,
                user_id
            ),
            parse_mode="HTML"
        )

    except Exception as e:

        print(
            f"Ошибка отправки заявки модератору: {e}"
        )

        cursor.execute(
            "DELETE FROM requests WHERE id = ?",
            (request_id,)
        )

        db.commit()

        await callback.answer(
            "❌ Не удалось отправить заявку.",
            show_alert=True
        )

        return

    await callback.answer("Заявка создана")

    await callback.message.answer(
        "✅ <b>Заявка создана!</b>\n\n"
        f"💰 Валюта: <b>{currency}</b>\n"
        f"🌐 Сеть: <b>{network}</b>\n\n"
        f"💵 Сумма вывода: "
        f"<b>{format_amount(currency, amount)}</b>\n"
        f"💸 Комиссия: "
        f"<b>{format_amount(currency, fee_amount)}</b>\n"
        f"💳 К получению: "
        f"<b>{format_amount(currency, net_amount)}</b>\n\n"
        "⚠️ При выводе может взиматься комиссия.\n\n"
        "Заявка отправлена модератору.",
        reply_markup=only_main_menu(),
        parse_mode="HTML"
    )

    clear_user_state(user_id)


@dp.callback_query(F.data == "withdraw_cancel")
async def withdraw_cancel(callback: CallbackQuery):

    await callback.answer()

    clear_user_state(callback.from_user.id)

    await callback.message.answer(
        "❌ Вывод отменён.",
        reply_markup=main_menu(callback.from_user.id)
    )


# =========================================================
# ПРОФИЛЬ
# =========================================================

@dp.message(F.text == "👤 Профиль")
async def profile(message: Message):

    ensure_user(message)

    username = message.from_user.username or "не указан"

    status = (
        "🚫 Заблокирован"
        if is_blocked(message.from_user.id)
        else "🟢 Активен"
    )

    await message.answer(
        "👤 <b>Профиль</b>\n\n"
        f"👤 Имя: <b>{escape_html(message.from_user.full_name)}</b>\n"
        f"🔗 Username: <b>@{escape_html(username)}</b>\n"
        f"🆔 ID: <code>{message.from_user.id}</code>\n"
        f"📊 Статус: <b>{status}</b>",
        reply_markup=only_main_menu(),
        parse_mode="HTML"
    )


# =========================================================
# ИСТОРИЯ
# =========================================================

@dp.message(F.text == "📜 История")
async def history(message: Message):

    cursor.execute("""
    SELECT type, currency, amount, description, created_at
    FROM transactions
    WHERE user_id = ?
    ORDER BY id DESC
    LIMIT 20
    """, (message.from_user.id,))

    rows = cursor.fetchall()

    if not rows:

        await message.answer(
            "📜 <b>История</b>\n\n"
            "Операций пока нет.",
            reply_markup=only_main_menu(),
            parse_mode="HTML"
        )

        return

    text = "📜 <b>История</b>\n\n"

    for row in rows:

        transaction_type = row[0]
        currency = row[1] or ""
        amount = row[2]
        description = row[3] or ""
        created = row[4]

        text += (
            f"• <b>{escape_html(transaction_type)}</b>\n"
            f"💰 {amount} {escape_html(currency)}\n"
            f"📝 {escape_html(description)}\n"
            f"🕐 {escape_html(created)}\n\n"
        )

    await message.answer(
        text,
        reply_markup=only_main_menu(),
        parse_mode="HTML"
    )


# =========================================================
# ПОДДЕРЖКА
# =========================================================

@dp.message(F.text == "🆘 Поддержка")
async def support(message: Message):

    clear_user_state(message.from_user.id)

    support_state.add(message.from_user.id)

    await message.answer(
        "🆘 <b>Поддержка</b>\n\n"
        "Напишите свой вопрос одним сообщением.\n\n"
        "Он будет отправлен модератору.",
        reply_markup=only_main_menu(),
        parse_mode="HTML"
    )


# =========================================================
# КУПИТЬ / ПРОДАТЬ
# =========================================================

def trade_currency_keyboard(action):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 USDT", callback_data=f"trade_{action}_USDT")],
        [InlineKeyboardButton(text="💎 TON", callback_data=f"trade_{action}_TON")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def trade_country_keyboard(action, currency):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🇺🇦 Украина", callback_data=f"trade_country_{action}_{currency}_UA")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"trade_back_currency_{action}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def trade_bank_keyboard(action, currency, country):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏦 SenseBank", callback_data=f"trade_bank_{action}_{currency}_{country}_SENSE")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"trade_back_country_{action}_{currency}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def trade_amount_mode_keyboard(action, currency):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🪙 Ввести количество {currency}", callback_data=f"trade_mode_crypto_{action}_{currency}")],
        [InlineKeyboardButton(text="💴 Ввести сумму в гривнах", callback_data=f"trade_mode_uah_{action}_{currency}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"trade_back_currency_{action}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])


def trade_confirm_keyboard(action):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Продолжить", callback_data=f"trade_confirm_{action}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")],
    ])


def trade_paid_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data="trade_buy_paid")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")],
    ])


def trade_sent_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Я отправил крипту", callback_data="trade_sell_sent")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")],
    ])


def trade_format(currency, amount):
    return f"{amount:.6f}".rstrip("0").rstrip(".") if currency == "TON" else f"{amount:.6f}".rstrip("0").rstrip(".")


def trade_rate(currency):
    return float(BUY_SELL_RATES.get(currency, 0))


def trade_summary(data):
    currency = data["currency"]
    rate = data["rate"]
    crypto = data["crypto_amount"]
    fiat = data["fiat_amount"]
    return (
        f"💰 Крипта: <b>{currency}</b>\n"
        f"🇺🇦 Страна: <b>Украина</b>\n"
        f"🏦 Банк: <b>SenseBank</b>\n"
        f"📈 Курс: <b>{rate:.2f} ₴</b> за 1 {currency}\n\n"
        f"🪙 Количество: <b>{trade_format(currency, crypto)} {currency}</b>\n"
        f"💴 Сумма: <b>{fiat:.2f} ₴</b>"
    )


@dp.message(F.text == "🟢 Купить")
async def buy(message: Message):
    user_id = message.from_user.id
    if user_id != MODERATOR_ID and is_blocked(user_id):
        await message.answer("🚫 <b>Ваш аккаунт заблокирован.</b>", parse_mode="HTML")
        return
    clear_user_state(user_id)
    trade_data[user_id] = {"action": "buy"}
    await message.answer(
        "🟢 <b>Покупка</b>\n\nВыберите криптовалюту:",
        reply_markup=trade_currency_keyboard("buy"),
        parse_mode="HTML"
    )


@dp.message(F.text == "🔴 Продать")
async def sell(message: Message):
    user_id = message.from_user.id
    if user_id != MODERATOR_ID and is_blocked(user_id):
        await message.answer("🚫 <b>Ваш аккаунт заблокирован.</b>", parse_mode="HTML")
        return
    clear_user_state(user_id)
    trade_data[user_id] = {"action": "sell"}
    await message.answer(
        "🔴 <b>Продажа</b>\n\nВыберите криптовалюту:",
        reply_markup=trade_currency_keyboard("sell"),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("trade_buy_USDT"))
@dp.callback_query(F.data.startswith("trade_buy_TON"))
@dp.callback_query(F.data.startswith("trade_sell_USDT"))
@dp.callback_query(F.data.startswith("trade_sell_TON"))
async def trade_currency_selected(callback: CallbackQuery):
    user_id = callback.from_user.id
    if user_id != MODERATOR_ID and is_blocked(user_id):
        await callback.answer("🚫 Аккаунт заблокирован.", show_alert=True)
        return
    parts = callback.data.split("_")
    action = parts[1]
    currency = parts[2]
    trade_data[user_id] = {"action": action, "currency": currency}
    await callback.answer()
    await callback.message.edit_text(
        f"{'🟢 Покупка' if action == 'buy' else '🔴 Продажа'} <b>{currency}</b>\n\nВыберите страну:",
        reply_markup=trade_country_keyboard(action, currency),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("trade_country_"))
async def trade_country_selected(callback: CallbackQuery):
    _, _, action, currency, country = callback.data.split("_")
    data = trade_data.get(callback.from_user.id)
    if not data:
        await callback.answer("Операция потеряна.", show_alert=True)
        return
    data["country"] = "Украина"
    await callback.answer()
    await callback.message.edit_text(
        f"{'🟢 Покупка' if action == 'buy' else '🔴 Продажа'} <b>{currency}</b>\n\n"
        "🇺🇦 Страна: <b>Украина</b>\n\nВыберите банк:",
        reply_markup=trade_bank_keyboard(action, currency, country),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("trade_bank_"))
async def trade_bank_selected(callback: CallbackQuery):
    _, _, action, currency, country, bank = callback.data.split("_")
    data = trade_data.get(callback.from_user.id)
    if not data:
        await callback.answer("Операция потеряна.", show_alert=True)
        return
    data["country"] = "Украина"
    data["bank"] = "SenseBank"
    data["rate"] = trade_rate(currency)
    await callback.answer()
    if data["rate"] <= 0:
        await callback.message.edit_text("⚠️ Курс для этой криптовалюты ещё не настроен.")
        return
    await callback.message.edit_text(
        f"{'🟢 Покупка' if action == 'buy' else '🔴 Продажа'} <b>{currency}</b>\n\n"
        "🇺🇦 Украина\n🏦 SenseBank\n"
        f"📈 Курс: <b>{data['rate']:.2f} ₴</b> за 1 {currency}\n\n"
        "Выберите, как хотите указать сумму:",
        reply_markup=trade_amount_mode_keyboard(action, currency),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("trade_mode_"))
async def trade_mode_selected(callback: CallbackQuery):
    _, _, mode, action, currency = callback.data.split("_")
    data = trade_data.get(callback.from_user.id)
    if not data:
        await callback.answer("Операция потеряна.", show_alert=True)
        return
    data["input_mode"] = mode
    trade_amount_state.add(callback.from_user.id)
    await callback.answer()
    if mode == "crypto":
        prompt = f"🪙 Введите количество <b>{currency}</b>:\n\nНапример: <code>100</code>"
    else:
        prompt = "💴 Введите сумму в гривнах:\n\nНапример: <code>5000</code>"
    await callback.message.edit_text(prompt, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="trade_cancel")]
    ]), parse_mode="HTML")


@dp.callback_query(F.data.startswith("trade_back_currency_"))
async def trade_back_currency(callback: CallbackQuery):
    action = callback.data.rsplit("_", 1)[1]
    await callback.answer()
    await callback.message.edit_text(
        "Выберите криптовалюту:",
        reply_markup=trade_currency_keyboard(action),
    )


@dp.callback_query(F.data.startswith("trade_back_country_"))
async def trade_back_country(callback: CallbackQuery):
    _, _, _, action, currency = callback.data.split("_")
    await callback.answer()
    await callback.message.edit_text(
        "Выберите страну:",
        reply_markup=trade_country_keyboard(action, currency),
    )


@dp.callback_query(F.data == "trade_cancel")
async def trade_cancel(callback: CallbackQuery):
    clear_user_state(callback.from_user.id)
    await callback.answer("Операция отменена")
    await callback.message.edit_text("❌ Операция отменена.")
    await callback.message.answer("🏠 <b>Главное меню</b>", reply_markup=main_menu(callback.from_user.id), parse_mode="HTML")


@dp.callback_query(F.data == "trade_confirm_buy")
async def trade_confirm_buy(callback: CallbackQuery):
    data = trade_data.get(callback.from_user.id)
    if not data:
        await callback.answer("Операция потеряна.", show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(
        "💳 <b>Реквизиты для оплаты</b>\n\n"
        f"🏦 Банк: <b>SenseBank</b>\n"
        f"💳 Карта: <code>{escape_html(BUY_CARD_NUMBER)}</code>\n"
        f"💵 К оплате: <b>{data['fiat_amount']:.2f} ₴</b>\n\n"
        "После перевода нажмите «✅ Я оплатил» и отправьте чек/скриншот.",
        reply_markup=trade_paid_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "trade_confirm_sell")
async def trade_confirm_sell(callback: CallbackQuery):
    data = trade_data.get(callback.from_user.id)
    if not data:
        await callback.answer("Операция потеряна.", show_alert=True)
        return
    await callback.answer()
    trade_card_state.add(callback.from_user.id)
    await callback.message.edit_text(
        "💳 <b>Введите номер карты для получения гривен</b>\n\n"
        "Укажите реквизиты карты SenseBank, на которую нужно отправить выплату.",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "trade_sell_continue_crypto")
async def trade_sell_continue_crypto(callback: CallbackQuery):
    data = trade_data.get(callback.from_user.id)
    if not data:
        await callback.answer("Операция потеряна.", show_alert=True)
        return
    await callback.answer()
    address = SELL_USDT_ADDRESS if data["currency"] == "USDT" else SELL_TON_ADDRESS
    if not address:
        await callback.message.edit_text(
            "⚠️ <b>Реквизиты для приёма крипты ещё не настроены.</b>\n\n"
            "Модератору нужно добавить адрес для этой валюты.",
            parse_mode="HTML"
        )
        return
    data["sell_address"] = address
    await callback.message.edit_text(
        "📤 <b>Отправьте криптовалюту</b>\n\n"
        f"💰 Валюта: <b>{data['currency']}</b>\n"
        f"🪙 Сумма: <b>{trade_format(data['currency'], data['crypto_amount'])} {data['currency']}</b>\n"
        f"🌐 Сеть: <b>{'TRC20' if data['currency'] == 'USDT' else 'TON'}</b>\n\n"
        f"📍 Адрес:\n<code>{escape_html(address)}</code>\n\n"
        "После отправки нажмите «✅ Я отправил крипту», затем отправьте чек/скриншот.",
        reply_markup=trade_sent_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "trade_buy_paid")
async def trade_buy_paid(callback: CallbackQuery):
    trade_receipt_state.add(callback.from_user.id)
    await callback.answer()
    await callback.message.edit_text(
        "📸 <b>Отправьте чек или скриншот оплаты.</b>",
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "trade_sell_sent")
async def trade_sell_sent(callback: CallbackQuery):
    trade_receipt_state.add(callback.from_user.id)
    await callback.answer()
    await callback.message.edit_text(
        "📸 <b>Отправьте чек или скриншот перевода криптовалюты.</b>",
        parse_mode="HTML"
    )


# =========================================================
# МОДЕРАТОР — ОТВЕТ
# =========================================================

@dp.callback_query(F.data.startswith("reply:"))
async def moderator_reply(callback: CallbackQuery):

    if callback.from_user.id != MODERATOR_ID:

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    try:
        user_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):

        await callback.answer(
            "❌ Ошибка пользователя.",
            show_alert=True
        )

        return

    moderator_reply_to[MODERATOR_ID] = user_id

    await callback.answer("Напишите ответ")

    await callback.message.answer(
        "💬 <b>Ответ пользователю</b>\n\n"
        f"🆔 ID: <code>{user_id}</code>\n\n"
        "Отправьте сообщение следующим сообщением:",
        parse_mode="HTML"
    )


# =========================================================
# МОДЕРАТОР — ПОДТВЕРДИТЬ
# =========================================================

@dp.callback_query(F.data.startswith("approve:"))
async def approve(callback: CallbackQuery):

    if callback.from_user.id != MODERATOR_ID:

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    try:
        request_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):

        await callback.answer(
            "❌ Неверный ID заявки.",
            show_alert=True
        )

        return

    cursor.execute("""
    SELECT
        user_id,
        type,
        currency,
        amount,
        address,
        network,
        status,
        fee_percent,
        fee_amount,
        net_amount,
        rate,
        fiat_amount,
        crypto_amount
    FROM requests
    WHERE id = ?
    """, (request_id,))

    request = cursor.fetchone()

    if not request:

        await callback.answer(
            "Заявка не найдена.",
            show_alert=True
        )

        return

    (
        user_id,
        request_type,
        currency,
        amount,
        address,
        network,
        status,
        fee_percent,
        fee_amount,
        net_amount,
        rate,
        fiat_amount,
        crypto_amount
    ) = request

    if status != "pending":

        await callback.answer(
            "Заявка уже обработана.",
            show_alert=True
        )

        return

    # =====================================================
    # ПОПОЛНЕНИЕ
    # =====================================================

    if request_type == "deposit":

        if currency == "USDT":

            cursor.execute("""
            UPDATE users
            SET balance_usdt = balance_usdt + ?
            WHERE user_id = ?
            """, (
                amount,
                user_id
            ))

        elif currency == "TON":

            cursor.execute("""
            UPDATE users
            SET balance_ton = balance_ton + ?
            WHERE user_id = ?
            """, (
                amount,
                user_id
            ))

        cursor.execute("""
        INSERT INTO transactions (
            user_id,
            type,
            currency,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            "Пополнение",
            currency,
            amount,
            f"{currency} / {network} / заявка #{request_id}",
            now()
        ))

        cursor.execute("""
        UPDATE requests
        SET status = 'approved'
        WHERE id = ?
        """, (request_id,))

        db.commit()

        new_balance = get_balance(
            user_id,
            currency
        )

        # ВАЖНО:
        # Отправляем сообщение пользователю отдельно.
        try:

            await bot.send_message(
                user_id,
                "✅ <b>Пополнение подтверждено!</b>\n\n"
                f"📋 Заявка: <b>#{request_id}</b>\n"
                f"💰 Валюта: <b>{currency}</b>\n"
                f"🌐 Сеть: <b>{network}</b>\n"
                f"💵 Зачислено: "
                f"<b>{format_amount(currency, amount)}</b>\n\n"
                f"💳 Ваш баланс: "
                f"<b>{format_amount(currency, new_balance)}</b> "
                f"{currency}",
                reply_markup=only_main_menu(),
                parse_mode="HTML"
            )

            user_sent = True

        except Exception as e:

            print(
                f"Ошибка отправки подтверждения "
                f"пользователю {user_id}: {e}"
            )

            user_sent = False

        await callback.message.answer(
            "✅ <b>Пополнение подтверждено.</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"💰 {amount} {currency}\n"
            f"💳 Новый баланс: "
            f"{format_amount(currency, new_balance)} {currency}\n\n"
            + (
                "📨 Пользователь уведомлён."
                if user_sent
                else
                "⚠️ Не удалось отправить уведомление "
                "пользователю."
            ),
            parse_mode="HTML"
        )

    # =====================================================
    # КУПИТЬ / ПРОДАТЬ
    # =====================================================

    elif request_type in ("trade_buy", "trade_sell"):

        operation = "Покупка" if request_type == "trade_buy" else "Продажа"
        cursor.execute("""
            INSERT INTO transactions (user_id, type, currency, amount, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            operation,
            currency,
            amount,
            f"{currency} / Украина / SenseBank / заявка #{request_id}",
            now()
        ))

        # При покупке после подтверждения зачисляем крипту на баланс.
        if request_type == "trade_buy":
            if currency == "USDT":
                cursor.execute("UPDATE users SET balance_usdt = balance_usdt + ? WHERE user_id = ?", (amount, user_id))
            elif currency == "TON":
                cursor.execute("UPDATE users SET balance_ton = balance_ton + ? WHERE user_id = ?", (amount, user_id))

        cursor.execute("UPDATE requests SET status = 'approved' WHERE id = ?", (request_id,))
        db.commit()

        if request_type == "trade_buy":
            new_balance = get_balance(user_id, currency)
            user_text = (
                "✅ <b>Покупка подтверждена!</b>\n\n"
                f"📋 Заявка: <b>#{request_id}</b>\n"
                f"💰 {currency}: <b>{format_amount(currency, amount)}</b>\n"
                f"💴 Оплачено: <b>{fiat_amount:.2f} ₴</b>\n"
                f"📈 Курс: <b>{rate:.2f} ₴</b>\n\n"
                f"💳 Новый баланс: <b>{format_amount(currency, new_balance)} {currency}</b>"
            )
        else:
            user_text = (
                "✅ <b>Продажа подтверждена!</b>\n\n"
                f"📋 Заявка: <b>#{request_id}</b>\n"
                f"💰 Продано: <b>{format_amount(currency, amount)} {currency}</b>\n"
                f"💴 К получению: <b>{fiat_amount:.2f} ₴</b>\n"
                f"📈 Курс: <b>{rate:.2f} ₴</b>\n\n"
                "Модератор подтвердил операцию. Выплата производится по указанным реквизитам."
            )
        try:
            await bot.send_message(user_id, user_text, reply_markup=only_main_menu(), parse_mode="HTML")
            sent = True
        except Exception as e:
            print(f"Ошибка уведомления по торговой заявке #{request_id}: {e}")
            sent = False

        await callback.message.answer(
            f"✅ <b>{operation} подтверждена.</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"💰 {format_amount(currency, amount)} {currency}\n"
            f"💴 {fiat_amount:.2f} ₴\n\n"
            + ("📨 Пользователь уведомлён." if sent else "⚠️ Не удалось уведомить пользователя."),
            parse_mode="HTML"
        )
        await callback.answer("Готово")
        return

    # =====================================================
    # ВЫВОД
    # =====================================================

    elif request_type == "withdraw":

        balance = get_balance(
            user_id,
            currency
        )

        if amount > balance:

            await callback.answer(
                "❌ У пользователя недостаточно средств.",
                show_alert=True
            )

            return

        if currency == "USDT":

            cursor.execute("""
            UPDATE users
            SET balance_usdt = balance_usdt - ?
            WHERE user_id = ?
            """, (
                amount,
                user_id
            ))

        elif currency == "TON":

            cursor.execute("""
            UPDATE users
            SET balance_ton = balance_ton - ?
            WHERE user_id = ?
            """, (
                amount,
                user_id
            ))

        cursor.execute("""
        INSERT INTO transactions (
            user_id,
            type,
            currency,
            amount,
            description,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            "Вывод",
            currency,
            amount,
            (
                f"{currency} / {network} / "
                f"заявка #{request_id} / "
                f"комиссия {fee_amount}"
            ),
            now()
        ))

        cursor.execute("""
        UPDATE requests
        SET status = 'approved'
        WHERE id = ?
        """, (request_id,))

        db.commit()

        try:

            await bot.send_message(
                user_id,
                "✅ <b>Вывод подтверждён!</b>\n\n"
                f"📋 Заявка: <b>#{request_id}</b>\n"
                f"💰 Валюта: <b>{currency}</b>\n"
                f"🌐 Сеть: <b>{network}</b>\n\n"
                f"💵 Сумма вывода: "
                f"<b>{format_amount(currency, amount)}</b>\n"
                f"💸 Комиссия ({fee_percent:g}%): "
                f"<b>{format_amount(currency, fee_amount)}</b>\n"
                f"💳 К получению: "
                f"<b>{format_amount(currency, net_amount)}</b>\n\n"
                "Средства отправлены по указанному адресу.",
                reply_markup=only_main_menu(),
                parse_mode="HTML"
            )

            user_sent = True

        except Exception as e:

            print(
                f"Ошибка отправки уведомления "
                f"о выводе пользователю {user_id}: {e}"
            )

            user_sent = False

        await callback.message.answer(
            "✅ <b>Вывод подтверждён.</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"💵 Вывод: "
            f"<b>{format_amount(currency, amount)}</b> {currency}\n"
            f"💸 Комиссия: "
            f"<b>{format_amount(currency, fee_amount)}</b> {currency}\n"
            f"💳 К получению: "
            f"<b>{format_amount(currency, net_amount)}</b> {currency}\n\n"
            + (
                "📨 Пользователь уведомлён."
                if user_sent
                else
                "⚠️ Не удалось отправить уведомление "
                "пользователю."
            ),
            parse_mode="HTML"
        )

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.answer("Готово")


# =========================================================
# МОДЕРАТОР — ОТКЛОНИТЬ
# =========================================================

@dp.callback_query(F.data.startswith("reject:"))
async def reject(callback: CallbackQuery):

    if callback.from_user.id != MODERATOR_ID:

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    try:
        request_id = int(
            callback.data.split(":")[1]
        )
    except (ValueError, IndexError):

        await callback.answer(
            "❌ Неверный ID заявки.",
            show_alert=True
        )

        return

    cursor.execute("""
    SELECT
        user_id,
        type,
        currency,
        amount,
        network,
        status
    FROM requests
    WHERE id = ?
    """, (request_id,))

    request = cursor.fetchone()

    if not request:

        await callback.answer(
            "Заявка не найдена.",
            show_alert=True
        )

        return

    (
        user_id,
        request_type,
        currency,
        amount,
        network,
        status
    ) = request

    if status != "pending":

        await callback.answer(
            "Заявка уже обработана.",
            show_alert=True
        )

        return

    cursor.execute("""
    UPDATE requests
    SET status = 'rejected'
    WHERE id = ?
    """, (request_id,))

    db.commit()

    try:

        await bot.send_message(
            user_id,
            "❌ <b>Заявка отклонена.</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"💰 {amount} {currency}\n"
            f"🌐 Сеть: {network}\n\n"
            "Если это ошибка — обратитесь в поддержку.",
            reply_markup=only_main_menu(),
            parse_mode="HTML"
        )

        user_sent = True

    except Exception as e:

        print(
            f"Ошибка отправки отклонения "
            f"пользователю {user_id}: {e}"
        )

        user_sent = False

    try:
        await callback.message.edit_reply_markup(
            reply_markup=None
        )
    except Exception:
        pass

    await callback.message.answer(
        f"❌ <b>Заявка #{request_id} отклонена.</b>\n\n"
        + (
            "📨 Пользователь уведомлён."
            if user_sent
            else
            "⚠️ Не удалось отправить уведомление."
        ),
        parse_mode="HTML"
    )

    await callback.answer("Отклонено")


# =========================================================
# АДМИНКА
# =========================================================

def admin_menu():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📥 Пополнения",
                    callback_data="admin_deposits"
                ),
                InlineKeyboardButton(
                    text="📤 Выводы",
                    callback_data="admin_withdrawals"
                )
            ],
            [
                InlineKeyboardButton(
                    text="👥 Пользователи",
                    callback_data="admin_users"
                ),
                InlineKeyboardButton(
                    text="💰 Балансы",
                    callback_data="admin_balances"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📊 Статистика",
                    callback_data="admin_stats"
                ),
                InlineKeyboardButton(
                    text="🔎 Пользователь",
                    callback_data="admin_user_card"
                )
            ],
            [
                InlineKeyboardButton(
                    text="💸 Комиссия",
                    callback_data="admin_commission"
                )
            ],
            [
                InlineKeyboardButton(
                    text="📜 Все заявки",
                    callback_data="admin_requests"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ]
        ]
    )


def admin_back_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Админ-панель",
                    callback_data="admin_home"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🏠 Главное меню",
                    callback_data="main_menu"
                )
            ]
        ]
    )


def admin_request_list_keyboard(rows):

    buttons = []

    for (
        request_id,
        request_type,
        currency,
        amount,
        network,
        created_at
    ) in rows:

        icon = (
            "➕"
            if request_type == "deposit"
            else "➖"
        )

        buttons.append([
            InlineKeyboardButton(
                text=(
                    f"{icon} #{request_id} • "
                    f"{amount} {currency} • "
                    f"{network or '—'}"
                ),
                callback_data=f"admin_request:{request_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="⬅️ Админ-панель",
            callback_data="admin_home"
        )
    ])

    return InlineKeyboardMarkup(
        inline_keyboard=buttons
    )


# =========================================================
# АДМИН — ГЛАВНАЯ
# =========================================================

@dp.message(F.text == "👨‍💻 Админ-панель")
async def admin_panel_message(message: Message):

    if not is_moderator(message.from_user.id):

        await message.answer("⛔ Нет доступа.")
        return

    clear_user_state(message.from_user.id)

    await message.answer(
        "👨‍💻 <b>Админ-панель</b>\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )


@dp.message(F.text == "/admin")
async def admin_command(message: Message):

    if not is_moderator(message.from_user.id):

        await message.answer("⛔ Нет доступа.")
        return

    clear_user_state(message.from_user.id)

    await message.answer(
        "👨‍💻 <b>Админ-панель</b>\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data == "admin_home")
async def admin_home(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    admin_balance_user_state.discard(
        callback.from_user.id
    )

    admin_balance_amount_state.pop(
        callback.from_user.id,
        None
    )

    admin_user_card_state.discard(
        callback.from_user.id
    )

    admin_commission_state.discard(
        callback.from_user.id
    )

    await callback.answer()

    await callback.message.edit_text(
        "👨‍💻 <b>Админ-панель</b>\n\n"
        "Выберите раздел:",
        reply_markup=admin_menu(),
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — СТАТИСТИКА
# =========================================================

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )

    users_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(amount), 0)
        FROM requests
        WHERE type = 'deposit'
        AND status = 'approved'
    """)

    deposit_count, deposit_sum = cursor.fetchone()

    cursor.execute("""
        SELECT
            COUNT(*),
            COALESCE(SUM(amount), 0)
        FROM requests
        WHERE type = 'withdraw'
        AND status = 'approved'
    """)

    withdraw_count, withdraw_sum = cursor.fetchone()

    cursor.execute("""
        SELECT
            COALESCE(SUM(balance_usdt), 0),
            COALESCE(SUM(balance_ton), 0)
        FROM users
    """)

    total_usdt, total_ton = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*)
        FROM requests
        WHERE status = 'pending'
    """)

    pending = cursor.fetchone()[0]

    blocked = cursor.execute("""
        SELECT COUNT(*)
        FROM users
        WHERE blocked = 1
    """).fetchone()[0]

    fee_percent = get_withdraw_fee_percent()

    await callback.answer()

    await callback.message.edit_text(
        "📊 <b>Статистика PaltoPay</b>\n\n"
        f"👥 Пользователей: <b>{users_count}</b>\n"
        f"🚫 Заблокировано: <b>{blocked}</b>\n\n"
        f"➕ Пополнений: <b>{deposit_count}</b>\n"
        f"💰 Сумма пополнений: "
        f"<b>{deposit_sum:.2f}</b>\n\n"
        f"➖ Выводов: <b>{withdraw_count}</b>\n"
        f"💰 Сумма выводов: "
        f"<b>{withdraw_sum:.2f}</b>\n\n"
        f"💵 USDT на балансах: "
        f"<b>{total_usdt:.2f}</b>\n"
        f"💎 TON на балансах: "
        f"<b>{total_ton:.4f}</b>\n\n"
        f"📋 Ожидающих заявок: <b>{pending}</b>\n"
        f"💸 Комиссия: <b>{fee_percent:g}%</b>",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — КОМИССИЯ
# =========================================================

@dp.callback_query(F.data == "admin_commission")
async def admin_commission(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    current = get_withdraw_fee_percent()

    admin_commission_state.add(
        callback.from_user.id
    )

    await callback.answer()

    await callback.message.edit_text(
        "💸 <b>Комиссия при выводе</b>\n\n"
        f"Текущая комиссия: <b>{current:g}%</b>\n\n"
        "Введите новый процент.\n\n"
        "Например:\n"
        "<code>2.5</code>\n"
        "<code>5</code>\n"
        "<code>0</code> — отключить комиссию.",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — ПОПОЛНЕНИЯ
# =========================================================

@dp.callback_query(F.data == "admin_deposits")
async def admin_deposits(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    cursor.execute("""
        SELECT id, type, currency, amount, network, created_at
        FROM requests
        WHERE status = 'pending'
        AND type = 'deposit'
        ORDER BY id DESC
        LIMIT 50
    """)

    rows = cursor.fetchall()

    await callback.answer()

    if not rows:

        await callback.message.edit_text(
            "📥 <b>Ожидающие пополнения</b>\n\n"
            "Нет новых заявок.",
            reply_markup=admin_back_keyboard(),
            parse_mode="HTML"
        )

        return

    await callback.message.edit_text(
        "📥 <b>Ожидающие пополнения</b>\n\n"
        "Выберите заявку:",
        reply_markup=admin_request_list_keyboard(rows),
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — ВЫВОДЫ
# =========================================================

@dp.callback_query(F.data == "admin_withdrawals")
async def admin_withdrawals(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    cursor.execute("""
        SELECT id, type, currency, amount, network, created_at
        FROM requests
        WHERE status = 'pending'
        AND type = 'withdraw'
        ORDER BY id DESC
        LIMIT 50
    """)

    rows = cursor.fetchall()

    await callback.answer()

    if not rows:

        await callback.message.edit_text(
            "📤 <b>Ожидающие выводы</b>\n\n"
            "Нет новых заявок.",
            reply_markup=admin_back_keyboard(),
            parse_mode="HTML"
        )

        return

    await callback.message.edit_text(
        "📤 <b>Ожидающие выводы</b>\n\n"
        "Выберите заявку:",
        reply_markup=admin_request_list_keyboard(rows),
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — ЗАЯВКА
# =========================================================

@dp.callback_query(F.data.startswith("admin_request:"))
async def admin_request_detail(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    request_id = int(
        callback.data.split(":", 1)[1]
    )

    cursor.execute("""
        SELECT
            r.id,
            r.user_id,
            r.type,
            r.currency,
            r.amount,
            r.address,
            r.network,
            r.status,
            r.created_at,
            r.receipt_file_id,
            r.fee_percent,
            r.fee_amount,
            r.net_amount,
            r.rate,
            r.fiat_amount,
            r.crypto_amount,
            r.card_details,
            r.country,
            r.bank,
            u.username,
            u.full_name
        FROM requests r
        LEFT JOIN users u
        ON u.user_id = r.user_id
        WHERE r.id = ?
    """, (request_id,))

    row = cursor.fetchone()

    await callback.answer()

    if not row:

        await callback.message.edit_text(
            "❌ Заявка не найдена.",
            reply_markup=admin_back_keyboard()
        )

        return

    (
        rid,
        user_id,
        request_type,
        currency,
        amount,
        address,
        network,
        status,
        created_at,
        receipt_file_id,
        fee_percent,
        fee_amount,
        net_amount,
        rate,
        fiat_amount,
        crypto_amount,
        card_details,
        country,
        bank,
        username,
        full_name
    ) = row

    type_text = {
        "deposit": "Пополнение",
        "withdraw": "Вывод",
        "trade_buy": "🟢 Покупка",
        "trade_sell": "🔴 Продажа",
    }.get(request_type, request_type)

    username_text = (
        f"@{username}"
        if username
        else "нет username"
    )

    status_text = {
        "pending": "⏳ ожидает",
        "approved": "✅ подтверждена",
        "rejected": "❌ отклонена"
    }.get(status, status)

    text = (
        f"📋 <b>Заявка #{rid}</b>\n\n"
        f"Тип: <b>{type_text}</b>\n"
        f"👤 {escape_html(full_name or 'неизвестно')}\n"
        f"🔗 {escape_html(username_text)}\n"
        f"🆔 <code>{user_id}</code>\n\n"
        f"💰 Валюта: <b>{currency}</b>\n"
        f"🌐 Сеть: <b>{network or '—'}</b>\n"
        f"💵 Сумма: <b>{amount}</b>\n"
    )

    if request_type == "withdraw":

        text += (
            f"💸 Комиссия: "
            f"<b>{fee_percent or 0:g}%</b>\n"
            f"💸 Сумма комиссии: "
            f"<b>{fee_amount or 0}</b> {currency}\n"
            f"💳 К получению: "
            f"<b>{net_amount or 0}</b> {currency}\n"
        )

    if request_type in ("trade_buy", "trade_sell"):
        text += (
            f"🇺🇦 Страна: <b>{country or 'Украина'}</b>\n"
            f"🏦 Банк: <b>{bank or 'SenseBank'}</b>\n"
            f"📈 Курс: <b>{rate or 0:.2f} ₴</b>\n"
            f"🪙 Крипта: <b>{crypto_amount or amount}</b> {currency}\n"
            f"💴 Сумма: <b>{fiat_amount or 0:.2f} ₴</b>\n"
            f"💳 Реквизиты пользователя: <code>{escape_html(card_details or '—')}</code>\n"
        )

    text += (
        f"📍 Адрес: "
        f"<code>{escape_html(address or '—')}</code>\n"
        f"📊 Статус: <b>{status_text}</b>\n"
        f"🕐 {created_at}"
    )

    if status == "pending":

        markup = moderator_request_keyboard(
            rid,
            user_id
        )

    else:

        markup = admin_back_keyboard()

    if receipt_file_id:

        try:

            await callback.message.answer_photo(
                receipt_file_id,
                caption=text,
                reply_markup=markup,
                parse_mode="HTML"
            )

            return

        except Exception as e:

            print(
                f"Ошибка отправки чека: {e}"
            )

    await callback.message.edit_text(
        text,
        reply_markup=markup,
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — ПОЛЬЗОВАТЕЛИ
# =========================================================

@dp.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    cursor.execute(
        "SELECT COUNT(*) FROM users"
    )

    total = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            user_id,
            username,
            full_name,
            balance_usdt,
            balance_ton,
            blocked
        FROM users
        ORDER BY user_id DESC
        LIMIT 20
    """)

    rows = cursor.fetchall()

    text = (
        f"👥 <b>Пользователи</b>\n\n"
        f"Всего: <b>{total}</b>\n\n"
    )

    for (
        uid,
        username,
        full_name,
        usdt,
        ton,
        blocked
    ) in rows:

        uname = (
            f"@{username}"
            if username
            else "без username"
        )

        status = "🚫" if blocked else "🟢"

        text += (
            f"{status} 👤 "
            f"{escape_html(full_name or '—')} "
            f"({escape_html(uname)})\n"
            f"🆔 <code>{uid}</code>\n"
            f"💵 {usdt or 0:.2f} USDT\n"
            f"💎 {ton or 0:.4f} TON\n\n"
        )

    await callback.answer()

    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — КАРТОЧКА ПОЛЬЗОВАТЕЛЯ
# =========================================================

def user_card_keyboard(
    user_id,
    blocked
):

    block_button = (
        InlineKeyboardButton(
            text="🔓 Разблокировать",
            callback_data=f"unblock:{user_id}"
        )
        if blocked
        else
        InlineKeyboardButton(
            text="🚫 Заблокировать",
            callback_data=f"block:{user_id}"
        )
    )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [block_button],
            [
                InlineKeyboardButton(
                    text="➕ USDT",
                    callback_data=(
                        f"admin_balance_change:"
                        f"{user_id}:USDT:plus"
                    )
                ),
                InlineKeyboardButton(
                    text="➖ USDT",
                    callback_data=(
                        f"admin_balance_change:"
                        f"{user_id}:USDT:minus"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="➕ TON",
                    callback_data=(
                        f"admin_balance_change:"
                        f"{user_id}:TON:plus"
                    )
                ),
                InlineKeyboardButton(
                    text="➖ TON",
                    callback_data=(
                        f"admin_balance_change:"
                        f"{user_id}:TON:minus"
                    )
                )
            ],
            [
                InlineKeyboardButton(
                    text="⬅️ Админ-панель",
                    callback_data="admin_home"
                )
            ]
        ]
    )


async def send_user_card(
    target_message,
    user_id,
    edit=True
):

    cursor.execute("""
        SELECT
            user_id,
            username,
            full_name,
            balance_usdt,
            balance_ton,
            blocked
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    user = cursor.fetchone()

    if not user:

        text = "❌ Пользователь не найден."

        if edit:
            await target_message.edit_text(
                text,
                reply_markup=admin_back_keyboard()
            )
        else:
            await target_message.answer(text)

        return

    (
        uid,
        username,
        full_name,
        usdt,
        ton,
        blocked
    ) = user

    cursor.execute("""
        SELECT
            COUNT(*)
        FROM requests
        WHERE user_id = ?
        AND type = 'deposit'
        AND status = 'approved'
    """, (user_id,))

    deposit_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            COUNT(*)
        FROM requests
        WHERE user_id = ?
        AND type = 'withdraw'
        AND status = 'approved'
    """, (user_id,))

    withdraw_count = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            type,
            currency,
            amount,
            description,
            created_at
        FROM transactions
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 5
    """, (user_id,))

    transactions = cursor.fetchall()

    status = (
        "🚫 Заблокирован"
        if blocked
        else "🟢 Активен"
    )

    username_text = (
        f"@{username}"
        if username
        else "нет username"
    )

    text = (
        "🔎 <b>Карточка пользователя</b>\n\n"
        f"👤 Имя: <b>{escape_html(full_name or '—')}</b>\n"
        f"🔗 Username: <b>{escape_html(username_text)}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📊 Статус: <b>{status}</b>\n\n"
        f"💵 USDT: <b>{usdt or 0:.2f}</b>\n"
        f"💎 TON: <b>{ton or 0:.4f}</b>\n\n"
        f"➕ Пополнений: <b>{deposit_count}</b>\n"
        f"➖ Выводов: <b>{withdraw_count}</b>\n\n"
        "📜 <b>Последние операции:</b>\n"
    )

    if not transactions:

        text += "Операций нет."

    else:

        for (
            tx_type,
            currency,
            amount,
            description,
            created_at
        ) in transactions:

            text += (
                f"• {escape_html(tx_type)} — "
                f"<b>{amount} {escape_html(currency)}</b>\n"
                f"  🕐 {escape_html(created_at)}\n"
            )

    markup = user_card_keyboard(
        uid,
        bool(blocked)
    )

    if edit:

        await target_message.edit_text(
            text,
            reply_markup=markup,
            parse_mode="HTML"
        )

    else:

        await target_message.answer(
            text,
            reply_markup=markup,
            parse_mode="HTML"
        )


@dp.callback_query(F.data == "admin_user_card")
async def admin_user_card_start(
    callback: CallbackQuery
):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    admin_user_card_state.add(
        callback.from_user.id
    )

    await callback.answer()

    await callback.message.edit_text(
        "🔎 <b>Карточка пользователя</b>\n\n"
        "Отправьте ID пользователя числом.",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# БЛОКИРОВКА
# =========================================================

@dp.callback_query(F.data.startswith("block:"))
async def block_user(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    user_id = int(
        callback.data.split(":")[1]
    )

    if user_id == MODERATOR_ID:

        await callback.answer(
            "❌ Нельзя заблокировать администратора.",
            show_alert=True
        )

        return

    cursor.execute("""
        SELECT user_id
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    if not cursor.fetchone():

        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )

        return

    cursor.execute("""
        UPDATE users
        SET blocked = 1
        WHERE user_id = ?
    """, (user_id,))

    db.commit()

    try:

        await bot.send_message(
            user_id,
            "🚫 <b>Ваш аккаунт заблокирован.</b>\n\n"
            "Создание операций временно недоступно.\n\n"
            "Для уточнения причины обратитесь в поддержку.",
            parse_mode="HTML"
        )

    except Exception as e:

        print(
            f"Ошибка уведомления о блокировке: {e}"
        )

    await callback.answer(
        "Пользователь заблокирован."
    )

    await send_user_card(
        callback.message,
        user_id
    )


@dp.callback_query(F.data.startswith("unblock:"))
async def unblock_user(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    user_id = int(
        callback.data.split(":")[1]
    )

    cursor.execute("""
        UPDATE users
        SET blocked = 0
        WHERE user_id = ?
    """, (user_id,))

    db.commit()

    try:

        await bot.send_message(
            user_id,
            "🔓 <b>Ваш аккаунт разблокирован.</b>\n\n"
            "Теперь вы снова можете пользоваться ботом.",
            reply_markup=main_menu(user_id),
            parse_mode="HTML"
        )

    except Exception as e:

        print(
            f"Ошибка уведомления о разблокировке: {e}"
        )

    await callback.answer(
        "Пользователь разблокирован."
    )

    await send_user_card(
        callback.message,
        user_id
    )


# =========================================================
# АДМИН — БАЛАНСЫ
# =========================================================

@dp.callback_query(F.data == "admin_balances")
async def admin_balances(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    admin_balance_user_state.add(
        callback.from_user.id
    )

    await callback.answer()

    await callback.message.edit_text(
        "💰 <b>Управление балансом</b>\n\n"
        "Отправьте ID пользователя числом.",
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )


@dp.callback_query(F.data.startswith("admin_balance_change:"))
async def admin_balance_change(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    try:

        _, user_id, currency, sign = (
            callback.data.split(":")
        )

        user_id = int(user_id)

    except (ValueError, IndexError):

        await callback.answer(
            "❌ Ошибка данных.",
            show_alert=True
        )

        return

    cursor.execute("""
        SELECT
            user_id,
            username,
            full_name,
            balance_usdt,
            balance_ton
        FROM users
        WHERE user_id = ?
    """, (user_id,))

    user = cursor.fetchone()

    if not user:

        await callback.answer(
            "Пользователь не найден.",
            show_alert=True
        )

        return

    admin_balance_amount_state[
        callback.from_user.id
    ] = {
        "user_id": user_id,
        "currency": currency,
        "sign": sign
    }

    await callback.answer()

    action = (
        "начисления"
        if sign == "plus"
        else "списания"
    )

    await callback.message.answer(
        f"💰 Введите сумму для {action}: "
        f"<b>{currency}</b>\n\n"
        f"Пользователь: <code>{user_id}</code>",
        parse_mode="HTML"
    )


# =========================================================
# АДМИН — ВСЕ ЗАЯВКИ
# =========================================================

@dp.callback_query(F.data == "admin_requests")
async def admin_requests(callback: CallbackQuery):

    if not is_moderator(callback.from_user.id):

        await callback.answer(
            "⛔ Нет доступа.",
            show_alert=True
        )

        return

    cursor.execute("""
        SELECT
            id,
            type,
            currency,
            amount,
            network,
            created_at
        FROM requests
        ORDER BY id DESC
        LIMIT 50
    """)

    rows = cursor.fetchall()

    await callback.answer()

    if not rows:

        await callback.message.edit_text(
            "📜 <b>Заявки</b>\n\n"
            "Заявок пока нет.",
            reply_markup=admin_back_keyboard(),
            parse_mode="HTML"
        )

        return

    text = "📜 <b>Последние заявки</b>\n\n"

    for (
        rid,
        rtype,
        currency,
        amount,
        network,
        created_at
    ) in rows:

        icon = (
            "➕"
            if rtype == "deposit"
            else "➖"
        )

        text += (
            f"{icon} <b>#{rid}</b> — "
            f"{amount} {currency} / "
            f"{network or '—'} — "
            f"{created_at}\n"
        )

    await callback.message.edit_text(
        text,
        reply_markup=admin_back_keyboard(),
        parse_mode="HTML"
    )


# =========================================================
# ОБЩАЯ ОБРАБОТКА СООБЩЕНИЙ
# =========================================================

@dp.message(F.from_user.id == MODERATOR_ID)
async def admin_input_handler(message: Message):

    user_id = message.from_user.id

    # =====================================================
    # ОТВЕТ ПОЛЬЗОВАТЕЛЮ
    # =====================================================

    if MODERATOR_ID in moderator_reply_to:

        target_user_id = moderator_reply_to.pop(
            MODERATOR_ID
        )

        if not message.text:

            await message.answer(
                "❌ Ответ должен быть текстовым сообщением."
            )

            return

        safe_text = escape_html(
            message.text
        )

        try:

            await bot.send_message(
                target_user_id,
                "👨‍💻 <b>Ответ администратора:</b>\n\n"
                f"{safe_text}",
                parse_mode="HTML",
                reply_markup=only_main_menu()
            )

            await message.answer(
                "✅ <b>Ответ успешно отправлен пользователю.</b>",
                parse_mode="HTML"
            )

        except Exception as e:

            print(
                f"Ошибка отправки ответа пользователю "
                f"{target_user_id}: {e}"
            )

            await message.answer(
                "❌ <b>Не удалось отправить ответ.</b>\n\n"
                "Возможно, пользователь заблокировал бота "
                "или Telegram не разрешает отправку.",
                parse_mode="HTML"
            )

        return

    # =====================================================
    # КОМИССИЯ
    # =====================================================

    if user_id in admin_commission_state:

        if not message.text:

            await message.answer(
                "❌ Введите процент числом."
            )

            return

        try:

            percent = float(
                message.text
                .replace(",", ".")
                .strip()
            )

        except ValueError:

            await message.answer(
                "❌ Введите корректный процент."
            )

            return

        if percent < 0 or percent > 100:

            await message.answer(
                "❌ Процент должен быть от 0 до 100."
            )

            return

        set_setting(
            "withdraw_fee_percent",
            percent
        )

        admin_commission_state.discard(
            user_id
        )

        await message.answer(
            "✅ <b>Комиссия изменена.</b>\n\n"
            f"💸 Новая комиссия: <b>{percent:g}%</b>",
            reply_markup=main_menu(user_id),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # КАРТОЧКА ПОЛЬЗОВАТЕЛЯ
    # =====================================================

    if user_id in admin_user_card_state:

        if not message.text or not message.text.isdigit():

            await message.answer(
                "❌ Отправьте корректный ID пользователя."
            )

            return

        target_id = int(
            message.text
        )

        if not ensure_user_by_id(target_id):

            await message.answer(
                "❌ Пользователь с таким ID не найден."
            )

            return

        admin_user_card_state.discard(
            user_id
        )

        await send_user_card(
            message,
            target_id,
            edit=False
        )

        return

    # =====================================================
    # ID ПОЛЬЗОВАТЕЛЯ ДЛЯ БАЛАНСА
    # =====================================================

    if user_id in admin_balance_user_state:

        if not message.text or not message.text.isdigit():

            await message.answer(
                "❌ Отправьте корректный ID пользователя."
            )

            return

        target_id = int(
            message.text
        )

        cursor.execute("""
            SELECT
                user_id,
                username,
                full_name,
                balance_usdt,
                balance_ton,
                blocked
            FROM users
            WHERE user_id = ?
        """, (target_id,))

        user = cursor.fetchone()

        if not user:

            await message.answer(
                "❌ Пользователь с таким ID не найден."
            )

            return

        admin_balance_user_state.discard(
            user_id
        )

        (
            uid,
            username,
            full_name,
            usdt,
            ton,
            blocked
        ) = user

        username_text = (
            f"@{username}"
            if username
            else "нет username"
        )

        await message.answer(
            "👤 <b>Пользователь</b>\n\n"
            f"Имя: <b>{escape_html(full_name or '—')}</b>\n"
            f"Username: <b>{escape_html(username_text)}</b>\n"
            f"🆔 <code>{uid}</code>\n"
            f"💵 USDT: <b>{usdt or 0:.2f}</b>\n"
            f"💎 TON: <b>{ton or 0:.4f}</b>\n\n"
            "Выберите действие:",
            reply_markup=user_card_keyboard(
                uid,
                bool(blocked)
            ),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # СУММА БАЛАНСА
    # =====================================================

    if user_id in admin_balance_amount_state:

        if not message.text:

            await message.answer(
                "❌ Введите сумму числом."
            )

            return

        try:

            amount = float(
                message.text
                .replace(",", ".")
                .strip()
            )

        except ValueError:

            await message.answer(
                "❌ Введите корректную сумму."
            )

            return

        if amount <= 0:

            await message.answer(
                "❌ Сумма должна быть больше 0."
            )

            return

        data = admin_balance_amount_state.pop(
            user_id
        )

        target_id = data["user_id"]
        currency = data["currency"]
        sign = data["sign"]

        column = (
            "balance_usdt"
            if currency == "USDT"
            else "balance_ton"
        )

        delta = (
            amount
            if sign == "plus"
            else -amount
        )

        if sign == "minus":

            current_balance = get_balance(
                target_id,
                currency
            )

            if amount > current_balance:

                await message.answer(
                    "❌ Нельзя списать больше, "
                    "чем есть на балансе."
                )

                return

        cursor.execute(
            f"""
            UPDATE users
            SET {column} = {column} + ?
            WHERE user_id = ?
            """,
            (
                delta,
                target_id
            )
        )

        cursor.execute("""
            INSERT INTO transactions (
                user_id,
                type,
                currency,
                amount,
                description,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            target_id,
            (
                "Ручное начисление"
                if sign == "plus"
                else "Ручное списание"
            ),
            currency,
            amount,
            "Изменение баланса администратором",
            now()
        ))

        db.commit()

        new_balance = get_balance(
            target_id,
            currency
        )

        await message.answer(
            "✅ <b>Баланс изменён</b>\n\n"
            f"🆔 Пользователь: <code>{target_id}</code>\n"
            f"💰 Валюта: <b>{currency}</b>\n"
            f"{'➕' if sign == 'plus' else '➖'} "
            f"Сумма: <b>{amount}</b>\n"
            f"💳 Новый баланс: "
            f"<b>{new_balance}</b> {currency}",
            parse_mode="HTML"
        )

        try:

            await bot.send_message(
                target_id,
                "💰 <b>Изменение баланса</b>\n\n"
                f"{'➕ Начислено' if sign == 'plus' else '➖ Списано'}: "
                f"<b>{amount}</b> {currency}\n"
                f"💳 Новый баланс: "
                f"<b>{new_balance}</b> {currency}",
                reply_markup=only_main_menu(),
                parse_mode="HTML"
            )

        except Exception as e:

            print(
                f"Ошибка уведомления об изменении баланса: {e}"
            )

        return


# =========================================================
# ОБЩАЯ ОБРАБОТКА ПОЛЬЗОВАТЕЛЕЙ
# =========================================================

@dp.message()
async def all_messages(message: Message):

    user_id = message.from_user.id

    ensure_user(message)

    # =====================================================
    # ПОПОЛНЕНИЕ — СУММА
    # =====================================================

    if user_id in deposit_amount_state:

        if not message.text:

            await message.answer(
                "❌ Введите сумму числом."
            )

            return

        try:

            amount = float(
                message.text
                .replace(",", ".")
                .strip()
            )

        except ValueError:

            await message.answer(
                "❌ Введите корректную сумму."
            )

            return

        if amount < MIN_DEPOSIT:

            await message.answer(
                f"❌ Минимальная сумма пополнения — "
                f"<b>{MIN_DEPOSIT:g}</b>.",
                parse_mode="HTML"
            )

            return

        data = deposit_data.get(user_id)

        if not data:

            clear_user_state(user_id)

            await message.answer(
                "❌ Операция потеряна. "
                "Начните заново.",
                reply_markup=main_menu(user_id)
            )

            return

        currency = data["currency"]
        network = data["network"]

        address = get_deposit_address(
            currency,
            network
        )

        if not address:

            await message.answer(
                "⚠️ <b>Эта сеть пока не настроена.</b>\n\n"
                "Адрес для неё ещё не добавлен.\n\n"
                "Выберите другую сеть или обратитесь "
                "в поддержку.",
                reply_markup=only_main_menu(),
                parse_mode="HTML"
            )

            clear_user_state(user_id)

            return

        deposit_amount_state.discard(
            user_id
        )

        data["amount"] = amount
        data["address"] = address

        await message.answer(
            "⚠️ <b>ВНИМАНИЕ</b>\n\n"
            f"💰 Валюта: <b>{currency}</b>\n"
            f"🌐 Сеть: <b>{network}</b>\n"
            f"💵 Сумма: <b>{amount}</b>\n\n"
            "📍 <b>Адрес:</b>\n"
            f"<code>{address}</code>\n\n"
            f"❗ <b>ОТПРАВЛЯЙТЕ {currency} "
            f"ТОЛЬКО ПО СЕТИ {network}.</b>\n\n"
            "Перевод по другой сети может привести "
            "к потере средств.\n\n"
            "После перевода нажмите "
            "<b>«✅ Я оплатил»</b>.",
            reply_markup=paid_keyboard(),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # ПОПОЛНЕНИЕ — ЧЕК
    # =====================================================

    if user_id in deposit_waiting_receipt:

        if not message.photo:

            await message.answer(
                "📸 Отправьте именно фотографию "
                "или скриншот чека."
            )

            return

        data = deposit_data.get(user_id)

        if not data:

            clear_user_state(user_id)

            await message.answer(
                "❌ Данные операции потеряны.",
                reply_markup=main_menu(user_id)
            )

            return

        currency = data["currency"]
        network = data["network"]
        amount = data["amount"]
        address = data["address"]

        photo_id = message.photo[-1].file_id

        photo_id = message.photo[-1].file_id

        cursor.execute("""
        INSERT INTO requests (
            user_id,
            type,
            currency,
            amount,
            address,
            network,
            status,
            created_at,
            receipt_file_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            "deposit",
            currency,
            amount,
            address,
            network,
            "pending",
            now(),
            photo_id
        ))

        request_id = cursor.lastrowid

        db.commit()

        username = message.from_user.username

        username_text = (
            f"@{username}"
            if username
            else "нет username"
        )

        try:

            await bot.send_photo(
                MODERATOR_ID,
                photo=photo_id,
                caption=(
                    "➕ <b>НОВАЯ ЗАЯВКА НА ПОПОЛНЕНИЕ</b>\n\n"
                    f"📋 Заявка: <b>#{request_id}</b>\n"
                    f"👤 {escape_html(message.from_user.full_name)}\n"
                    f"🔗 {escape_html(username_text)}\n"
                    f"🆔 <code>{user_id}</code>\n\n"
                    f"💰 Валюта: <b>{currency}</b>\n"
                    f"🌐 Сеть: <b>{network}</b>\n"
                    f"💵 Сумма: <b>{amount}</b>\n\n"
                    "📸 Чек прикреплён."
                ),
                reply_markup=moderator_request_keyboard(
                    request_id,
                    user_id
                ),
                parse_mode="HTML"
            )

        except Exception as e:

            print(
                f"Ошибка отправки заявки пополнения: {e}"
            )

            cursor.execute(
                "DELETE FROM requests WHERE id = ?",
                (request_id,)
            )

            db.commit()

            await message.answer(
                "❌ Не удалось отправить заявку модератору.\n\n"
                "Попробуйте ещё раз.",
                reply_markup=main_menu(user_id)
            )

            clear_user_state(user_id)

            return

        await message.answer(
            "✅ <b>Заявка отправлена модератору!</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"💰 {currency}: <b>{amount}</b>\n"
            f"🌐 Сеть: <b>{network}</b>\n\n"
            "Ожидайте проверки.",
            reply_markup=only_main_menu(),
            parse_mode="HTML"
        )

        clear_user_state(user_id)

        return

    # =====================================================
    # ВЫВОД — СУММА
    # =====================================================

    if user_id in withdraw_amount_state:

        if not message.text:

            await message.answer(
                "❌ Введите сумму."
            )

            return

        try:

            amount = float(
                message.text
                .replace(",", ".")
                .strip()
            )

        except ValueError:

            await message.answer(
                "❌ Введите корректную сумму."
            )

            return

        data = withdraw_data.get(user_id)

        if not data:

            clear_user_state(user_id)

            await message.answer(
                "❌ Операция потеряна.",
                reply_markup=main_menu(user_id)
            )

            return

        currency = data["currency"]

        if amount < MIN_WITHDRAW:

            await message.answer(
                f"❌ Минимальная сумма вывода — "
                f"<b>{MIN_WITHDRAW:g} {currency}</b>.",
                parse_mode="HTML"
            )

            return

        balance = get_balance(
            user_id,
            currency
        )

        if amount > balance:

            await message.answer(
                "❌ Недостаточно средств.\n\n"
                f"💰 Доступно: <b>{balance}</b> {currency}",
                parse_mode="HTML"
            )

            return

        withdraw_amount_state.discard(
            user_id
        )

        data["amount"] = amount

        withdraw_address_state.add(
            user_id
        )

        fee_percent = get_withdraw_fee_percent()

        await message.answer(
            "📍 <b>Введите адрес получения</b>\n\n"
            f"💰 Валюта: <b>{currency}</b>\n"
            f"🌐 Сеть: <b>{data['network']}</b>\n"
            f"💵 Сумма вывода: <b>{amount}</b>\n"
            f"💸 Комиссия: <b>{fee_percent:g}%</b>\n\n"
            "⚠️ При выводе может взиматься комиссия.\n\n"
            "Проверьте, что адрес соответствует "
            "выбранной сети.",
            reply_markup=only_main_menu(),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # ВЫВОД — АДРЕС
    # =====================================================

    if user_id in withdraw_address_state:

        if not message.text:

            await message.answer(
                "❌ Отправьте адрес текстом."
            )

            return

        address = message.text.strip()

        data = withdraw_data.get(user_id)

        if not data:

            clear_user_state(user_id)

            await message.answer(
                "❌ Операция потеряна.",
                reply_markup=main_menu(user_id)
            )

            return

        data["address"] = address

        withdraw_address_state.discard(
            user_id
        )

        amount = data["amount"]
        currency = data["currency"]

        fee_percent, fee_amount, net_amount = (
            calculate_fee(amount)
        )

        data["fee_percent"] = fee_percent
        data["fee_amount"] = fee_amount
        data["net_amount"] = net_amount

        await message.answer(
            "⚠️ <b>ПРОВЕРЬТЕ ДАННЫЕ</b>\n\n"
            f"💰 Валюта: <b>{currency}</b>\n"
            f"🌐 Сеть: <b>{data['network']}</b>\n\n"
            f"💵 Сумма вывода: "
            f"<b>{format_amount(currency, amount)}</b>\n"
            f"💸 Комиссия ({fee_percent:g}%): "
            f"<b>{format_amount(currency, fee_amount)}</b>\n"
            f"💳 К получению: "
            f"<b>{format_amount(currency, net_amount)}</b>\n\n"
            "📍 Адрес:\n"
            f"<code>{escape_html(address)}</code>\n\n"
            "⚠️ <b>При выводе может взиматься комиссия.</b>\n\n"
            "❗ Если указать неправильный адрес "
            "или сеть, средства могут быть потеряны.",
            reply_markup=withdraw_confirm_keyboard(),
            parse_mode="HTML"
        )

        return

    # =====================================================
    # КУПИТЬ / ПРОДАТЬ — СУММА
    # =====================================================
    if user_id in trade_amount_state:
        if not message.text:
            await message.answer("❌ Введите сумму числом.")
            return
        try:
            value = float(message.text.replace(",", ".").strip())
        except ValueError:
            await message.answer("❌ Введите корректную сумму.")
            return
        if value <= 0:
            await message.answer("❌ Сумма должна быть больше 0.")
            return
        data = trade_data.get(user_id)
        if not data:
            clear_user_state(user_id)
            await message.answer("❌ Операция потеряна.", reply_markup=main_menu(user_id))
            return
        rate = data["rate"]
        if data["input_mode"] == "crypto":
            crypto_amount = value
            fiat_amount = value * rate
        else:
            fiat_amount = value
            crypto_amount = value / rate
        data["crypto_amount"] = crypto_amount
        data["fiat_amount"] = fiat_amount
        trade_amount_state.discard(user_id)
        action = data["action"]
        await message.answer(
            f"{'🟢 Покупка' if action == 'buy' else '🔴 Продажа'}\n\n"
            + trade_summary(data) + "\n\n"
            "Проверьте данные перед продолжением.",
            reply_markup=trade_confirm_keyboard(action),
            parse_mode="HTML"
        )
        return

    # =====================================================
    # ПРОДАЖА — РЕКВИЗИТЫ КАРТЫ
    # =====================================================
    if user_id in trade_card_state:
        if not message.text:
            await message.answer("❌ Отправьте номер карты текстом.")
            return
        card = message.text.strip()
        digits = "".join(ch for ch in card if ch.isdigit())
        if len(digits) < 10:
            await message.answer("❌ Похоже, номер карты указан неверно. Введите реквизиты ещё раз.")
            return
        data = trade_data.get(user_id)
        if not data:
            clear_user_state(user_id)
            await message.answer("❌ Операция потеряна.", reply_markup=main_menu(user_id))
            return
        data["card_details"] = card
        trade_card_state.discard(user_id)
        address = SELL_USDT_ADDRESS if data["currency"] == "USDT" else SELL_TON_ADDRESS
        if not address:
            await message.answer(
                "⚠️ <b>Адрес для приёма крипты ещё не настроен.</b>\n\n"
                "Добавьте SELL_USDT_ADDRESS / SELL_TON_ADDRESS в настройках бота.",
                reply_markup=only_main_menu(), parse_mode="HTML"
            )
            clear_user_state(user_id)
            return
        data["sell_address"] = address
        await message.answer(
            "📤 <b>Куда отправить крипту</b>\n\n"
            f"💰 Валюта: <b>{data['currency']}</b>\n"
            f"🪙 Сумма: <b>{trade_format(data['currency'], data['crypto_amount'])} {data['currency']}</b>\n"
            f"🌐 Сеть: <b>{'TRC20' if data['currency'] == 'USDT' else 'TON'}</b>\n\n"
            f"📍 Адрес:\n<code>{escape_html(address)}</code>\n\n"
            "После перевода нажмите кнопку ниже.",
            reply_markup=trade_sent_keyboard(), parse_mode="HTML"
        )
        return

    # =====================================================
    # КУПИТЬ / ПРОДАТЬ — ЧЕК
    # =====================================================
    if user_id in trade_receipt_state:
        if not message.photo:
            await message.answer("📸 Отправьте именно фотографию или скриншот чека.")
            return
        data = trade_data.get(user_id)
        if not data:
            clear_user_state(user_id)
            await message.answer("❌ Операция потеряна.", reply_markup=main_menu(user_id))
            return
        photo_id = message.photo[-1].file_id
        action = data["action"]
        currency = data["currency"]
        crypto_amount = data["crypto_amount"]
        fiat_amount = data["fiat_amount"]
        rate = data["rate"]
        card_details = data.get("card_details", "")
        operation = "buy" if action == "buy" else "sell"
        request_address = BUY_CARD_NUMBER if action == "buy" else card_details
        sell_address = data.get("sell_address", "")
        description = f"{action} / {currency} / Украина / SenseBank"
        cursor.execute("""
            INSERT INTO requests (
                user_id, type, currency, amount, address, network, status,
                created_at, receipt_file_id, operation, country, bank, rate,
                fiat_amount, crypto_amount, card_details
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user_id, f"trade_{operation}", currency, crypto_amount,
            request_address, "TRC20" if currency == "USDT" else "TON", "pending",
            now(), photo_id, operation, "Украина", "SenseBank", rate,
            fiat_amount, crypto_amount, card_details
        ))
        request_id = cursor.lastrowid
        db.commit()
        username = message.from_user.username
        username_text = f"@{username}" if username else "нет username"
        caption = (
            f"{'🟢' if action == 'buy' else '🔴'} <b>НОВАЯ ЗАЯВКА — {'ПОКУПКА' if action == 'buy' else 'ПРОДАЖА'}</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"👤 {escape_html(message.from_user.full_name)}\n"
            f"🔗 {escape_html(username_text)}\n"
            f"🆔 <code>{user_id}</code>\n\n"
            f"💰 Крипта: <b>{currency}</b>\n"
            f"🇺🇦 Страна: <b>Украина</b>\n"
            f"🏦 Банк: <b>SenseBank</b>\n"
            f"📈 Курс: <b>{rate:.2f} ₴</b>\n"
            f"🪙 Крипта: <b>{trade_format(currency, crypto_amount)} {currency}</b>\n"
            f"💴 Сумма: <b>{fiat_amount:.2f} ₴</b>\n\n"
        )
        if action == "buy":
            caption += f"💳 Карта магазина: <code>{escape_html(BUY_CARD_NUMBER)}</code>\n"
        else:
            caption += f"💳 Карта пользователя: <code>{escape_html(card_details)}</code>\n"
            caption += f"📍 Адрес приёма: <code>{escape_html(sell_address)}</code>\n"
        caption += "\n📸 Чек прикреплён."
        await bot.send_photo(
            MODERATOR_ID,
            photo=photo_id,
            caption=caption,
            reply_markup=moderator_request_keyboard(request_id, user_id),
            parse_mode="HTML"
        )
        await message.answer(
            "✅ <b>Заявка отправлена модератору!</b>\n\n"
            f"📋 Заявка: <b>#{request_id}</b>\n"
            f"🪙 {trade_format(currency, crypto_amount)} {currency}\n"
            f"💴 {fiat_amount:.2f} ₴\n\nОжидайте проверки.",
            reply_markup=only_main_menu(),
            parse_mode="HTML"
        )
        clear_user_state(user_id)
        return

    # =====================================================
    # ПОДДЕРЖКА
    # =====================================================

    if user_id in support_state:

        if not message.text:

            await message.answer(
                "❌ Отправьте вопрос текстом."
            )

            return

        username = message.from_user.username

        username_text = (
            f"@{username}"
            if username
            else "нет username"
        )

        try:

            await bot.send_message(
                MODERATOR_ID,
                "🆘 <b>ЗАЯВКА В ПОДДЕРЖКУ</b>\n\n"
                f"👤 {escape_html(message.from_user.full_name)}\n"
                f"🔗 {escape_html(username_text)}\n"
                f"🆔 <code>{user_id}</code>\n\n"
                "💬 Сообщение:\n"
                f"{escape_html(message.text)}",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="💬 Ответить",
                                callback_data=f"reply:{user_id}"
                            )
                        ]
                    ]
                ),
                parse_mode="HTML"
            )

        except Exception as e:

            print(
                f"Ошибка отправки поддержки: {e}"
            )

            await message.answer(
                "❌ Не удалось отправить сообщение "
                "в поддержку."
            )

            return

        await message.answer(
            "✅ <b>Сообщение отправлено модератору.</b>\n\n"
            "Ожидайте ответа.",
            reply_markup=only_main_menu(),
            parse_mode="HTML"
        )

        support_state.discard(user_id)

        return


# =========================================================
# ЗАПУСК
# =========================================================

async def main():

    print("PaltoPay запускается...")

    await bot.delete_webhook(
        drop_pending_updates=True
    )

    print("Webhook удалён.")
    print("PaltoPay запущен!")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
