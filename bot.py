import os
import logging
import tempfile
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import yt_dlp

TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)

SEARCH_RESULTS = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "হ্যালো! xHamster Demo Bot 🔥\n\n"
        "কমান্ড:\n"
        "/search <কিওয়ার্ড> - সার্চ করো\n"
        "তারপর নাম্বার দিয়ে ভিডিও সিলেক্ট করো"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ কিওয়ার্ড দাও।\nউদাহরণ: /search blonde")
        return

    query = " ".join(context.args)
    msg = await update.message.reply_text(f"🔍 সার্চ করছি: {query} ...")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "default_search": "ytsearch5",  # fallback
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # xHamster সার্চ
            info = ydl.extract_info(f"https://xhamster.com/search/{query}", download=False)

        results = []
        if "entries" in info:
            for i, entry in enumerate(info["entries"][:5], 1):
                title = entry.get("title", "No title")
                url = entry.get("url") or entry.get("webpage_url")
                results.append({"title": title, "url": url})
                await update.message.reply_text(f"{i}. {title}")

        if not results:
            await msg.edit_text("কিছু পাওয়া যায়নি 😔")
            return

        SEARCH_RESULTS[update.effective_user.id] = results
        await update.message.reply_text("ভিডিও সিলেক্ট করতে নাম্বার লিখো (1-5)")

    except Exception as e:
        await msg.edit_text(f"সার্চ ফেইল: {str(e)}")

async def select_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in SEARCH_RESULTS:
        return

    if not text.isdigit():
        await update.message.reply_text("শুধু নাম্বার লিখো (1-5)")
        return

    num = int(text)
    results = SEARCH_RESULTS[user_id]

    if num < 1 or num > len(results):
        await update.message.reply_text("সঠিক নাম্বার দাও")
        return

    video = results[num - 1]
    await update.message.reply_text(f"⬇️ ডাউনলোড শুরু করছি...\n{video['title']}\n\nঅপেক্ষা করো (সময় লাগতে পারে)")

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts = {
                "format": "worst[ext=mp4]/worst",  # সবচেয়ে ছোট কোয়ালিটি
                "outtmpl": f"{tmpdir}/%(title)s.%(ext)s",
                "quiet": True,
                "no_warnings": True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video["url"], download=True)
                filename = ydl.prepare_filename(info)

            # ফাইল সাইজ চেক
            size = os.path.getsize(filename)
            if size > 49 * 1024 * 1024:  # 49MB
                await update.message.reply_text("❌ ভিডিও খুব বড় (৫০MB এর বেশি)। পাঠানো যাচ্ছে না।")
                return

            with open(filename, "rb") as f:
                await update.message.reply_video(video=f, caption=video["title"][:200])

            await update.message.reply_text("✅ পাঠানো হয়েছে!")

    except Exception as e:
        await update.message.reply_text(f"❌ ডাউনলোড ফেইল হয়েছে:\n{str(e)}")

    finally:
        if user_id in SEARCH_RESULTS:
            del SEARCH_RESULTS[user_id]

def main():
    if not TOKEN:
        print("BOT_TOKEN সেট করা হয়নি!")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("search", search))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, select_video))

print("Bot চালু...")
app.run_polling()

if __name__ == "__main__":
    main()
