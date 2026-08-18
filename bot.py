import os
import json
import logging
import tempfile
import random
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
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))
DATA_FILE = "data.json"

# অটো সার্চ কিওয়ার্ড (বাংলা রিলেটেড)
AUTO_KEYWORDS = [
    "bangla", "bengali", "desi", "kolkata", "dhaka",
    "bangla sex", "bengali sex", "desi sex", "bangla hot",
    "bengali girl", "desi girl", "bangla couple"
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_CUSTOM_REASON = 1

# ==================== DATA FUNCTIONS ====================
def load_data():
    default = {
        "approved": [],
        "pending": {},
        "search_history": {},
        "video_history": {},
        "database": [],          # অটো সার্চের ভিডিও এখানে জমা হবে
        "auto_search": False     # অটো সার্চ অন/অফ
    }
    if not os.path.exists(DATA_FILE):
        return default
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        for key in default:
            if key not in data:
                data[key] = default[key]
        return data

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

def add_to_database(videos):
    """নতুন ভিডিও database-এ যোগ করে (ডুপ্লিকেট এড়িয়ে)"""
    data = load_data()
    existing_urls = {v["url"] for v in data["database"]}
    
    added = 0
    for v in videos:
        if v["url"] not in existing_urls:
            data["database"].append(v)
            added += 1
    
    # শুধু শেষ ১০০০টা রাখবে
    data["database"] = data["database"][-1000:]
    save_data(data)
    return added

# ==================== AUTO SEARCH JOB ====================
async def auto_search_job(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data.get("auto_search", False):
        return

    keyword = random.choice(AUTO_KEYWORDS)
    logger.info(f"Auto searching: {keyword}")

    try:
        url = f"https://xhamster.com/search/{keyword}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        items = soup.select(".thumb-list__item")[:8]

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
                    "thumb": thumb,
                    "keyword": keyword,
                    "added": datetime.now().strftime("%Y-%m-%d %H:%M")
                })

        if results:
            added = add_to_database(results)
            logger.info(f"Auto search '{keyword}' → {added} new videos added")

    except Exception as e:
        logger.error(f"Auto search error: {e}")

# ==================== START ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if user_id == ADMIN_ID or is_approved(user_id):
        keyboard = [
            [InlineKeyboardButton("🔍 Search", callback_data="menu_search")]
        ]
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard")])

        await update.message.reply_text(
            f"স্বাগতম {user.first_name}! 🔥\n\n"
            "তুমি বট ব্যবহার করতে পারো।\n"
            "নিচের বাটন ব্যবহার করো অথবা সরাসরি কিওয়ার্ড লিখে সার্চ করো।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return

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

# ==================== BUTTON HANDLER ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = query.from_user
    user_id = user.id

    # Request
    if data == "request_access":
        db = load_data()
        db["pending"][str(user_id)] = {
            "name": user.full_name,
            "username": user.username or "None",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
        save_data(db)

        keyboard = [[
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        ]]
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"🔔 নতুন Request!\n\nName: {user.full_name}\nUsername: @{user.username or 'None'}\nChat ID: `{user_id}`",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await query.edit_message_text("✅ Request পাঠানো হয়েছে। অপেক্ষা করো।")

    elif data == "cancel_request":
        await query.edit_message_text("Request বাতিল করা হয়েছে।")

    elif data == "custom_request":
        await query.edit_message_text("কি কারণে বট ব্যবহার করতে চাও? লিখে পাঠাও:")
        return WAITING_CUSTOM_REASON

    # Approve / Reject
    elif data.startswith("approve_"):
        target_id = data.split("_")[1]
        db = load_data()
        if target_id not in db["approved"]:
            db["approved"].append(target_id)
        if target_id in db["pending"]:
            del db["pending"][target_id]
        save_data(db)
        await query.edit_message_text(f"✅ User {target_id} Approve হয়েছে।")
        try:
            await context.bot.send_message(chat_id=int(target_id), text="🎉 Approve হয়েছে! এখন /start দাও।")
        except: pass

    elif data.startswith("reject_"):
        target_id = data.split("_")[1]
        db = load_data()
        if target_id in db["pending"]:
            del db["pending"][target_id]
        save_data(db)
        await query.edit_message_text(f"❌ User {target_id} Reject হয়েছে।")
        try:
            await context.bot.send_message(chat_id=int(target_id), text="দুঃখিত, Request Reject করা হয়েছে।")
        except: pass

    # Menu
    elif data == "menu_search":
        await query.edit_message_text("🔍 সার্চ করতে কিওয়ার্ড লিখে পাঠাও:")

    elif data == "menu_dashboard" and user_id == ADMIN_ID:
        db = load_data()
        auto_status = "🟢 ON" if db.get("auto_search") else "🔴 OFF"
        keyboard = [
            [InlineKeyboardButton("👥 User Data", callback_data="dash_users")],
            [InlineKeyboardButton("🔍 Search History", callback_data="dash_search")],
            [InlineKeyboardButton("🎬 User Videos", callback_data="dash_videos")],
            [InlineKeyboardButton(f"🗄️ Database ({len(db.get('database', []))})", callback_data="dash_database_0")],
            [InlineKeyboardButton(f"⚙️ Auto Search: {auto_status}", callback_data="toggle_auto")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ]
        await query.edit_message_text("📊 Admin Dashboard", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back_main":
        keyboard = [[InlineKeyboardButton("🔍 Search", callback_data="menu_search")]]
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard")])
        await query.edit_message_text("স্বাগতম! 🔥\n\nনিচের বাটন ব্যবহার করো:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "toggle_auto" and user_id == ADMIN_ID:
        db = load_data()
        db["auto_search"] = not db.get("auto_search", False)
        save_data(db)
        status = "ON 🟢" if db["auto_search"] else "OFF 🔴"
        await query.answer(f"Auto Search এখন {status}")
        # Dashboard আবার দেখাও
        auto_status = "🟢 ON" if db["auto_search"] else "🔴 OFF"
        keyboard = [
            [InlineKeyboardButton("👥 User Data", callback_data="dash_users")],
            [InlineKeyboardButton("🔍 Search History", callback_data="dash_search")],
            [InlineKeyboardButton("🎬 User Videos", callback_data="dash_videos")],
            [InlineKeyboardButton(f"🗄️ Database ({len(db.get('database', []))})", callback_data="dash_database_0")],
            [InlineKeyboardButton(f"⚙️ Auto Search: {auto_status}", callback_data="toggle_auto")],
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
        text = "🔍 **Search History:**\n\n"
        count = 0
        for uid, histories in db["search_history"].items():
            for h in histories[-5:]:
                text += f"`{uid}` → {h['query']} ({h['time']})\n"
                count += 1
                if count >= 40: break
        if count == 0:
            text += "কোনো হিস্টোরি নেই"
        await query.edit_message_text(text[:4000], parse_mode="Markdown")

    elif data == "dash_videos" and user_id == ADMIN_ID:
        db = load_data()
        text = "🎬 **Downloaded Videos:**\n\n"
        count = 0
        for uid, videos in db["video_history"].items():
            for v in videos[-4:]:
                text += f"`{uid}` → {v['title'][:45]}...\n"
                count += 1
                if count >= 30: break
        if count == 0:
            text += "কোনো ভিডিও নেই"
        await query.edit_message_text(text[:4000], parse_mode="Markdown")

    # ---------- DATABASE PAGINATION ----------
    elif data.startswith("dash_database_") and user_id == ADMIN_ID:
        page = int(data.split("_")[-1])
        db = load_data()
        videos = db.get("database", [])
        total = len(videos)
        per_page = 20
        start = page * per_page
        end = start + per_page
        page_videos = videos[start:end]

        if not page_videos:
            await query.edit_message_text("Database খালি।")
            return

        text = f"🗄️ **Database** (Page {page+1})\nমোট: {total}টা\n\n"
        for i, v in enumerate(page_videos, start + 1):
            text += f"{i}. {v['title'][:50]}\n"

        buttons = []
        # নাম্বার বাটন (বর্তমান পেজের)
        row = []
        for i in range(start + 1, end + 1):
            if i > total: break
            row.append(InlineKeyboardButton(str(i), callback_data=f"dbdl_{i-1}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        # Pagination
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"dash_database_{page-1}"))
        if end < total:
            nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"dash_database_{page+1}"))
        if nav:
            buttons.append(nav)

        buttons.append([InlineKeyboardButton("🔙 Dashboard", callback_data="menu_dashboard")])

        await query.edit_message_text(text[:4000], parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))

    # Database থেকে ডাউনলোড
    elif data.startswith("dbdl_") and user_id == ADMIN_ID:
        idx = int(data.split("_")[1])
        db = load_data()
        videos = db.get("database", [])
        if 0 <= idx < len(videos):
            video = videos[idx]
            await query.edit_message_text(f"⬇️ ডাউনলোড হচ্ছে:\n{video['title'][:60]}...")
            await download_and_send(context, video, user_id)
        else:
            await query.edit_message_text("ভিডিও পাওয়া যায়নি।")

    # Manual download from search
    elif data.startswith("dl_"):
        if not is_approved(user_id) and user_id != ADMIN_ID:
            await query.edit_message_text("তুমি অনুমোদিত নও।")
            return

        action = data.split("_")[1]
        results = context.user_data.get("last_results", [])

        if not results:
            await query.edit_message_text("সার্চ রেজাল্ট মেয়াদোত্তীর্ণ। আবার সার্চ করো।")
            return

        if action == "all":
            await query.edit_message_text("⬇️ All ডাউনলোড শুরু (প্রথম ৫টা)...")
            for video in results[:5]:
                await download_and_send(context, video, user_id)
            await context.bot.send_message(chat_id=user_id, text="✅ All শেষ।")
        else:
            try:
                num = int(action)
                if 1 <= num <= len(results):
                    video = results[num-1]
                    await query.edit_message_text(f"⬇️ ডাউনলোড হচ্ছে:\n{video['title'][:60]}...")
                    await download_and_send(context, video, user_id)
            except:
                await query.edit_message_text("সমস্যা হয়েছে")

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

    keyboard = [[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
        InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")
    ]]
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"🔔 Custom Request!\n\nName: {user.full_name}\nUsername: @{user.username or 'None'}\nChat ID: `{user.id}`\n\nReason: {reason}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    await update.message.reply_text("✅ Custom Request পাঠানো হয়েছে।")
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল করা হয়েছে।")
    return ConversationHandler.END

# ==================== MANUAL SEARCH ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if not is_approved(user_id) and user_id != ADMIN_ID:
        await update.message.reply_text("তুমি অনুমোদিত নও। `/start` দিয়ে Request পাঠাও।")
        return

    if text.startswith("/"):
        return

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
                results.append({"title": title, "url": link, "thumb": thumb})

        if not results:
            await update.message.reply_text("কিছু পাওয়া যায়নি 😔")
            return

        context.user_data["last_results"] = results

        media_group = []
        for i, v in enumerate(results[:8], 1):
            if v.get("thumb"):
                media_group.append(InputMediaPhoto(media=v["thumb"], caption=f"{i}. {v['title'][:55]}"))
        if media_group:
            try:
                await update.message.reply_media_group(media=media_group)
            except: pass

        buttons = []
        row = []
        for i in range(1, len(results)+1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"dl_{i}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("📥 All (প্রথম ৫টা)", callback_data="dl_all")])

        await update.message.reply_text(
            f"✅ {len(results)}টা ভিডিও পাওয়া গেছে।\nনাম্বার সিলেক্ট করো:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
    except Exception as e:
        await update.message.reply_text(f"সার্চ ফেইল: {str(e)}")

async def download_and_send(context: ContextTypes.DEFAULT_TYPE, video, user_id):
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
                await context.bot.send_message(chat_id=user_id, text=f"❌ ভিডিও খুব বড়:\n{video['title'][:50]}")
                return

            with open(filename, "rb") as f:
                await context.bot.send_video(chat_id=user_id, video=f, caption=video["title"][:200], supports_streaming=True)

            add_video_history(user_id, video["title"], video["url"])
            await context.bot.send_message(chat_id=user_id, text="✅ পাঠানো হয়েছে!")
    except Exception as e:
        await context.bot.send_message(chat_id=user_id, text=f"❌ ডাউনলোড ফেইল:\n{str(e)[:180]}")

# ==================== MAIN ====================
def main():
    if not TOKEN:
        print("❌ BOT_TOKEN সেট করা হয়নি!")
        return

    if ADMIN_ID == 0:
        print("❌ ADMIN_ID সেট করা হয়নি!")
        return

    app = Application.builder().token(TOKEN).build()

    # JobQueue দিয়ে ১ মিনিট পরপর অটো সার্চ
    job_queue = app.job_queue
    job_queue.run_repeating(
        auto_search_job,
        interval=60,
        first=10
    )

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                button_handler,
                pattern="^custom_request$"
            )
        ],
        states={
            WAITING_CUSTOM_REASON: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    custom_reason
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conv)
        ],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("✅ Bot চালু হয়েছে + Auto Search Job Ready...")
    app.run_polling()


if __name__ == "__main__":
    main()
