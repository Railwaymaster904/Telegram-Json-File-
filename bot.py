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

clients = {}
pending = {}

# ====================== HELPERS ======================
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

async def check_joined(bot, user_id):
    if not FORCE_CHANNEL:
        return True
    try:
        member = await bot.get_chat_member(FORCE_CHANNEL, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

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
            codes[phone].insert(0, {"code": m.group(1), "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
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

# ====================== USER HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if FORCE_CHANNEL and not await check_joined(context.bot, user.id):
        kb = [[InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{str(FORCE_CHANNEL).replace('@','')}")]]
        await update.message.reply_text("⚠️ Please join our channel first.", reply_markup=InlineKeyboardMarkup(kb))
        return

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
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        f"Send number with +\nExample: `+8801712345678`\n\n"
        f"🔗 Referral: `{link}`\n\n"
        f"/balance /withdraw /support /myaccounts",
        parse_mode="Markdown"
    )

async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = load_json(BALANCES_FILE, {}).get(str(update.effective_user.id), 0)
    await update.message.reply_text(f"💰 Balance: **${bal:.2f}**", parse_mode="Markdown")

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_on() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🔴 Bot is currently OFF.")
        return

    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    if is_frozen(phone):
        await update.message.reply_text(f"❄️ This number is frozen.\n`{phone}`", parse_mode="Markdown")
        return

    # Capacity check
    code = get_country_code(phone)
    limit = get_capacity(code)
    accs = load_json(ACCOUNTS_FILE, {})
    current = sum(1 for p in accs if p.startswith(f"+{code}"))
    if current >= limit:
        await update.message.reply_text(f"❌ Capacity full for `{code}` ({current}/{limit})", parse_mode="Markdown")
        return

    wait_msg = await update.message.reply_text("⏳ Waiting for otp...")

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait_msg.edit_text("Already logged in!")
            await client.disconnect()
            return

        sent = await client.send_code_request(phone)
        pending[chat_id] = {"client": client, "phone": phone, "hash": sent.phone_code_hash, "uid": uid}

        flag = get_flag(phone)
        await wait_msg.edit_text(
            f"📲 {flag} `{phone}`\n\nCode sent! Reply with the login code.\n\n➿ /cancel",
            parse_mode="Markdown"
        )
        return WAITING_CODE
    except FloodWaitError as e:
        await wait_msg.edit_text(f"FloodWait! Wait {e.seconds}s")
    except Exception as e:
        await wait_msg.edit_text(f"Error: {e}")

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        return

    data = pending[chat_id]
    code = update.message.text.strip()

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        await update.message.reply_text("Already has 2FA. Skipped.")
        await data["client"].disconnect()
        del pending[chat_id]
        return
    except PhoneCodeInvalidError:
        await update.message.reply_text("❗️ Invalid code. Try again.\n\n➿ /cancel")
        return
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        await data["client"].disconnect()
        del pending[chat_id]
        return

    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"], TWO_FA_PASSWORD)

    country_code = get_country_code(data["phone"])
    c_set = get_country_setting(country_code)
    price = c_set.get("price", get_settings()["price"])
    wait = c_set.get("wait", get_settings()["wait"])

    claim_id = f"{data['uid']}_{data['phone'][1:]}_{int(datetime.now().timestamp())}"

    accs = load_json(ACCOUNTS_FILE, {})
    accs[data["phone"]] = {
        "uid": data["uid"],
        "name": me.first_name or "",
        "price": price,
        "wait": wait,
        "claim_id": claim_id
    }
    save_json(ACCOUNTS_FILE, accs)

    claims = load_json(CLAIMS_FILE, {})
    claims[claim_id] = {
        "uid": data["uid"],
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
    kb = [[InlineKeyboardButton("💰 Claim Balance", callback_data=f"claim_{claim_id}")]]
    await update.message.reply_text(
        f"✅ **Account Received** {flag}\n"
        f"• Number: `{data['phone']}`\n"
        f"• Price: ${price}\n"
        f"• Wait: {wait} hrs\n"
        f"• 2FA: {'✅' if ok else '❌'}",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def claim_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = q.data.replace("claim_", "")
    claims = load_json(CLAIMS_FILE, {})

    if cid not in claims or claims[cid]["done"]:
        await q.edit_message_text("Already claimed")
        return

    c = claims[cid]
    if c["uid"] != q.from_user.id:
        await q.answer("Not yours", show_alert=True)
        return

    unlock = datetime.fromisoformat(c["time"]) + timedelta(hours=c["wait"])
    if datetime.now() < unlock:
        left = unlock - datetime.now()
        await q.answer(f"Wait {int(left.total_seconds()//3600)}h {int((left.total_seconds()%3600)//60)}m", show_alert=True)
        return

    newb = add_balance(c["uid"], c["price"])
    refs = load_json(REFS_FILE, {})
    if str(c["uid"]) in refs:
        add_balance(refs[str(c["uid"])], get_settings()["ref_bonus"])

    c["done"] = True
    claims[cid] = c
    save_json(CLAIMS_FILE, claims)
    await q.edit_message_text(f"✅ +${c['price']}\nBalance: ${newb:.2f}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in pending:
        try:
            await pending[chat_id]["client"].disconnect()
        except:
            pass
        del pending[chat_id]
    await update.message.reply_text("✅ Cancelled.")
    return ConversationHandler.END

# ====================== SUPPORT & WITHDRAW ======================
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧑🏻‍💻 Send your message.\n/cancel to cancel")
    return SUPPORT_MSG

async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    for admin_id in get_admins():
        try:
            kb = [[InlineKeyboardButton("💬 Reply", callback_data=f"reply_{user.id}")]]
            await context.bot.send_message(
                admin_id,
                f"🆘 Support\nFrom: {user.first_name} (`{user.id}`)\n\n{text}",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode="Markdown"
            )
        except:
            pass
    await update.message.reply_text("✅ Sent to support.")
    return ConversationHandler.END

async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = load_json(BALANCES_FILE, {}).get(str(update.effective_user.id), 0)
    if bal < MIN_WITHDRAW:
        await update.message.reply_text(f"Min ${MIN_WITHDRAW}. You have ${bal:.2f}")
        return ConversationHandler.END

    kb = [
        [InlineKeyboardButton("💳 Leader Card", callback_data="wd_card")],
        [InlineKeyboardButton("🟡 Binance BEP20", callback_data="wd_bep")],
        [InlineKeyboardButton("❌ Cancel", callback_data="wd_cancel")]
    ]
    await update.message.reply_text(f"Balance: ${bal:.2f}\nSelect method:", reply_markup=InlineKeyboardMarkup(kb))
    return WD_METHOD

async def wd_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "wd_cancel":
        await q.edit_message_text("Cancelled")
        return ConversationHandler.END
    context.user_data["method"] = "Leader Card" if q.data == "wd_card" else "Binance BEP20"
    await q.edit_message_text("Send your details:")
    return WD_DETAILS

async def wd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    details = update.message.text
    method = context.user_data.get("method")
    bal = load_json(BALANCES_FILE, {}).get(str(user.id), 0)
    accs = sum(1 for a in load_json(ACCOUNTS_FILE, {}).values() if a.get("uid") == user.id)

    b = load_json(BALANCES_FILE, {})
    b[str(user.id)] = 0
    save_json(BALANCES_FILE, b)

    text = (
        f"💸 New Withdrawal\n\n"
        f"Name: {user.first_name}\nID: `{user.id}`\n"
        f"Username: @{user.username or 'None'}\n"
        f"Accounts: {accs}\nAmount: ${bal:.2f}\n"
        f"Method: {method}\nDetails: {details}"
    )
    if WITHDRAW_CHANNEL:
        try:
            await context.bot.send_message(int(WITHDRAW_CHANNEL), text, parse_mode="Markdown")
        except:
            pass
    await update.message.reply_text("✅ Request submitted!")
    return ConversationHandler.END

# ====================== ADMIN ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    s = get_settings()
    accs = len(load_json(ACCOUNTS_FILE, {}))
    total_bal = sum(load_json(BALANCES_FILE, {}).values())

    text = (
        f"📊 **Dashboard**\n\n"
        f"Accounts: `{accs}`\nOnline: `{len(clients)}`\n"
        f"Balance: `${total_bal:.2f}`\n"
        f"Price: `${s['price']}` | Wait: `{s['wait']}h`"
    )
    kb = [
        [InlineKeyboardButton("💰 Set Price", callback_data="set_price"),
         InlineKeyboardButton("⏱ Set Wait", callback_data="set_wait")],
        [InlineKeyboardButton("🎁 Set Ref", callback_data="set_ref")],
        [InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
         InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")],
        [InlineKeyboardButton("📥 Codes", callback_data="dl_codes"),
         InlineKeyboardButton("📁 Sessions", callback_data="dl_sess")],
        [InlineKeyboardButton("📋 Accounts", callback_data="list_acc")]
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
        await q.edit_message_text("Send new price (e.g. 0.35)")
    elif data == "set_wait":
        context.user_data["edit"] = "wait"
        await q.edit_message_text("Send wait hours (e.g. 18)")
    elif data == "set_ref":
        context.user_data["edit"] = "ref"
        await q.edit_message_text("Send referral bonus (e.g. 0.05)")
    elif data == "add_admin":
        context.user_data["edit"] = "add_admin"
        await q.edit_message_text("Send new admin User ID")
    elif data == "remove_admin":
        admins = get_admins()
        kb = [[InlineKeyboardButton(f"Remove {a}", callback_data=f"rmadmin_{a}")] for a in admins if a != q.from_user.id]
        await q.edit_message_text("Select admin to remove:", reply_markup=InlineKeyboardMarkup(kb))
    elif data.startswith("rmadmin_"):
        aid = int(data.split("_")[1])
        admins = get_admins()
        if aid in admins and len(admins) > 1:
            admins.remove(aid)
            save_json(ADMINS_FILE, admins)
            await q.edit_message_text(f"✅ Removed {aid}")
    elif data.startswith("reply_"):
        context.user_data["reply_to"] = int(data.split("_")[1])
        await q.edit_message_text("Send reply message:")
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
        text = f"Total: {len(accs)}\n\n" + "\n".join([f"`{p}`" for p in list(accs.keys())[:40]])
        await q.edit_message_text(text or "Empty", parse_mode="Markdown")

async def admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if "reply_to" in context.user_data:
        uid = context.user_data.pop("reply_to")
        try:
            await context.bot.send_message(uid, f"📩 Support Reply:\n\n{update.message.text}")
            await update.message.reply_text("✅ Reply sent")
        except:
            await update.message.reply_text("Failed")
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
                await update.message.reply_text(f"✅ Added admin `{new_id}`", parse_mode="Markdown")
        else:
            val = float(text) if key != "wait" else int(text)
            s = get_settings()
            if key == "price": s["price"] = val
            elif key == "wait": s["wait"] = val
            elif key == "ref": s["ref_bonus"] = val
            save_settings(s)
            await update.message.reply_text(f"✅ Updated {key} = {val}")
    except:
        await update.message.reply_text("Invalid value")

# ====================== EXTRA ADMIN COMMANDS ======================
async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        set_bot_status(True)
        await update.message.reply_text("✅ Bot ON")

async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if is_admin(update.effective_user.id):
        set_bot_status(False)
        await update.message.reply_text("🔴 Bot OFF")

async def myaccounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accs = [p for p, i in load_json(ACCOUNTS_FILE, {}).items() if i.get("uid") == uid]
    if not accs:
        await update.message.reply_text("No accounts yet.")
        return
    text = f"Your Accounts ({len(accs)}):\n\n" + "\n".join([f"{get_flag(p)} `{p}`" for p in accs[:30]])
    await update.message.reply_text(text, parse_mode="Markdown")

async def post_init(app):
    for phone in load_json(ACCOUNTS_FILE, {}):
        try:
            await start_client(phone)
        except:
            pass
    print("Bot Ready!")

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

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
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True,
    )

    # Withdraw Conversation
    wd_conv = ConversationHandler(
        entry_points=[
            CommandHandler("withdraw", withdraw)
        ],
        states={
            WD_METHOD: [
                CallbackQueryHandler(wd_method)
            ],
            WD_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wd_details)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    # Support Conversation
    support_conv = ConversationHandler(
        entry_points=[
            CommandHandler("support", support_start)
        ],
        states={
            SUPPORT_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_message)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
    )

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("on", bot_on))
    app.add_handler(CommandHandler("off", bot_off))
    app.add_handler(CommandHandler("myaccounts", myaccounts_cmd))

    # Conversation Handlers
    app.add_handler(login_conv)
    app.add_handler(wd_conv)
    app.add_handler(support_conv)

    # Callback Queries
    app.add_handler(CallbackQueryHandler(claim_cb, pattern=r"^claim_"))
    app.add_handler(CallbackQueryHandler(admin_cb))

    # Admin Text Handler (শেষে রাখো)
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit)
    )

    print("Running...")
    app.run_polling()


if __name__ == "__main__":
    main()
