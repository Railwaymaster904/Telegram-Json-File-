# =========================
# PART 1 — CONFIG + DATABASE + HELPERS
# =========================

import os
import json
import re
import zipfile
from datetime import datetime, timedelta

from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# =========================
# ENVIRONMENT
# =========================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
WITHDRAW_CHANNEL = os.getenv("WITHDRAW_CHANNEL", "")
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "")

REFERRAL_BONUS = float(
    os.getenv("REFERRAL_BONUS", "0.05")
)

INITIAL_ADMINS = [
    int(x.strip())
    for x in os.getenv("ADMIN_IDS", "0").split(",")
    if x.strip().isdigit()
]

# =========================
# DEFAULT SETTINGS
# =========================

DEFAULT_PRICE = 0.30
DEFAULT_WAIT_HOURS = 18
MIN_WITHDRAW = 1.00

# =========================
# DIRECTORIES
# =========================

DATA_DIR = "data"

os.makedirs(DATA_DIR, exist_ok=True)

# =========================
# DATA FILES
# =========================

BALANCES_FILE = f"{DATA_DIR}/balances.json"
CLAIMS_FILE = f"{DATA_DIR}/claims.json"
REFS_FILE = f"{DATA_DIR}/referrals.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"
SUPPORT_FILE = f"{DATA_DIR}/support.json"

LANG_FILE = f"{DATA_DIR}/user_lang.json"
CAPACITY_FILE = f"{DATA_DIR}/capacity.json"

FROZEN_FILE = f"{DATA_DIR}/frozen.json"

BOT_STATUS_FILE = f"{DATA_DIR}/bot_status.json"
COUNTRY_SETTINGS_FILE = f"{DATA_DIR}/country_settings.json"

# =========================
# CONVERSATION STATES
# =========================

WD_METHOD = 1
WD_DETAILS = 2
SUPPORT_MSG = 3

# =========================
# GLOBAL DATA
# =========================

pending = {}

# =========================
# JSON HELPERS
# =========================

def load_json(path, default=None):
    if default is None:
        default = {}

    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

    except Exception as e:
        print(f"JSON Load Error [{path}]: {e}")

    return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=2
            )

    except Exception as e:
        print(f"JSON Save Error [{path}]: {e}")


# =========================
# ADMIN SYSTEM
# =========================

def get_admins():
    admins = load_json(ADMINS_FILE, [])

    if not admins:
        admins = INITIAL_ADMINS[:]
        save_json(ADMINS_FILE, admins)

    return admins


def is_admin(user_id):
    return user_id in get_admins()


def add_admin(user_id):
    admins = get_admins()

    if user_id not in admins:
        admins.append(user_id)
        save_json(ADMINS_FILE, admins)
        return True

    return False


def remove_admin(user_id):
    admins = get_admins()

    if user_id in admins and len(admins) > 1:
        admins.remove(user_id)
        save_json(ADMINS_FILE, admins)
        return True

    return False


# =========================
# SETTINGS
# =========================

def get_settings():

    settings = load_json(SETTINGS_FILE, {})

    return {
        "price": settings.get(
            "price",
            DEFAULT_PRICE
        ),

        "wait": settings.get(
            "wait",
            DEFAULT_WAIT_HOURS
        ),

        "ref_bonus": settings.get(
            "ref_bonus",
            REFERRAL_BONUS
        )
    }


def save_settings(settings):
    save_json(
        SETTINGS_FILE,
        settings
    )


# =========================
# BALANCE SYSTEM
# =========================

def get_balance(user_id):

    balances = load_json(
        BALANCES_FILE,
        {}
    )

    return float(
        balances.get(
            str(user_id),
            0
        )
    )


def set_balance(user_id, amount):

    balances = load_json(
        BALANCES_FILE,
        {}
    )

    balances[str(user_id)] = round(
        float(amount),
        2
    )

    save_json(
        BALANCES_FILE,
        balances
    )

    return balances[str(user_id)]


def add_balance(user_id, amount):

    current = get_balance(user_id)

    new_balance = round(
        current + float(amount),
        2
    )

    return set_balance(
        user_id,
        new_balance
    )


def subtract_balance(user_id, amount):

    current = get_balance(user_id)

    new_balance = max(
        0,
        round(
            current - float(amount),
            2
        )
    )

    return set_balance(
        user_id,
        new_balance
    )


# =========================
# LANGUAGE SYSTEM
# =========================

def get_user_lang(user_id):

    langs = load_json(
        LANG_FILE,
        {}
    )

    return langs.get(
        str(user_id),
        "en"
    )


def set_user_lang(user_id, lang):

    langs = load_json(
        LANG_FILE,
        {}
    )

    langs[str(user_id)] = lang

    save_json(
        LANG_FILE,
        langs
    )


def t(user_id, en_text, bn_text):

    if get_user_lang(user_id) == "bn":
        return bn_text

    return en_text


# =========================
# BOT ON / OFF
# =========================

def is_bot_on():

    status = load_json(
        BOT_STATUS_FILE,
        {"on": True}
    )

    return bool(
        status.get("on", True)
    )


def set_bot_status(status):

    save_json(
        BOT_STATUS_FILE,
        {
            "on": bool(status)
        }
    )


# =========================
# COUNTRY CODE
# =========================

def get_country_code(phone):

    phone = phone.replace(
        "+",
        ""
    ).strip()

    # Common international prefixes.
    # This is only a prefix helper,
    # not a complete telecom database.

    prefixes = [
        "880",
        "91",
        "92",
        "234",
        "966",
        "971",
        "212",
        "216",
        "213",
        "254",
        "27",
        "90",
        "49",
        "33",
        "44",
        "39",
        "34",
        "7",
        "1",
    ]

    for prefix in sorted(
        prefixes,
        key=len,
        reverse=True
    ):
        if phone.startswith(prefix):
            return prefix

    return phone[:1]


# =========================
# COUNTRY SETTINGS
# =========================

def get_country_setting(country_code):

    settings = load_json(
        COUNTRY_SETTINGS_FILE,
        {}
    )

    default = get_settings()

    return settings.get(
        str(country_code),
        {
            "price": default["price"],
            "wait": default["wait"]
        }
    )


def set_country_setting(
    country_code,
    price=None,
    wait=None
):

    settings = load_json(
        COUNTRY_SETTINGS_FILE,
        {}
    )

    code = str(country_code)

    if code not in settings:
        settings[code] = {}

    if price is not None:
        settings[code]["price"] = float(price)

    if wait is not None:
        settings[code]["wait"] = int(wait)

    save_json(
        COUNTRY_SETTINGS_FILE,
        settings
    )


# =========================
# CAPACITY SYSTEM
# =========================

def get_capacity(country_code):

    capacities = load_json(
        CAPACITY_FILE,
        {}
    )

    return int(
        capacities.get(
            str(country_code),
            9999
        )
    )


def set_capacity(
    country_code,
    limit
):

    capacities = load_json(
        CAPACITY_FILE,
        {}
    )

    capacities[str(country_code)] = int(
        limit
    )

    save_json(
        CAPACITY_FILE,
        capacities
    )


# =========================
# FROZEN SYSTEM
# =========================

def get_frozen():

    return load_json(
        FROZEN_FILE,
        {}
    )


def is_frozen(phone):

    frozen = get_frozen()

    return phone in frozen


def add_frozen(
    phone,
    reason="Frozen"
):

    frozen = get_frozen()

    frozen[phone] = {
        "reason": reason,
        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M"
        )
    }

    save_json(
        FROZEN_FILE,
        frozen
    )


def remove_frozen(phone):

    frozen = get_frozen()

    if phone in frozen:
        del frozen[phone]

    save_json(
        FROZEN_FILE,
        frozen
    )


# =========================
# FLAG HELPER
# =========================

def get_flag(phone):

    flags = {
        "880": "🇧🇩",
        "91": "🇮🇳",
        "92": "🇵🇰",
        "1": "🇺🇸",
        "44": "🇬🇧",
        "27": "🇿🇦",
        "234": "🇳🇬",
        "966": "🇸🇦",
        "971": "🇦🇪",
        "90": "🇹🇷",
        "7": "🇷🇺",
        "49": "🇩🇪",
        "33": "🇫🇷",
        "86": "🇨🇳",
        "62": "🇮🇩",
        "60": "🇲🇾",
        "65": "🇸🇬",
        "63": "🇵🇭",
        "55": "🇧🇷",
        "52": "🇲🇽",
        "20": "🇪🇬",
        "212": "🇲🇦",
        "40": "🇷🇴",
        "48": "🇵🇱",
        "216": "🇹🇳",
        "213": "🇩🇿",
        "254": "🇰🇪",
    }

    phone = phone.replace(
        "+",
        ""
    )

    for code in sorted(
        flags,
        key=len,
        reverse=True
    ):
        if phone.startswith(code):
            return flags[code]

    return "🏳️"


# =========================
# FORCE JOIN
# =========================

async def check_joined(
    bot,
    user_id
):

    if not FORCE_CHANNEL:
        return True

    try:
        member = await bot.get_chat_member(
            FORCE_CHANNEL,
            user_id
        )

        return member.status in [
            "member",
            "administrator",
            "creator"
        ]

    except Exception:
        return False


# =========================
# REFERRAL SYSTEM
# =========================

def get_referrer(user_id):

    refs = load_json(
        REFS_FILE,
        {}
    )

    return refs.get(
        str(user_id)
    )


def set_referrer(
    user_id,
    referrer_id
):

    refs = load_json(
        REFS_FILE,
        {}
    )

    if str(user_id) not in refs:
        refs[str(user_id)] = int(
            referrer_id
        )

        save_json(
            REFS_FILE,
            refs
        )

        return True

    return False


# =========================
# BASIC USER VALIDATION
# =========================

def valid_phone(text):

    text = text.strip().replace(
        " ",
        ""
    )

    return bool(
        re.match(
            r"^\+?\d{8,15}$",
            text
        )
    )


# =========================
# CLAIM HELPERS
# =========================

def create_claim(
    user_id,
    reference,
    price,
    wait
):

    claim_id = (
        f"{user_id}_"
        f"{reference}_"
        f"{int(datetime.now().timestamp())}"
    )

    claims = load_json(
        CLAIMS_FILE,
        {}
    )

    claims[claim_id] = {
        "uid": user_id,
        "reference": reference,
        "price": float(price),
        "wait": int(wait),
        "time": datetime.now().isoformat(),
        "done": False
    }

    save_json(
        CLAIMS_FILE,
        claims
    )

    return claim_id


# =========================
# PART 1 END
# =========================

print("✅ Part 1 loaded successfully.")
# ============================================================
# PART 2 — USER SYSTEM + WITHDRAW + SUPPORT + ADMIN
# ============================================================

# ====================== LANGUAGE ======================

LANG_FILE = f"{DATA_DIR}/user_lang.json"


def get_user_lang(uid):
    langs = load_json(LANG_FILE, {})
    return langs.get(str(uid), "en")


def set_user_lang(uid, lang):
    langs = load_json(LANG_FILE, {})
    langs[str(uid)] = lang
    save_json(LANG_FILE, langs)


async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")]
    ]

    await update.message.reply_text(
        "🌐 Select Language / ভাষা নির্বাচন করুন:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ====================== FROZEN USERS ======================

FROZEN_FILE = f"{DATA_DIR}/frozen.json"


def get_frozen():
    return load_json(FROZEN_FILE, {})


def add_frozen(uid, reason="Frozen"):
    frozen = get_frozen()

    frozen[str(uid)] = {
        "reason": reason,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }

    save_json(FROZEN_FILE, frozen)


def remove_frozen(uid):
    frozen = get_frozen()

    if str(uid) in frozen:
        del frozen[str(uid)]
        save_json(FROZEN_FILE, frozen)


def is_frozen(uid):
    return str(uid) in get_frozen()


# ====================== BOT ON/OFF ======================

BOT_STATUS_FILE = f"{DATA_DIR}/bot_status.json"


def is_bot_on():
    status = load_json(BOT_STATUS_FILE, {"on": True})
    return status.get("on", True)


def set_bot_status(status):
    save_json(BOT_STATUS_FILE, {"on": bool(status)})


async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    set_bot_status(True)

    await update.message.reply_text(
        "🟢 Bot is now ON.\n\nUsers can use the bot."
    )


async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    set_bot_status(False)

    await update.message.reply_text(
        "🔴 Bot is now OFF.\n\nUsers cannot submit new requests."
    )


# ====================== COUNTRY SETTINGS ======================

COUNTRY_SETTINGS_FILE = f"{DATA_DIR}/country_settings.json"
CAPACITY_FILE = f"{DATA_DIR}/capacity.json"


def get_country_setting(country_code):
    settings = load_json(COUNTRY_SETTINGS_FILE, {})

    default = get_settings()

    return settings.get(
        str(country_code),
        {
            "price": default["price"],
            "wait": default["wait"]
        }
    )


def set_country_setting(country_code, price=None, wait=None):
    settings = load_json(COUNTRY_SETTINGS_FILE, {})

    code = str(country_code)

    if code not in settings:
        settings[code] = {}

    if price is not None:
        settings[code]["price"] = float(price)

    if wait is not None:
        settings[code]["wait"] = int(wait)

    save_json(COUNTRY_SETTINGS_FILE, settings)


def get_capacity(country_code):
    caps = load_json(CAPACITY_FILE, {})
    return caps.get(str(country_code), 9999)


def set_capacity(country_code, limit):
    caps = load_json(CAPACITY_FILE, {})

    caps[str(country_code)] = int(limit)

    save_json(CAPACITY_FILE, caps)


async def set_country(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage:\n"
            "/setcountry 880 0.40 20\n\n"
            "Format:\n"
            "/setcountry <country_code> <price> <wait_hours>"
        )
        return

    try:
        code = context.args[0]
        price = float(context.args[1])
        wait = int(context.args[2])

        set_country_setting(
            code,
            price=price,
            wait=wait
        )

        await update.message.reply_text(
            f"✅ Country setting updated!\n\n"
            f"🌍 Code: {code}\n"
            f"💰 Price: ${price:.2f}\n"
            f"⏱ Wait: {wait} hours"
        )

    except Exception:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Example:\n"
            "/setcountry 880 0.40 20"
        )


# ====================== SET CAPACITY ======================

async def set_capacity_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n\n"
            "/capacity 880 150\n"
            "/capacity 91 200"
        )
        return

    try:
        code = context.args[0]
        limit = int(context.args[1])

        set_capacity(code, limit)

        await update.message.reply_text(
            f"✅ Capacity updated!\n\n"
            f"🌍 Country Code: `{code}`\n"
            f"📊 Limit: `{limit}`",
            parse_mode="Markdown"
        )

    except Exception:
        await update.message.reply_text(
            "❌ Invalid format.\n\n"
            "Example:\n"
            "/capacity 880 150"
        )


# ====================== WITHDRAW ======================

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):

    uid = update.effective_user.id

    if is_frozen(uid):
        await update.message.reply_text(
            "❄️ Your account is currently frozen."
        )
        return ConversationHandler.END

    balances = load_json(BALANCES_FILE, {})
    balance = float(balances.get(str(uid), 0))

    if balance < MIN_WITHDRAW:
        await update.message.reply_text(
            f"❌ Minimum withdrawal: ${MIN_WITHDRAW:.2f}\n\n"
            f"💰 Your balance: ${balance:.2f}"
        )
        return ConversationHandler.END

    keyboard = [
        [
            InlineKeyboardButton(
                "💳 Leader Card",
                callback_data="wd_card"
            )
        ],
        [
            InlineKeyboardButton(
                "🟡 Binance BEP20",
                callback_data="wd_bep"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Cancel",
                callback_data="wd_cancel"
            )
        ]
    ]

    await update.message.reply_text(
        f"💰 Your Balance: ${balance:.2f}\n\n"
        f"Select withdrawal method:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return WD_METHOD


async def wd_method(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    if query.data == "wd_cancel":
        await query.edit_message_text(
            "❌ Withdrawal cancelled."
        )
        return ConversationHandler.END

    if query.data == "wd_card":
        method = "Leader Card"

    elif query.data == "wd_bep":
        method = "Binance BEP20"

    else:
        return ConversationHandler.END

    context.user_data["withdraw_method"] = method

    await query.edit_message_text(
        f"💳 Method: {method}\n\n"
        "Send your payment details now."
    )

    return WD_DETAILS


async def wd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user

    details = update.message.text.strip()

    method = context.user_data.get(
        "withdraw_method",
        "Unknown"
    )

    balances = load_json(BALANCES_FILE, {})

    balance = float(
        balances.get(str(user.id), 0)
    )

    if balance < MIN_WITHDRAW:
        await update.message.reply_text(
            "❌ Your balance is no longer sufficient."
        )
        return ConversationHandler.END

    # Deduct balance
    balances[str(user.id)] = 0
    save_json(BALANCES_FILE, balances)

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    total_accounts = sum(
        1
        for info in accounts.values()
        if info.get("uid") == user.id
    )

    request_text = (
        "💸 NEW WITHDRAWAL REQUEST\n\n"
        f"👤 Name: {user.first_name}\n"
        f"🆔 User ID: {user.id}\n"
        f"🔗 Username: @{user.username or 'None'}\n\n"
        f"📱 Accounts: {total_accounts}\n"
        f"💰 Amount: ${balance:.2f}\n"
        f"💳 Method: {method}\n"
        f"📝 Details: {details}\n\n"
        f"⏰ Time: "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

    if WITHDRAW_CHANNEL:

        try:
            await context.bot.send_message(
                chat_id=int(WITHDRAW_CHANNEL),
                text=request_text
            )

        except Exception as e:
            print("Withdraw channel error:", e)

    await update.message.reply_text(
        "✅ Withdrawal request submitted successfully!\n\n"
        f"💰 Amount: ${balance:.2f}\n"
        f"💳 Method: {method}"
    )

    context.user_data.pop(
        "withdraw_method",
        None
    )

    return ConversationHandler.END


# ====================== SUPPORT ======================

async def support_start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "🧑🏻‍💻 Support\n\n"
        "Send your problem or question.\n\n"
        "❌ Use /cancel to cancel."
    )

    return SUPPORT_MSG


async def support_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    user = update.effective_user
    message = update.message.text

    tickets = load_json(
        SUPPORT_FILE,
        {}
    )

    ticket_id = (
        f"{user.id}_"
        f"{int(datetime.now().timestamp())}"
    )

    tickets[ticket_id] = {
        "user_id": user.id,
        "name": user.first_name,
        "username": user.username,
        "message": message,
        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M"
        )
    }

    save_json(
        SUPPORT_FILE,
        tickets
    )

    for admin_id in get_admins():

        try:

            keyboard = [[
                InlineKeyboardButton(
                    "💬 Reply",
                    callback_data=f"reply_{user.id}"
                )
            ]]

            await context.bot.send_message(
                admin_id,
                "🆘 New Support Message\n\n"
                f"👤 {user.first_name}\n"
                f"🆔 {user.id}\n"
                f"🔗 @{user.username or 'None'}\n\n"
                f"💬 Message:\n{message}",
                reply_markup=InlineKeyboardMarkup(
                    keyboard
                )
            )

        except Exception:
            pass

    await update.message.reply_text(
        "✅ Your message has been sent to support.\n\n"
        "Please wait for an admin reply."
    )

    return ConversationHandler.END


# ====================== USER ACCOUNTS LIST ======================

async def myaccounts_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    uid = update.effective_user.id

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    user_accounts = [
        phone
        for phone, info in accounts.items()
        if info.get("uid") == uid
    ]

    if not user_accounts:
        await update.message.reply_text(
            "📭 You don't have any registered accounts."
        )
        return

    text = (
        f"📱 Your Accounts "
        f"({len(user_accounts)})\n\n"
    )

    for i, phone in enumerate(
        user_accounts[:30],
        1
    ):

        flag = get_flag(phone)

        frozen = (
            " ❄️"
            if is_frozen(uid)
            else ""
        )

        text += (
            f"{i}. {flag} "
            f"`{phone}`{frozen}\n"
        )

    if len(user_accounts) > 30:

        text += (
            f"\n... and "
            f"{len(user_accounts) - 30} more"
        )

    await update.message.reply_text(
        text,
        parse_mode="Markdown"
    )


# ====================== USER INFO ======================

async def userinfo_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:

        await update.message.reply_text(
            "Usage:\n"
            "/userinfo 123456789"
        )

        return

    try:
        target_uid = int(context.args[0])

    except ValueError:

        await update.message.reply_text(
            "❌ Invalid User ID."
        )

        return

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    balances = load_json(
        BALANCES_FILE,
        {}
    )

    claims = load_json(
        CLAIMS_FILE,
        {}
    )

    user_accounts = [
        phone
        for phone, info in accounts.items()
        if info.get("uid") == target_uid
    ]

    balance = balances.get(
        str(target_uid),
        0
    )

    pending_claims = sum(
        1
        for claim in claims.values()
        if claim.get("uid") == target_uid
        and not claim.get("done")
    )

    status = (
        "❄️ Frozen"
        if is_frozen(target_uid)
        else "🟢 Active"
    )

    text = (
        "👤 USER INFORMATION\n\n"
        f"🆔 User ID: `{target_uid}`\n"
        f"📊 Status: {status}\n"
        f"📱 Accounts: {len(user_accounts)}\n"
        f"💰 Balance: ${float(balance):.2f}\n"
        f"⏳ Pending Claims: {pending_claims}\n"
    )

    await update.message.reply_text(
        text,
        parse_mode="Markdown"
    )


# ====================== FREEZE USER ======================

async def freeze_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:

        await update.message.reply_text(
            "Usage:\n/freeze 123456789"
        )

        return

    try:
        uid = int(context.args[0])

    except ValueError:

        await update.message.reply_text(
            "❌ Invalid User ID."
        )

        return

    add_frozen(
        uid,
        "Frozen by admin"
    )

    await update.message.reply_text(
        f"❄️ User `{uid}` has been frozen.",
        parse_mode="Markdown"
    )


async def unfreeze_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/unfreeze 123456789"
        )
        return

    try:
        uid = int(context.args[0])

    except ValueError:
        await update.message.reply_text(
            "❌ Invalid User ID."
        )
        return

    remove_frozen(uid)

    await update.message.reply_text(
        f"✅ User `{uid}` has been unfrozen.",
        parse_mode="Markdown"
    )


# ====================== STATISTICS ======================

async def stats_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    balances = load_json(
        BALANCES_FILE,
        {}
    )

    claims = load_json(
        CLAIMS_FILE,
        {}
    )

    frozen = get_frozen()

    users = set()

    for info in accounts.values():

        uid = info.get("uid")

        if uid:
            users.add(uid)

    total_balance = sum(
        float(v)
        for v in balances.values()
    )

    pending_claims = sum(
        1
        for c in claims.values()
        if not c.get("done")
    )

    text = (
        "📊 BOT STATISTICS\n\n"
        f"👥 Users: {len(users)}\n"
        f"📱 Accounts: {len(accounts)}\n"
        f"💰 Balance: ${total_balance:.2f}\n"
        f"⏳ Pending Claims: {pending_claims}\n"
        f"❄️ Frozen Users: {len(frozen)}\n"
        f"🟢 Bot Status: "
        f"{'ON' if is_bot_on() else 'OFF'}"
    )

    await update.message.reply_text(
        text
    )


# ====================== BROADCAST ======================

async def broadcast_cmd(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    if not context.args:

        await update.message.reply_text(
            "Usage:\n"
            "/broadcast Your message"
        )

        return

    message = " ".join(
        context.args
    )

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    user_ids = list({
        info.get("uid")
        for info in accounts.values()
        if info.get("uid")
    })

    status = await update.message.reply_text(
        f"📢 Sending to {len(user_ids)} users..."
    )

    success = 0
    failed = 0

    for uid in user_ids:

        try:

            await context.bot.send_message(
                uid,
                f"📢 Announcement\n\n{message}"
            )

            success += 1

        except Exception:
            failed += 1

    await status.edit_text(
        "✅ Broadcast completed!\n\n"
        f"🟢 Success: {success}\n"
        f"🔴 Failed: {failed}"
    )


# ====================== ADMIN REPLY ======================

async def admin_reply_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    if "reply_to" not in context.user_data:
        return

    target_uid = context.user_data.pop(
        "reply_to"
    )

    message = update.message.text

    try:

        await context.bot.send_message(
            target_uid,
            f"📩 Support Reply\n\n{message}"
        )

        await update.message.reply_text(
            "✅ Reply sent successfully."
        )

    except Exception:

        await update.message.reply_text(
            "❌ Could not send reply."
        )


# ====================== ADMIN CALLBACK ======================

async def admin_cb(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    # ---------- LANGUAGE ----------

    if data.startswith("lang_"):

        lang = data.replace(
            "lang_",
            ""
        )

        set_user_lang(
            query.from_user.id,
            lang
        )

        if lang == "bn":
            msg = "✅ ভাষা বাংলা করা হয়েছে।"
        else:
            msg = "✅ Language changed to English."

        await query.edit_message_text(
            msg
        )

        return

    # ---------- SUPPORT REPLY ----------

    if data.startswith("reply_"):

        uid = int(
            data.replace(
                "reply_",
                ""
            )
        )

        context.user_data[
            "reply_to"
        ] = uid

        await query.edit_message_text(
            f"✍️ Send reply for user `{uid}`:",
            parse_mode="Markdown"
        )

        return

    # ---------- SET PRICE ----------

    if data == "set_price":

        context.user_data[
            "admin_edit"
        ] = "price"

        await query.edit_message_text(
            "💰 Send new price.\n\n"
            "Example: 0.35"
        )

        return

    # ---------- SET WAIT ----------

    if data == "set_wait":

        context.user_data[
            "admin_edit"
        ] = "wait"

        await query.edit_message_text(
            "⏱ Send wait time in hours.\n\n"
            "Example: 18"
        )

        return

    # ---------- SET REF ----------

    if data == "set_ref":

        context.user_data[
            "admin_edit"
        ] = "ref"

        await query.edit_message_text(
            "🎁 Send referral bonus.\n\n"
            "Example: 0.05"
        )

        return

    # ---------- SET CAPACITY ----------

    if data == "set_capacity":

        context.user_data[
            "admin_edit"
        ] = "capacity"

        await query.edit_message_text(
            "📊 Send country code and capacity.\n\n"
            "Example:\n"
            "880 150"
        )

        return

    # ---------- ADD ADMIN ----------

    if data == "add_admin":

        context.user_data[
            "admin_edit"
        ] = "add_admin"

        await query.edit_message_text(
            "➕ Send Telegram User ID:"
        )

        return

    # ---------- ADMIN LIST ----------

    if data == "list_admins":

        admins = get_admins()

        text = (
            "👑 ADMIN LIST\n\n"
            + "\n".join(
                f"• `{uid}`"
                for uid in admins
            )
        )

        await query.edit_message_text(
            text,
            parse_mode="Markdown"
        )

        return

    # ---------- BACK ----------

    if data == "back_dashboard":

        await show_dashboard(
            query,
            context
        )

        return


# ====================== DASHBOARD ======================

async def show_dashboard(
    query,
    context
):

    settings = get_settings()

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    balances = load_json(
        BALANCES_FILE,
        {}
    )

    total_balance = sum(
        float(v)
        for v in balances.values()
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "💰 Set Price",
                callback_data="set_price"
            ),
            InlineKeyboardButton(
                "⏱ Set Wait",
                callback_data="set_wait"
            )
        ],

        [
            InlineKeyboardButton(
                "🎁 Referral Bonus",
                callback_data="set_ref"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 Set Capacity",
                callback_data="set_capacity"
            )
        ],

        [
            InlineKeyboardButton(
                "➕ Add Admin",
                callback_data="add_admin"
            ),
            InlineKeyboardButton(
                "👑 Admin List",
                callback_data="list_admins"
            )
        ]
    ]

    text = (
        "📊 ADMIN DASHBOARD\n\n"
        f"📱 Accounts: {len(accounts)}\n"
        f"💰 Total Balance: ${total_balance:.2f}\n"
        f"💵 Price: ${settings['price']}\n"
        f"⏱ Wait: {settings['wait']} hours\n"
        f"🎁 Referral: ${settings['ref_bonus']}\n"
        f"🟢 Bot: {'ON' if is_bot_on() else 'OFF'}"
    )

    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


async def dashboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    settings = get_settings()

    accounts = load_json(
        ACCOUNTS_FILE,
        {}
    )

    balances = load_json(
        BALANCES_FILE,
        {}
    )

    total_balance = sum(
        float(v)
        for v in balances.values()
    )

    keyboard = [

        [
            InlineKeyboardButton(
                "💰 Set Price",
                callback_data="set_price"
            ),
            InlineKeyboardButton(
                "⏱ Set Wait",
                callback_data="set_wait"
            )
        ],

        [
            InlineKeyboardButton(
                "🎁 Referral",
                callback_data="set_ref"
            )
        ],

        [
            InlineKeyboardButton(
                "📊 Capacity",
                callback_data="set_capacity"
            )
        ],

        [
            InlineKeyboardButton(
                "➕ Add Admin",
                callback_data="add_admin"
            ),
            InlineKeyboardButton(
                "👑 Admins",
                callback_data="list_admins"
            )
        ]
    ]

    text = (
        "📊 ADMIN DASHBOARD\n\n"
        f"📱 Accounts: {len(accounts)}\n"
        f"💰 Balance: ${total_balance:.2f}\n"
        f"💵 Price: ${settings['price']}\n"
        f"⏱ Wait: {settings['wait']} hours\n"
        f"🎁 Referral: ${settings['ref_bonus']}\n"
        f"🟢 Bot: {'ON' if is_bot_on() else 'OFF'}"
    )

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(
            keyboard
        )
    )


# ====================== ADMIN EDIT ======================

async def admin_edit(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_admin(update.effective_user.id):
        return

    # Support reply
    if "reply_to" in context.user_data:

        await admin_reply_handler(
            update,
            context
        )

        return

    key = context.user_data.pop(
        "admin_edit",
        None
    )

    if not key:
        return

    text = update.message.text.strip()

    try:

        # ---------- PRICE ----------

        if key == "price":

            value = float(text)

            settings = get_settings()
            settings["price"] = value
            save_settings(settings)

            await update.message.reply_text(
                f"✅ Price updated: ${value:.2f}"
            )

        # ---------- WAIT ----------

        elif key == "wait":

            value = int(text)

            settings = get_settings()
            settings["wait"] = value
            save_settings(settings)

            await update.message.reply_text(
                f"✅ Wait time updated: {value} hours"
            )

        # ---------- REFERRAL ----------

        elif key == "ref":

            value = float(text)

            settings = get_settings()
            settings["ref_bonus"] = value
            save_settings(settings)

            await update.message.reply_text(
                f"✅ Referral bonus updated: ${value:.2f}"
            )

        # ---------- CAPACITY ----------

        elif key == "capacity":

            parts = text.split()

            if len(parts) != 2:
                raise ValueError(
                    "Use: 880 150"
                )

            code = parts[0]
            limit = int(parts[1])

            set_capacity(
                code,
                limit
            )

            await update.message.reply_text(
                f"✅ Capacity updated!\n\n"
                f"🌍 Code: {code}\n"
                f"📊 Limit: {limit}"
            )

        # ---------- ADD ADMIN ----------

        elif key == "add_admin":

            new_admin = int(text)

            admins = get_admins()

            if new_admin not in admins:

                admins.append(
                    new_admin
                )

                save_json(
                    ADMINS_FILE,
                    admins
                )

                await update.message.reply_text(
                    f"✅ Admin added:\n"
                    f"`{new_admin}`",
                    parse_mode="Markdown"
                )

            else:

                await update.message.reply_text(
                    "⚠️ This user is already an admin."
                )

    except Exception as e:

        await update.message.reply_text(
            f"❌ Invalid input.\n\n"
            f"Error: {e}"
        )


# ====================== CONFIG ======================

API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")


# ====================== CANCEL ======================

async def cancel(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    context.user_data.clear()

    await update.message.reply_text(
        "✅ Cancelled."
    )

    return ConversationHandler.END


# ============================================================
# PART 3 — MAIN + HANDLER REGISTRATION
# ============================================================

def main():

    # --------------------------------------------------------
    # Check required configuration
    # --------------------------------------------------------

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN is not set in environment variables.")
        return

    if not API_ID or not API_HASH:
        print("❌ API_ID / API_HASH is not configured.")
        return

    print("✅ Configuration loaded successfully.")

    # তোমার Application/handler registration এখানে থাকবে
    # --------------------------------------------------------
    # Create Telegram Bot Application
    # --------------------------------------------------------

    app = (
        Application
        .builder()
        .token(BOT_TOKEN)
        .build()
    )

    # ========================================================
    # WITHDRAW CONVERSATION
    # ========================================================

    wd_conv = ConversationHandler(

        entry_points=[
            CommandHandler(
                "withdraw",
                withdraw
            )
        ],

        states={

            WD_METHOD: [
                CallbackQueryHandler(
                    wd_method,
                    pattern=r"^wd_(card|bep|cancel)$"
                )
            ],

            WD_DETAILS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    wd_details
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel
            )
        ],

        allow_reentry=True
    )

    # ========================================================
    # SUPPORT CONVERSATION
    # ========================================================

    support_conv = ConversationHandler(

        entry_points=[
            CommandHandler(
                "support",
                support_start
            )
        ],

        states={

            SUPPORT_MSG: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    support_message
                )
            ]
        },

        fallbacks=[
            CommandHandler(
                "cancel",
                cancel
            )
        ],

        allow_reentry=True
    )

    # ========================================================
# BASIC USER COMMANDS
# ========================================================

app.add_handler(
    CommandHandler(
        "start",
        start
    )
)

app.add_handler(
    CommandHandler(
        "balance",
        balance_cmd
    )
)

app.add_handler(
    CommandHandler(
        "language",
        language_cmd
    )
)

app.add_handler(
    CommandHandler(
        "myaccounts",
        myaccounts_cmd
    )
)

app.add_handler(
    CommandHandler(
        "support",
        support_start
    )
)

app.add_handler(
    CommandHandler(
        "cancel",
        cancel
    )
)

    # ========================================================
    # WITHDRAW / SUPPORT CONVERSATIONS
    # ========================================================

    app.add_handler(
        wd_conv
    )

    app.add_handler(
        support_conv
    )

    # ========================================================
    # ADMIN COMMANDS
    # ========================================================

    app.add_handler(
        CommandHandler(
            "dashboard",
            dashboard
        )
    )

    app.add_handler(
        CommandHandler(
            "stats",
            stats_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "broadcast",
            broadcast_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "userinfo",
            userinfo_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "freeze",
            freeze_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "unfreeze",
            unfreeze_cmd
        )
    )

    app.add_handler(
        CommandHandler(
            "on",
            bot_on
        )
    )

    app.add_handler(
        CommandHandler(
            "off",
            bot_off
        )
    )

    app.add_handler(
        CommandHandler(
            "setcountry",
            set_country
        )
    )

    app.add_handler(
        CommandHandler(
            "capacity",
            set_capacity_cmd
        )
    )

    # ========================================================
    # CALLBACK QUERIES
    # ========================================================

    # Language buttons
    app.add_handler(
        CallbackQueryHandler(
            admin_cb,
            pattern=r"^(lang_en|lang_bn)$"
        )
    )

    # Withdraw buttons
    # These are already handled by wd_conv.
    # Do not register another generic withdraw handler.

    # Admin buttons
    app.add_handler(
        CallbackQueryHandler(
            admin_cb,
            pattern=r"^(set_price|set_wait|set_ref|set_capacity|add_admin|list_admins|back_dashboard|reply_\d+)$"
        )
    )

    # ========================================================
    # ADMIN TEXT INPUT
    # ========================================================

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_edit
        )
    )

# ========================================================
    # START BOT
    # ========================================================

    print("========================================")
    print("🚀 Bot is starting...")
    print("========================================")

    try:
        app.run_polling(
            drop_pending_updates=True
        )

    except KeyboardInterrupt:
        print("\n🛑 Bot stopped by user.")

    except Exception as e:
        print(f"\n❌ Bot stopped بسبب error: {e}")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
