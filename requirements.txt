import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from bs4 import BeautifulSoup

# Railway Environment Variable থেকে Token নিবে
TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "হ্যালো! আমি xHamster Demo Bot 🔥\n\n"
        "কমান্ড:\n"
        "/search <কিওয়ার্ড> - সার্চ করো\n"
        "অথবা সরাসরি কোনো xHamster ভিডিও লিংক পাঠাও"
    )

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("উদাহরণ: /search blonde")
        return

    query = " ".join(context.args)
    await update.message.reply_text(f"🔍 সার্চ করছি: {query} ...")

    try:
        url = f"https://xhamster.com/search/{query}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        videos = []
        for item in soup.select(".thumb-list__item")[:5]:
            title_tag = item.select_one(".video-thumb-info__name")
            link_tag = item.select_one("a")
            if title_tag and link_tag:
                title = title_tag.get_text(strip=True)
                link = "https://xhamster.com" + link_tag.get("href", "")
                videos.append(f"• {title}\n{link}")

        if videos:
            await update.message.reply_text("\n\n".join(videos))
        else:
            await update.message.reply_text("কিছু পাওয়া যায়নি 😔")
    except Exception as e:
        await update.message.reply_text(f"সমস্যা হয়েছে: {str(e)}")

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if "xhamster.com" not in text:
        return

    await update.message.reply_text("ভিডিও ইনফো নিচ্ছি...")

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        r = requests.get(text, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")

        title = soup.select_one("h1")
        title = title.get_text(strip=True) if title else "N/A"

        await update.message.reply_text(f"📌 Title: {title}\n🔗 Link: {text}")
    except Exception as e:
        await update.message.reply_text(f"পারিনি: {str(e)}")

def main():
    if not TOKEN:
        print("Error: BOT_TOKEN environment variable set করা হয়নি!")
        return

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search))
    app.add_handler(MessageHandler(filters.TEXT & \~filters.COMMAND, handle_link))

    print("Bot চালু হয়েছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
