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

AUTO_KEYWORDS = [
    "bangla", "bengali", "desi", "kolkata", "dhaka",
    "bangla sex", "bengali sex", "desi sex", "bangla hot"
]

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

WAITING_CUSTOM_REASON = 1

# ==================== DATA ====================
def load_data():
    default = {
        "approved": [],
        "pending": {},
        "search_history": {},
        "video_history": {},
        "database": [],
        "auto_search": False
    }
    if not os.path.exists(DATA_FILE):
        return default
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for k, v in default.items():
            if k not in data:
                data[k] = v
        return data
    except:
        return default

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_approved(user_id):
    data = load_data()
    return str(user_id) in data.get("approved", []) or user_id == ADMIN_ID

def add_to_database(videos):
    data = load_data()
    existing = {v["url"] for v in data.get("database", [])}
    added = 0
    for v in videos:
        if v["url"] not in existing:
            data["database"].append(v)
            added += 1
    data["database"] = data["database"][-800:]
    save_data(data)
    return added

# ==================== AUTO SEARCH ====================
async def auto_search_job(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if not data.get("auto_search"):
        return
    keyword = random.choice(AUTO_KEYWORDS)
    logger.info(f"[AUTO] Searching: {keyword}")
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(f"https://xhamster.com/search/{keyword}", headers=headers, timeout=12)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for item in soup.select(".thumb-list__item")[:6]:
            title_tag = item.select_one(".video-thumb-info__name") or item.select_one("a")
            link_tag = item.select_one("a")
            if title_tag and link_tag:
                href = link_tag.get("href", "")
                link = "https://xhamster.com" + href if href.startswith("/") else href
                results.append({
                    "title": title_tag.get_text(strip=True),
                    "url": link,
                    "thumb": None,
                    "keyword": keyword,
                    "added": datetime.now().strftime("%Y-%m-%d %H:%M")
                })
        if results:
            added = add_to_database(results)
            logger.info(f"[AUTO] Added {added} new videos")
    except Exception as e:
        logger.error(f"[AUTO] Error: {e}")

# ==================== START ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    logger.info(f"Start from {user_id}")

    if user_id == ADMIN_ID or is_approved(user_id):
        keyboard = [[InlineKeyboardButton("🔍 Search", callback_data="menu_search")]]
        if user_id == ADMIN_ID:
            keyboard.append([InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard")])
        await update.message.reply_text(
            f"স্বাগতম {user.first_name}! 🔥\n\n"
            "নিচের বাটন ব্যবহার করো অথবা সরাসরি কিওয়ার্ড লিখে সার্চ করো।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        keyboard = [
            [InlineKeyboardButton("✅ Request", callback_data="request_access")],
            [InlineKeyboardButton("📝 Custom Request", callback_data="custom_request")],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel_request")]
        ]
        await update.message.reply_text(
            f"হ্যালো {user.first_name}!\n\nবট ব্যবহার করতে Request পাঠাও।",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

# ==================== BUTTONS ====================
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    logger.info(f"Button: {data} from {user_id}")

    try:
        if data == "request_access":
            db = load_data()
            db["pending"][str(user_id)] = {
                "name": query.from_user.full_name,
                "username": query.from_user.username or "None",
                "time": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            save_data(db)
            kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
                   InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")]]
            await context.bot.send_message(
                ADMIN_ID,
                f"🔔 নতুন Request\nName: {query.from_user.full_name}\nID: `{user_id}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            await query.edit_message_text("✅ Request পাঠানো হয়েছে।")

        elif data == "cancel_request":
            await query.edit_message_text("বাতিল করা হয়েছে।")

        elif data == "custom_request":
            await query.edit_message_text("কারণ লিখে পাঠাও:")
            return WAITING_CUSTOM_REASON

        elif data.startswith("approve_"):
            tid = data.split("_")[1]
            db = load_data()
            if tid not in db["approved"]:
                db["approved"].append(tid)
            db["pending"].pop(tid, None)
            save_data(db)
            await query.edit_message_text(f"✅ {tid} Approve হয়েছে")
            try:
                await context.bot.send_message(int(tid), "🎉 Approve হয়েছে! /start দাও")
            except: pass

        elif data.startswith("reject_"):
            tid = data.split("_")[1]
            db = load_data()
            db["pending"].pop(tid, None)
            save_data(db)
            await query.edit_message_text(f"❌ {tid} Reject হয়েছে")
            try:
                await context.bot.send_message(int(tid), "Request Reject করা হয়েছে।")
            except: pass

        elif data == "menu_search":
            await query.edit_message_text("🔍 কিওয়ার্ড লিখে পাঠাও:")

        elif data == "menu_dashboard" and user_id == ADMIN_ID:
            db = load_data()
            status = "🟢 ON" if db.get("auto_search") else "🔴 OFF"
            kb = [
                [InlineKeyboardButton("👥 Users", callback_data="dash_users")],
                [InlineKeyboardButton("🔍 History", callback_data="dash_search")],
                [InlineKeyboardButton(f"🗄️ Database ({len(db.get('database',[]))})", callback_data="dash_db_0")],
                [InlineKeyboardButton(f"⚙️ Auto: {status}", callback_data="toggle_auto")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
            ]
            await query.edit_message_text("📊 Admin Dashboard", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "back_main":
            kb = [[InlineKeyboardButton("🔍 Search", callback_data="menu_search")]]
            if user_id == ADMIN_ID:
                kb.append([InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard")])
            await query.edit_message_text("মেইন মেনু:", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "toggle_auto" and user_id == ADMIN_ID:
            db = load_data()
            db["auto_search"] = not db.get("auto_search", False)
            save_data(db)
            await query.answer(f"Auto Search {'ON' if db['auto_search'] else 'OFF'}")
            # refresh
            status = "🟢 ON" if db["auto_search"] else "🔴 OFF"
            kb = [
                [InlineKeyboardButton("👥 Users", callback_data="dash_users")],
                [InlineKeyboardButton("🔍 History", callback_data="dash_search")],
                [InlineKeyboardButton(f"🗄️ Database ({len(db.get('database',[]))})", callback_data="dash_db_0")],
                [InlineKeyboardButton(f"⚙️ Auto: {status}", callback_data="toggle_auto")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
            ]
            await query.edit_message_text("📊 Admin Dashboard", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "dash_users" and user_id == ADMIN_ID:
            db = load_data()
            text = "👥 Approved Users:\n\n" + "\n".join(f"`{u}`" for u in db.get("approved", [])) or "খালি"
            await query.edit_message_text(text, parse_mode="Markdown")

        elif data == "dash_search" and user_id == ADMIN_ID:
            db = load_data()
            text = "🔍 Recent Searches:\n\n"
            count = 0
            for uid, hist in db.get("search_history", {}).items():
                for h in hist[-3:]:
                    text += f"`{uid}` → {h['query']}\n"
                    count += 1
                    if count > 30: break
            await query.edit_message_text(text[:3500] or "খালি", parse_mode="Markdown")

        elif data.startswith("dash_db_") and user_id == ADMIN_ID:
            page = int(data.split("_")[-1])
            db = load_data()
            videos = db.get("database", [])
            total = len(videos)
            start = page * 20
            end = start + 20
            page_vids = videos[start:end]

            if not page_vids:
                await query.edit_message_text("Database খালি")
                return

            text = f"🗄️ Database (Page {page+1}) | Total: {total}\n\n"
            for i, v in enumerate(page_vids, start+1):
                text += f"{i}. {v['title'][:48]}\n"

            buttons = []
            row = []
            for i in range(start, min(end, total)):
                row.append(InlineKeyboardButton(str(i+1), callback_data=f"dbdl_{i}"))
                if len(row) == 5:
                    buttons.append(row)
                    row = []
            if row: buttons.append(row)

            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"dash_db_{page-1}"))
            if end < total:
                nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"dash_db_{page+1}"))
            if nav: buttons.append(nav)
            buttons.append([InlineKeyboardButton("🔙 Dashboard", callback_data="menu_dashboard")])

            await query.edit_message_text(text[:4000], reply_markup=InlineKeyboardMarkup(buttons))

        elif data.startswith("dbdl_") and user_id == ADMIN_ID:
            idx = int(data.split("_")[1])
            db = load_data()
            videos = db.get("database", [])
            if 0 <= idx < len(videos):
                await query.edit_message_text(f"⬇️ ডাউনলোড শুরু...\n{videos[idx]['title'][:50]}")
                await download_and_send(context, videos[idx], user_id)
            else:
                await query.edit_message_text("ভিডিও পাওয়া যায়নি")

        elif data.startswith("dl_"):
            results = context.user_data.get("last_results", [])
            if not results:
                await query.edit_message_text("রেজাল্ট মেয়াদোত্তীর্ণ। আবার সার্চ করো।")
                return
            action = data.split("_")[1]
            if action == "all":
                await query.edit_message_text("⬇️ All শুরু (প্রথম ৫টা)...")
                for v in results[:5]:
                    await download_and_send(context, v, user_id)
                await context.bot.send_message(user_id, "✅ All শেষ")
            else:
                num = int(action)
                if 1 <= num <= len(results):
                    await query.edit_message_text(f"⬇️ ডাউনলোড...\n{results[num-1]['title'][:50]}")
                    await download_and_send(context, results[num-1], user_id)

    except Exception as e:
        logger.error(f"Button error: {e}")
        await query.edit_message_text(f"এরর হয়েছে: {str(e)[:150]}")

# ==================== CUSTOM REASON ====================
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
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"),
           InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")]]
    await context.bot.send_message(
        ADMIN_ID,
        f"🔔 Custom Request\nName: {user.full_name}\nID: `{user.id}`\nReason: {reason}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    await update.message.reply_text("✅ পাঠানো হয়েছে।")
    return ConversationHandler.END

async def cancel_conv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বাতিল।")
    return ConversationHandler.END

# ==================== MESSAGE / SEARCH ====================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    logger.info(f"Message from {user_id}: {text}")

    if not is_approved(user_id) and user_id != ADMIN_ID:
        await update.message.reply_text("তুমি অনুমোদিত নও। /start দাও।")
        return

    if text.startswith("/"):
        return

    msg = await update.message.reply_text(f"🔍 সার্চ করছি: {text}")

    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        r = requests.get(f"https://xhamster.com/search/{text}", headers=headers, timeout=18)
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        for item in soup.select(".thumb-list__item")[:10]:
            title_tag = item.select_one(".video-thumb-info__name") or item.select_one("a")
            link_tag = item.select_one("a")
            if title_tag and link_tag:
                href = link_tag.get("href", "")
                link = "https://xhamster.com" + href if href.startswith("/") else href
                results.append({
                    "title": title_tag.get_text(strip=True),
                    "url": link,
                    "thumb": None
                })

        if not results:
            await msg.edit_text("কিছু পাওয়া যায়নি 😔")
            return

        context.user_data["last_results"] = results

        # History
        data = load_data()
        uid = str(user_id)
        if uid not in data["search_history"]:
            data["search_history"][uid] = []
        data["search_history"][uid].append({"query": text, "time": datetime.now().strftime("%Y-%m-%d %H:%M")})
        data["search_history"][uid] = data["search_history"][uid][-40:]
        save_data(data)

        buttons = []
        row = []
        for i in range(1, len(results)+1):
            row.append(InlineKeyboardButton(str(i), callback_data=f"dl_{i}"))
            if len(row) == 5:
                buttons.append(row)
                row = []
        if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("📥 All (৫টা)", callback_data="dl_all")])

        await msg.edit_text(
            f"✅ {len(results)}টা ভিডিও পাওয়া গেছে।\nনাম্বার চাপো:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    except Exception as e:
        logger.error(f"Search error: {e}")
        await msg.edit_text(f"❌ সার্চ ফেইল হয়েছে:\n{str(e)[:200]}")

# ==================== DOWNLOAD ====================
async def download_and_send(context, video, user_id):
    try:
        with tempfile.TemporaryDirectory() as tmp:
            ydl_opts = {
                "format": "worst[ext=mp4]/worst",
                "outtmpl": f"{tmp}/%(id)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video["url"], download=True)
                filename = ydl.prepare_filename(info)

            if os.path.getsize(filename) > 49 * 1024 * 1024:
                await context.bot.send_message(user_id, "❌ ভিডিও ৫০MB এর বেশি")
                return

            with open(filename, "rb") as f:
                await context.bot.send_video(user_id, video=f, caption=video["title"][:180], supports_streaming=True)
            await context.bot.send_message(user_id, "✅ পাঠানো হয়েছে!")
    except Exception as e:
        await context.bot.send_message(user_id, f"❌ ডাউনলোড এরর:\n{str(e)[:180]}")

# ==================== MAIN ====================
def main():
    if not TOKEN or ADMIN_ID == 0:
        print("❌ BOT_TOKEN বা ADMIN_ID সেট করা হয়নি!")
        return

    app = Application.builder().token(TOKEN).build()

    if app.job_queue:
        app.job_queue.run_repeating(
            auto_search_job,
            interval=60,
            first=15
        )

    conv = ConversationHandler(
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
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    print("✅ Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
