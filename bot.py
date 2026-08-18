import os
import json
import logging
import tempfile
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes, ConversationHandler
)
import requests
from bs4 import BeautifulSoup
import yt_dlp

# ==================== CONFIG ====================
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))  # Railway-তে ADMIN_ID সেট করবে
DATA_FILE = "data.json"

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
WAITING_CUSTOM_REASON = 1

# ==================== DATA FUNCTIONS ====================
def load_data():
    if not os.path.exists(DATA_FILE):
        return {
            "approved": [],
            "pending": {},
            "search_history": {},
            "video_history": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_approved(user_id):
    data = load_data()
    return str(user_id) in data["approved"] or user_id == ADMIN_ID

def add_search_history(user_id, query):
    data = load_data()
    uid = str(user_id)
    if uid not in data["search_history"]:
        data["search_history"][uid] = []
    data["search_history"][uid].append({
        "query": query,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    # শুধু শেষ ৫০টা রাখবে
    data["search_history"][uid] = data["search_history"][uid][-50:]
    save_data(data)

def add_video_history(user_id, title, url):
    data = load_data()
    uid = str(user_id)
    if uid not in data["video_history"]:
        data["video_history"][uid] = []
    data["video_history"][uid].append({
        "title": title,
        "url": url,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    })
    data["video_history"][uid] = data["video_history"][uid][-100:]
    save_data(data)

# ==================== START ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id == ADMIN_ID or is_approved(user_id):
        keyboard = [
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search")],
            [InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard")] if user_id == ADMIN_ID else []
        ]
        # খালি লিস্ট রিমুভ
        keyboard = [k for k in keyboard if k]

        await update.message.reply_text(
            f"স্বাগতম {user.first_name}! 🔥\n\n"
            "তুমি বট ব্যবহার করতে পারো।\n"
            "নিচের বাটন ব্যবহার করো অথবা সরাসরি কিওয়ার্ড লিখে সার্চ করতে পারো।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

    # সাধারণ ইউজার
    keyboard = [
        [InlineKeyboardButton("✅ Request পাঠাও", callback_data="request_access")],
        [InlineKeyboardButton("📝 Custom Request", callback_data="custom_request")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel_request")]
    ]
    await update.message.reply_text(
        f"হ্যালো {user.first_name}!\n\n"
        "এই বট শুধুমাত্র অনুমোদিত ইউজাররা ব্যবহার করতে পারে।\n\n"
        "ব্যবহার করতে চাইলে **Request** বাটনে ক্লিক করো।",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== CALLBACK HANDLER ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    user_id = user.id

    # ---------- Request Access ----------
    if data == "request_access":
        db = load_data()
        db["pending"][str(user_id)] = {
            "name": user.full_name,
            "username": user.username or "None",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_data(db)

        # Admin কে পাঠাও
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
            ]
        ]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 নতুন Request!\n\n"
                 f"Name: {user.full_name}\n"
                 f"Username: @{user.username or 'None'}\n"
                 f"Chat ID: `{user_id}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.edit_message_text("✅ তোমার Request Admin-এর কাছে পাঠানো হয়েছে। অনুমোদনের অপেক্ষা করো।")

    elif data == "cancel_request":
        await query.edit_message_text("Request বাতিল করা হয়েছে।")

    elif data == "custom_request":
        await query.edit_message_text("কি কারণে বট ব্যবহার করতে চাও? নিচে লিখে পাঠাও:")
        return WAITING_CUSTOM_REASON

    # ---------- Approve / Reject ----------
    elif data.startswith("approve_"):
        target_id = data.split("_")[1]
        db = load_data()
        if target_id not in db["approved"]:
            db["approved"].append(target_id)
        if target_id in db["pending"]:
            del db["pending"][target_id]
        save_data(db)

        await query.edit_message_text(f"✅ User {target_id} Approve করা হয়েছে।")
        try:
            await context.bot.send_message(chat_id=int(target_id), text="🎉 তোমার Request Approve হয়েছে! এখন `/start` দাও।")
        except:
            pass

    elif data.startswith("reject_"):
        target_id = data.split("_")[1]
        db = load_data()
        if target_id in db["pending"]:
            del db["pending"][target_id]
        save_data(db)

        await query.edit_message_text(f"❌ User {target_id} Reject করা হয়েছে।")
        try:
            await context.bot.send_message(chat_id=int(target_id), text="দুঃখিত, তোমার Request Reject করা হয়েছে।")
        except:
            pass

    # ---------- Menu ----------
    elif data == "menu_search":
        await query.edit_message_text("🔍 সার্চ করতে কিওয়ার্ড লিখে পাঠাও:")

    elif data == "menu_dashboard" and user_id == ADMIN_ID:
        keyboard = [
            [InlineKeyboardButton("👥 User Data", callback_data="dash_users")],
            [InlineKeyboardButton("🔍 Search History", callback_data="dash_search")],
            [InlineKeyboardButton("🎬 User Videos", callback_data="dash_videos")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ]
        await query.edit_message_text("📊 Admin Dashboard", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "dash_users" and user_id == ADMIN_ID:
        db = load_data()
        text = "👥 **Approved Users:**\n\n"
        for uid in db["approved"]:
            text += f"`{uid}`\n"
        if not db["approved"]:
            text += "কোনো ইউজার নেই"
        await query.edit_message_text(text, parse_mode="Markdown")

    elif data == "dash_search" and user_id == ADMIN_ID:
        db = load_data()
        text = "🔍 **Search History (Last):**\n\n"
        count = 0
        for uid, histories in db["search_history"].items():
            for h in histories[-3:]:
                text += f"User `{uid}` → {h['query']} ({h['time']})\n"
                count += 1
                if count > 30:
                    break
        if count == 0:
            text += "কোনো হিস্টোরি নেই"
        await query.edit_message_text(text[:4000], parse_mode="Markdown")

    elif data == "dash_videos" and user_id == ADMIN_ID:
        db = load_data()
        text = "🎬 **Downloaded Videos:**\n\n"
        count = 0
        for uid, videos in db["video_history"].items():
            for v in videos[-3:]:
                text += f"User `{uid}` → {v['title'][:40]}...\n"
                count += 1
                if count > 25:
                    break
        if count == 0:
            text += "কোনো ভিডিও নেই"
        await query.edit_message_text(text[:4000], parse_mode="Markdown")

    # ---------- Video Select ----------
    elif data.startswith("dl_"):
        if not is_approved(user_id) and user_id != ADMIN_ID:
            await query.edit_message_text("তুমি অনুমোদিত নও।")
            return

        parts = data.split("_")
        action = parts[1]  # num or all
        results = context.user_data.get("last_results", [])

        if not results:
            await query.edit_message_text("সার্চ রেজাল্ট মেয়াদোত্তীর্ণ। আবার সার্চ করো।")
            return

        if action == "all":
            await query.edit_message_text("⬇️ সব ভিডিও ডাউনলোড শুরু হচ্ছে... (সময় লাগবে)")
            for i, video in enumerate(results[:5], 1):  # সর্বোচ্চ ৫টা (নিরাপত্তার জন্য)
                await download_and_send(update, context, video, user_id)
            await context.bot.send_message(chat_id=user_id, text="✅ All প্রসেস শেষ (প্রথম ৫টা)।")
        else:
            num = int(action)
            if 1 <= num <= len(results):
                video = results[num-1]
                await query.edit_message_text(f"⬇️ ডাউনলোড হচ্ছে: {video['title'][:50]}...")
                await download_and_send(update, context, video, user_id)
            else:
                await query.edit_message_text("ভুল নাম্বার")

async def custom_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    reason = update.message.text

    db = load_data()
    db["pending"][str(user.id)] = {
        "name": user.full_name,
        "username": user.username or "None",
        "reason": reason,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    save_data(db)

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
        ]
    ]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 Custom Request!\n\n"
             f"Name: {user.full_name}\n"
             f"Username: @{user.username or 'None'}\n"
             f"Chat ID: `{user.id}`\n"
             f"Reason: {reason}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ তোমার Custom Request পাঠানো হয়েছে।")
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল করা হয়েছে।")
    return ConversationHandler.END

# ==================== SEARCH & DOWNLOAD ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not is_approved(user_id) and user_id != ADMIN_ID:
        await update.message.reply_text("তুমি এখনো অনুমোদিত নও। `/start` দিয়ে Request পাঠাও।")
        return

    if text.startswith("/"):
        return

    # সার্চ শুরু
    await update.message.reply_text(f"🔍 সার্চ করছি: **{text}** ...", parse_mode="Markdown")
    add_search_history(user_id, text)

    try:
        url = f"https://xhamster.com/search/{text}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        items = soup.select(".thumb-list__item")[:10]

        for item in items:
            title_tag = item.select_one(".video-thumb-info__name") or item.select_one("a")
            link_tag = item.select_one("a")
            img_tag = item.select_one("img")

            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                link = "https://xhamster.com" + href if href.startswith("/") else href
                thumb = img_tag.get("src") or img_tag.get("data-src") if img_tag else None

                results.append({
                    "title": title,
                    "url": link,
                    "thumb": thumb
                })

        if not results:
            await update.message.reply_text("কিছু পাওয়া যায়নি 😔")
            return

        context.user_data["last_results"] = results

        # থাম্বনেইল পাঠানো (যতগুলো সম্ভব)
        media_group = []
        for i, v in enumerate(results[:8], 1):  # Telegram media group max 10, কিন্তু ৮ রাখলাম
            if v["thumb"]:
                media_group.append(InputMediaPhoto(media=v["thumb"], caption=f"{i}. {v['title'][:60]}"))
        
        if media_group:
            await update.message.reply_media_group(media=media_group)

        # বাটন তৈরি
        buttons = []
        row = []
        for i in range(1, len(results)+1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"dl_{i}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        buttons.append([InlineKeyboardButton("📥 All (প্রথম ৫টা)", callback_data="dl_all")])

        await update.message.reply_text(
            f"✅ {len(results)}টা ভিডিও পাওয়া গেছে।\nনাম্বার সিলেক্ট করো:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        await update.message.reply_text(f"সার্চ ফেইল: {str(e)}")

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, video, user_id):
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "format": "worst[ext=mp4]/worst",
                "outtmpl": f"{tmpdir}/%(id)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video["url"], download=True)
                filename = ydl.prepare_filename(info)

            size = os.path.getsize(filename)
            if size > 49 * 1024 * 1024:
                await context.bot.send_message(chat_id=user_id, text=f"❌ {video['title'][:40]}... খুব বড় (৫০MB+)")
                return

            with open(filename, "rb") as f:
                await context.bot.send_video(chat_id=user_id, video=f, caption=video["title"][:200], supports_streaming=True)

            add_video_history(user_id, video["title"], video["url"])
            await context.bot.send_message(chat_id=user_id, text="✅ পাঠানো হয়েছে!")

    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"❌ ডাউনলোড ফেইল: {str(e)[:200]}")

# ==================== MAIN ====================
def main():
    if not TOKEN:
        print("BOT_TOKEN সেট করা হয়নি!")
        return

    if ADMIN_ID == 0:
        print("ADMIN_ID সেট করা হয়নি!")
        return

    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_handler, pattern="^custom_request$")
        ],
        states={
            WAITING_CUSTOM_REASON: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_reason)
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv)
        ]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    print("Bot চালু হয়েছে...")
    app.run_polling()


if __name__ == "__main__":
    main()
