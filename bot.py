import os
import logging
import tempfile
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup
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

    try:
        url = f"https://xhamster.com/search/{query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=20)
        soup = BeautifulSoup(r.text, "html.parser")

        results = []
        items = soup.select(".thumb-list__item")[:5]

        for i, item in enumerate(items, 1):
            title_tag = item.select_one(".video-thumb-info__name") or item.select_one("a")
            link_tag = item.select_one("a")
            
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                href = link_tag.get("href", "")
                if href.startswith("/"):
                    link = "https://xhamster.com" + href
                else:
                    link = href
                
                results.append({"title": title, "url": link})
                await update.message.reply_text(f"{i}. {title}")

        if not results:
            await msg.edit_text("কিছু পাওয়া যায়নি 😔")
            return

        SEARCH_RESULTS[update.effective_user.id] = results
        await update.message.reply_text("✅ ভিডিও সিলেক্ট করতে নাম্বার লিখো (1-5)")

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
    await update.message.reply_text(f"⬇️ ডাউনলোড শুরু...\n{video['title']}\n\nঅপেক্ষা করো...")

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
                await update.message.reply_text("❌ ভিডিও ৫০MB এর বেশি। পাঠানো যাচ্ছে না।")
                return

            with open(filename, "rb") as f:
                await update.message.reply_video(video=f, caption=video["title"][:200])

            await update.message.reply_text("✅ পাঠানো হয়েছে!")

    except Exception as e:
        await update.message.reply_text(f"❌ ডাউনলোড ফেইল:\n{str(e)}")

    finally:
        if user_id in SEARCH_RESULTS:
            del SEARCH_RESULTS[user_id]

def main():
    if not TOKEN:
        print("BOT_TOKEN সেট করা হয়নি!")
        return

    def main():
    if not TOKEN:
        print("BOT_TOKEN সেট করা হয়নি!")
        return

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
