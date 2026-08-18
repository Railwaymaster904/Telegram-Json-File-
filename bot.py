import os
import logging
import requests
from bs4 import BeautifulSoup

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)


# ============================================================
# CONFIG
# ============================================================

# Railway Environment Variable থেকে Bot Token নেওয়া হবে
TOKEN = os.getenv("BOT_TOKEN")


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ============================================================
# START COMMAND
# ============================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "হ্যালো! আমি xHamster Demo Bot 🔥\n\n"
        "কমান্ড:\n"
        "/search <কিওয়ার্ড> - সার্চ করো\n\n"
        "অথবা সরাসরি কোনো xHamster ভিডিও লিংক পাঠাও।"
    )


# ============================================================
# SEARCH COMMAND
# ============================================================

async def search(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "❌ কিওয়ার্ড দাও।\n\n"
            "উদাহরণ:\n"
            "/search blonde"
        )
        return

    query = " ".join(context.args)

    await update.message.reply_text(
        f"🔍 সার্চ করছি: {query} ..."
    )

    try:
        url = f"https://xhamster.com/search/{query}"

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        videos = []

        for item in soup.select(".thumb-list__item")[:5]:

            title_tag = item.select_one(
                ".video-thumb-info__name"
            )

            link_tag = item.select_one("a")

            if title_tag and link_tag:

                title = title_tag.get_text(
                    strip=True
                )

                href = link_tag.get("href", "")

                if href.startswith("http"):
                    link = href
                else:
                    link = "https://xhamster.com" + href

                videos.append(
                    f"• {title}\n"
                    f"🔗 {link}"
                )

        if videos:

            message = (
                f"🔎 ফলাফল: {query}\n\n"
                + "\n\n".join(videos)
            )

            await update.message.reply_text(
                message
            )

        else:

            await update.message.reply_text(
                "😔 কোনো ফলাফল পাওয়া যায়নি।"
            )

    except requests.RequestException as e:

        logger.error(
            f"Search request error: {e}"
        )

        await update.message.reply_text(
            "❌ ওয়েবসাইটে কানেক্ট করতে সমস্যা হয়েছে।"
        )

    except Exception as e:

        logger.exception(
            f"Search error: {e}"
        )

        await update.message.reply_text(
            "❌ সার্চ করার সময় একটি সমস্যা হয়েছে।"
        )


# ============================================================
# HANDLE LINK
# ============================================================

async def handle_link(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not update.message:
        return

    text = update.message.text.strip()

    if "xhamster.com" not in text.lower():
        return

    await update.message.reply_text(
        "🔎 ভিডিও ইনফো নিচ্ছি..."
    )

    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(
            text,
            headers=headers,
            timeout=15
        )

        response.raise_for_status()

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        title_tag = soup.select_one("h1")

        if title_tag:
            title = title_tag.get_text(
                strip=True
            )
        else:
            title = "N/A"

        await update.message.reply_text(
            f"📌 Title: {title}\n\n"
            f"🔗 Link: {text}"
        )

    except requests.RequestException as e:

        logger.error(
            f"Link request error: {e}"
        )

        await update.message.reply_text(
            "❌ লিংকটি ওপেন করতে সমস্যা হয়েছে।"
        )

    except Exception as e:

        logger.exception(
            f"Link handling error: {e}"
        )

        await update.message.reply_text(
            "❌ ভিডিওর তথ্য নেওয়া যায়নি।"
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    logger.error(
        "Exception while handling update:",
        exc_info=context.error
    )


# ============================================================
# MAIN
# ============================================================

def main():

    if not TOKEN:

        print(
            "❌ Error: BOT_TOKEN environment variable "
            "set করা হয়নি!"
        )

        return

    app = (
        Application
        .builder()
        .token(TOKEN)
        .build()
    )

    # /start
    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    # /search
    app.add_handler(
        CommandHandler(
            "search",
            search
        )
    )

    # সাধারণ text message
    # এখানে ~filters.COMMAND ব্যবহার করতে হবে
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_link
        )
    )

    # Error Handler
    app.add_error_handler(
        error_handler
    )

    print("🚀 Bot চালু হয়েছে...")

    app.run_polling(
        drop_pending_updates=True
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
