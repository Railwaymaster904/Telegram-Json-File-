import os
import json
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError
from telethon.tl.functions.account import GetAuthorizationsRequest, ResetAuthorizationRequest

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

SESSIONS_DIR = "sessions"
DATA_DIR = "data"
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Conversation states
PHONE, CODE, PASSWORD = range(3)

# Global
clients = {}          # phone -> TelegramClient
pending = {}          # chat_id -> data
codes_data = {}       # phone -> list of codes


def load_json(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


def get_accounts():
    return load_json(ACCOUNTS_FILE, {})


def save_accounts(data):
    save_json(ACCOUNTS_FILE, data)


# ====================== Telethon Code Receiver ======================

async def start_client(phone: str):
    """একটা ক্লায়েন্ট চালু করে কোড লিসেনার যোগ করে"""
    session_path = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
    client = TelegramClient(session_path, API_ID, API_HASH)

    @client.on(events.NewMessage(from_users=777000))
    async def code_handler(event):
        text = event.message.message or ""
        # কোড বের করা
        match = re.search(r'(\d{5,6})', text)
        if match:
            code = match.group(1)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if phone not in codes_data:
                codes_data[phone] = []
            codes_data[phone].insert(0, {
                "code": code,
                "time": now,
                "full_text": text[:200]
            })
            # শুধু শেষ ১০টা রাখব
            codes_data[phone] = codes_data[phone][:10]
            save_json(CODES_FILE, codes_data)

            # অ্যাডমিনকে নোটিফিকেশন
            try:
                app = Application.builder().token(BOT_TOKEN).build()
                await app.bot.send_message(
                    ADMIN_ID,
                    f"🔔 নতুন লগইন কোড এসেছে!\n\n"
                    f"নাম্বার: `{phone}`\n"
                    f"কোড: `{code}`\n"
                    f"সময়: {now}"
                )
            except:
                pass

    await client.connect()
    if await client.is_user_authorized():
        clients[phone] = client
        return True
    else:
        await client.disconnect()
        return False


async def load_all_clients():
    """সব সেভ করা সেশন লোড করে"""
    accounts = get_accounts()
    for phone in accounts:
        try:
            ok = await start_client(phone)
            if ok:
                print(f"✅ Loaded: {phone}")
            else:
                print(f"❌ Not authorized: {phone}")
        except Exception as e:
            print(f"Error loading {phone}: {e}")


# ====================== Bot Handlers ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("অ্যাক্সেস নেই।")
        return

    keyboard = [
        [KeyboardButton("📊 Dashboard")],
        [KeyboardButton("➕ Add Account"), KeyboardButton("📥 Download Codes")],
        [KeyboardButton("📁 Download Sessions"), KeyboardButton("📋 List Accounts")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "স্বাগতম অ্যাডমিন!\nনিচের বাটনগুলো ব্যবহার করো।",
        reply_markup=reply_markup
    )


async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = get_accounts()
    total = len(accounts)
    online = len(clients)

    text = (
        f"📊 **Dashboard**\n\n"
        f"মোট অ্যাকাউন্ট: **{total}**\n"
        f"অনলাইন: **{online}**\n"
        f"কোড ফাইল: `data/codes.json`"
    )

    keyboard = [
        [
            InlineKeyboardButton("📥 Download Codes", callback_data="dl_codes"),
            InlineKeyboardButton("📁 Download Sessions", callback_data="dl_sessions")
        ],
        [
            InlineKeyboardButton("📋 List Accounts", callback_data="list_acc"),
            InlineKeyboardButton("🔄 Reload Clients", callback_data="reload")
        ],
        [
            InlineKeyboardButton("➕ Add Account", callback_data="add_acc")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="Markdown")


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not is_admin(query.from_user.id):
        return

    data = query.data

    if data == "dl_codes":
        await download_codes(update, context, from_callback=True)
    elif data == "dl_sessions":
        await download_sessions(update, context, from_callback=True)
    elif data == "list_acc":
        await list_accounts(update, context, from_callback=True)
    elif data == "reload":
        await query.edit_message_text("রিলোড হচ্ছে...")
        await load_all_clients()
        await dashboard(update, context)
    elif data == "add_acc":
        await query.edit_message_text("নতুন অ্যাকাউন্ট যোগ করতে:\n`/login +8801XXXXXXXXX`", parse_mode="Markdown")


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    if not context.args:
        await update.message.reply_text("ব্যবহার: `/login +8801XXXXXXXXX`", parse_mode="Markdown")
        return ConversationHandler.END

    phone = context.args[0].strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    chat_id = update.effective_chat.id

    try:
        session_path = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await update.message.reply_text(f"{phone} ইতিমধ্যে লগইন আছে!")
            await client.disconnect()
            return ConversationHandler.END

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash
        }

        await update.message.reply_text(f"{phone} এ কোড পাঠানো হয়েছে।\nকোডটা এখানে পাঠাও:")
        return CODE

    except FloodWaitError as e:
        await update.message.reply_text(f"FloodWait: {e.seconds} সেকেন্ড অপেক্ষা করো।")
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"এরর: {e}")
        return ConversationHandler.END


async def receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    chat_id = update.effective_chat.id
    if chat_id not in pending:
        await update.message.reply_text("আগে `/login` দাও।")
        return ConversationHandler.END

    code = update.message.text.strip()
    data = pending[chat_id]
    client = data["client"]
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
        me = await client.get_me()

        # সেভ করা
        accounts = get_accounts()
        accounts[phone] = {
            "name": me.first_name or "",
            "username": me.username or "",
            "id": me.id,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_accounts(accounts)

        await client.disconnect()
        # আবার চালু করা (কোড লিসেনারসহ)
        await start_client(phone)

        del pending[chat_id]
        await update.message.reply_text(
            f"✅ সফলভাবে লগইন হয়েছে!\n"
            f"নাম: {me.first_name}\n"
            f"নাম্বার: {phone}"
        )
        return ConversationHandler.END

    except SessionPasswordNeededError:
        await update.message.reply_text("২FA পাসওয়ার্ড আছে। পাসওয়ার্ড পাঠাও:")
        return PASSWORD
    except PhoneCodeInvalidError:
        await update.message.reply_text("কোড ভুল। আবার চেষ্টা করো বা /cancel দাও।")
        return CODE
    except Exception as e:
        await client.disconnect()
        del pending[chat_id]
        await update.message.reply_text(f"এরর: {e}")
        return ConversationHandler.END


async def receive_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END

    chat_id = update.effective_chat.id
    if chat_id not in pending:
        return ConversationHandler.END

    password = update.message.text.strip()
    data = pending[chat_id]
    client = data["client"]
    phone = data["phone"]

    try:
        await client.sign_in(password=password)
        me = await client.get_me()

        accounts = get_accounts()
        accounts[phone] = {
            "name": me.first_name or "",
            "username": me.username or "",
            "id": me.id,
            "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_accounts(accounts)

        await client.disconnect()
        await start_client(phone)

        del pending[chat_id]
        await update.message.reply_text(f"✅ ২FA সহ লগইন সফল!\nনাম: {me.first_name}")
        return ConversationHandler.END

    except Exception as e:
        await client.disconnect()
        del pending[chat_id]
        await update.message.reply_text(f"এরর: {e}")
        return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in pending:
        try:
            await pending[chat_id]["client"].disconnect()
        except:
            pass
        del pending[chat_id]
    await update.message.reply_text("বাতিল করা হয়েছে।")
    return ConversationHandler.END


async def list_accounts(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    if not is_admin(update.effective_user.id if not from_callback else update.callback_query.from_user.id):
        return

    accounts = get_accounts()
    if not accounts:
        text = "কোনো অ্যাকাউন্ট নেই।"
    else:
        text = f"মোট অ্যাকাউন্ট: {len(accounts)}\n\n"
        for i, (phone, info) in enumerate(list(accounts.items())[:40], 1):
            status = "🟢" if phone in clients else "🔴"
            text += f"{i}. {status} `{phone}` - {info.get('name', '')}\n"
        if len(accounts) > 40:
            text += f"\n... আরও {len(accounts)-40} টি আছে"

    if from_callback:
        await update.callback_query.edit_message_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")


async def download_codes(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    if not is_admin(update.effective_user.id if not from_callback else update.callback_query.from_user.id):
        return

    # লেটেস্ট ডাটা লোড
    global codes_data
    codes_data = load_json(CODES_FILE, {})

    if not codes_data:
        text = "এখনো কোনো কোড আসেনি।"
        if from_callback:
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return

    # ফাইল তৈরি
    file_path = os.path.join(DATA_DIR, "latest_codes.json")
    save_json(file_path, codes_data)

    caption = f"মোট {len(codes_data)} টি নাম্বারের কোড আছে।"

    if from_callback:
        await update.callback_query.message.reply_document(
            document=open(file_path, "rb"),
            filename="codes.json",
            caption=caption
        )
    else:
        await update.message.reply_document(
            document=open(file_path, "rb"),
            filename="codes.json",
            caption=caption
        )


async def download_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE, from_callback=False):
    if not is_admin(update.effective_user.id if not from_callback else update.callback_query.from_user.id):
        return

    import zipfile
    zip_path = os.path.join(DATA_DIR, "all_sessions.zip")

    with zipfile.ZipFile(zip_path, "w") as zipf:
        for f in os.listdir(SESSIONS_DIR):
            if f.endswith(".session"):
                zipf.write(os.path.join(SESSIONS_DIR, f), f)

    caption = "সব সেশন ফাইল"

    if from_callback:
        await update.callback_query.message.reply_document(
            document=open(zip_path, "rb"),
            filename="all_sessions.zip",
            caption=caption
        )
    else:
        await update.message.reply_document(
            document=open(zip_path, "rb"),
            filename="all_sessions.zip",
            caption=caption
        )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    text = update.message.text

    if text == "📊 Dashboard":
        await dashboard(update, context)
    elif text == "➕ Add Account":
        await update.message.reply_text("নাম্বার দাও:\n`/login +8801XXXXXXXXX`", parse_mode="Markdown")
    elif text == "📥 Download Codes":
        await download_codes(update, context)
    elif text == "📁 Download Sessions":
        await download_sessions(update, context)
    elif text == "📋 List Accounts":
        await list_accounts(update, context)


async def logout_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """কোনো অ্যাকাউন্ট বট থেকে লগআউট করতে"""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("ব্যবহার: `/logout +8801XXXXXXXXX`", parse_mode="Markdown")
        return

    phone = context.args[0].strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    if phone in clients:
        try:
            await clients[phone].log_out()
            del clients[phone]
            await update.message.reply_text(f"{phone} লগআউট করা হয়েছে।")
        except Exception as e:
            await update.message.reply_text(f"এরর: {e}")
    else:
        await update.message.reply_text("এই নাম্বার অনলাইন নেই।")


async def post_init(app: Application):
    """বট স্টার্ট হলে সব ক্লায়েন্ট লোড করবে"""
    print("Loading all sessions...")
    await load_all_clients()
    print("Ready!")


def main():
    global codes_data
    codes_data = load_json(CODES_FILE, {})

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("login", login_command)],
        states={
            CODE: [MessageHandler(filters.TEXT & \~filters.COMMAND, receive_code)],
            PASSWORD: [MessageHandler(filters.TEXT & \~filters.COMMAND, receive_password)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("logout", logout_command))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, text_handler))

    print("Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
