import os
import json
import re
import asyncio
from datetime import datetime, timezone, timedelta
from telethon import TelegramClient, events
from telethon.tl.custom import Button
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

API_ID = 30298905
API_HASH = 'f84ab00ad475e2a293c2135f90801c85'
BOT_TOKEN = '8880691679:AAGsbWlKrI5yn3sxOcL44WW9rOCWFu2ylck'

DATA_FILE = 'saved_accounts.json'

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

temp_storage = {}

bot = TelegramClient('bot_session', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

def get_country_name(phone):
    phone = phone.replace("+", "").strip()
    
    country_codes = [
        ("93", "Afghanistan 🇦🇫"), ("355", "Albania 🇦🇱"), ("213", "Algeria 🇩🇿"), ("376", "Andorra 🇦🇩"),
        ("244", "Angola 🇦🇴"), ("54", "Argentina 🇦🇷"), ("374", "Armenia 🇦🇲"), ("61", "Australia 🇦🇺"),
        ("43", "Austria 🇦🇹"), ("994", "Azerbaijan 🇦🇿"), ("973", "Bahrain 🇧🇭"), ("880", "Bangladesh 🇧🇩"),
        ("375", "Belarus 🇧🇾"), ("32", "Belgium 🇧🇪"), ("501", "Belize 🇧🇿"), ("229", "Benin 🇧🇯"),
        ("975", "Bhutan 🇧🇹"), ("591", "Bolivia 🇧🇴"), ("387", "Bosnia and Herzegovina 🇧🇦"), ("267", "Botswana 🇧🇼"),
        ("55", "Brazil 🇧🇷"), ("673", "Brunei 🇧🇳"), ("359", "Bulgaria 🇧🇬"), ("226", "Burkina Faso 🇧🇫"),
        ("257", "Burundi 🇧🇮"), ("855", "Cambodia 🇰🇭"), ("237", "Cameroon 🇨🇲"), ("1", "USA/Canada 🇺🇸/🇨🇦"),
        ("238", "Cape Verde 🇨🇻"), ("236", "Central African Republic 🇨🇫"), ("235", "Chad 🇹🇩"), ("56", "Chile 🇨🇱"),
        ("86", "China 🇨🇳"), ("57", "Colombia 🇨🇴"), ("269", "Comoros 🇰🇲"), ("242", "Congo 🇨🇬"),
        ("506", "Costa Rica 🇨🇷"), ("385", "Croatia 🇭🇷"), ("53", "Cuba 🇨🇺"), ("357", "Cyprus 🇨🇾"),
        ("420", "Czech Republic 🇨🇿"), ("45", "Denmark 🇩🇰"), ("253", "Djibouti 🇩🇯"), ("593", "Ecuador 🇪🇨"),
        ("20", "Egypt 🇪🇬"), ("503", "El Salvador 🇸🇻"), ("240", "Equatorial Guinea 🇬🇶"), ("291", "Eritrea 🇪🇷"),
        ("372", "Estonia 🇪🇪"), ("251", "Ethiopia 🇪🇹"), ("679", "Fiji 🇫🇯"), ("358", "Finland 🇫🇮"),
        ("33", "France 🇫🇷"), ("241", "Gabon 🇬🇦"), ("220", "Gambia 🇬🇲"), ("995", "Georgia 🇬🇪"),
        ("49", "Germany 🇩🇪"), ("233", "Ghana 🇬🇭"), ("30", "Greece 🇬🇷"), ("502", "Guatemala 🇬🇹"),
        ("224", "Guinea 🇬🇳"), ("245", "Guinea-Bissau 🇬🇼"), ("509", "Haiti 🇭🇹"), ("504", "Honduras 🇭🇳"),
        ("852", "Hong Kong 🇭🇰"), ("36", "Hungary 🇭🇺"), ("354", "Iceland 🇮🇸"), ("91", "India 🇮🇳"),
        ("62", "Indonesia 🇮🇳"), ("98", "Iran 🇮🇷"), ("964", "Iraq 🇮🇶"), ("353", "Ireland 🇮🇪"),
        ("972", "Israel 🇮🇱"), ("39", "Italy 🇮🇹"), ("225", "Ivory Coast 🇨🇮"), ("81", "Japan 🇯🇵"),
        ("962", "Jordan 🇯🇴"), ("7", "Russia/Kazakhstan 🇷🇺/🇰🇿"), ("254", "Kenya 🇰🇪"), ("965", "Kuwait 🇰🇼"),
        ("996", "Kyrgyzstan 🇰🇬"), ("856", "Laos 🇱🇦"), ("371", "Latvia 🇱🇻"), ("961", "Lebanon 🇱🇧"),
        ("266", "Lesotho 🇱🇸"), ("231", "Liberia 🇱🇷"), ("218", "Libya 🇱🇾"), ("423", "Liechtenstein 🇱🇮"),
        ("370", "Lithuania 🇱🇹"), ("352", "Luxembourg 🇱🇺"), ("853", "Macau 🇲🇴"), ("389", "North Macedonia 🇲🇰"),
        ("261", "Madagascar 🇲🇬"), ("265", "Malawi 🇲🇼"), ("60", "Malaysia 🇲🇾"), ("960", "Maldives 🇲🇻"),
        ("223", "Mali 🇲🇱"), ("356", "Malta 🇲🇹"), ("222", "Mauritania 🇲🇷"), ("230", "Mauritius 🇲🇺"),
        ("52", "Mexico 🇲🇽"), ("373", "Moldova 🇲🇩"), ("377", "Monaco 🇲🇨"), ("976", "Mongolia 🇲🇳"),
        ("382", "Montenegro 🇲🇪"), ("212", "Morocco 🇲🇦"), ("258", "Mozambique 🇲🇿"), ("95", "Myanmar 🇲🇲"),
        ("264", "Namibia 🇳🇦"), ("977", "Nepal 🇳🇵"), ("31", "Netherlands 🇳🇱"), ("64", "New Zealand 🇳🇿"),
        ("505", "Nicaragua 🇳🇮"), ("227", "Niger 🇳🇪"), ("234", "Nigeria 🇳🇬"), ("47", "Norway 🇳🇴"),
        ("968", "Oman 🇴🇲"), ("92", "Pakistan 🇵🇰"), ("970", "Palestine 🇵🇸"), ("507", "Panama 🇵🇦"),
        ("675", "Papua New Guinea 🇵🇬"), ("595", "Paraguay 🇵🇾"), ("51", "Peru 🇵🇪"), ("63", "Philippines 🇵🇭"),
        ("48", "Poland 🇵🇱"), ("351", "Portugal 🇵🇹"), ("974", "Qatar 🇶🇦"), ("40", "Romania 🇷🇴"),
        ("250", "Rwanda 🇷🇼"), ("966", "Saudi Arabia 🇸🇦"), ("221", "Senegal 🇸🇳"), ("381", "Serbia 🇷🇸"),
        ("248", "Seychelles 🇸🇨"), ("232", "Sierra Leone 🇸🇱"), ("65", "Singapore 🇸🇬"), ("421", "Slovakia 🇸🇰"),
        ("386", "Slovenia 🇸🇮"), ("252", "Somalia 🇸🇴"), ("27", "South Africa 🇿🇦"), ("82", "South Korea 🇰🇷"),
        ("211", "South Sudan 🇸🇸"), ("34", "Spain 🇪🇸"), ("94", "Sri Lanka 🇱🇰"), ("249", "Sudan 🇸🇩"),
        ("597", "Suriname 🇸🇷"), ("46", "Sweden 🇸🇪"), ("41", "Switzerland 🇨🇭"), ("963", "Syria 🇸🇾"),
        ("886", "Taiwan 🇹🇼"), ("992", "Tajikistan 🇹🇯"), ("255", "Tanzania 🇹🇿"), ("66", "Thailand 🇹🇭"),
        ("228", "Togo 🇹🇬"), ("676", "Tonga 🇹🇴"), ("216", "Tunisia 🇹🇳"), ("90", "Turkey 🇹🇷"),
        ("993", "Turkmenistan 🇹🇲"), ("256", "Uganda 🇺🇬"), ("380", "Ukraine 🇺🇦"), ("971", "UAE 🇦🇪"),
        ("44", "UK 🇬🇧"), ("598", "Uruguay 🇺🇾"), ("998", "Uzbekistan 🇺🇿"), ("58", "Venezuela 🇻🇪"),
        ("84", "Vietnam 🇻🇳"), ("967", "Yemen 🇾🇪"), ("260", "Zambia 🇿🇲"), ("263", "Zimbabwe 🇿🇼")
    ]
    
    for code, name in country_codes:
        if phone.startswith(code):
            return name
            
    return "International 🌍"

def main_menu_keyboard():
    return [
        [Button.text("➕ New Number Add", resize=True)],
        [Button.text("📂 Your Numbers", resize=True)]
    ]

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    await event.respond(
        "স্বাগতম! আপনার অ্যাকাউন্ট ম্যানেজার বোটে। নিচের মেনু থেকে অপশন বেছে নিন:",
        buttons=main_menu_keyboard()
    )

@bot.on(events.NewMessage(pattern='➕ New Number Add'))
async def ask_number(event):
    sender_id = event.sender_id
    temp_storage[sender_id] = {
        'step': 'waiting_phone',
        'msg_ids': [event.message.id]
    }
    msg = await event.respond("দয়া করে আপনার ফোন নম্বরটি কান্ট্রি কোড সহ পাঠান (যেমন: `+88017xxxxxxxx`):")
    temp_storage[sender_id]['msg_ids'].append(msg.id)

@bot.on(events.NewMessage(pattern='📂 Your Numbers'))
async def list_countries(event):
    sender_id = str(event.sender_id)
    data = load_data()
    
    if sender_id not in data or not data[sender_id]:
        await event.respond("আপনার কোনো অ্যাকাউন্ট সেভ করা নেই।", buttons=main_menu_keyboard())
        return
    
    user_accounts = data[sender_id]
    valid_accounts = {}
    
    for phone, info in user_accounts.items():
        session_str = info.get('session')
        try:
            temp_client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await temp_client.connect()
            if await temp_client.is_user_authorized():
                valid_accounts[phone] = info
            await temp_client.disconnect()
        except:
            pass
            
    if len(valid_accounts) != len(user_accounts):
        data[sender_id] = valid_accounts
        save_data(data)
        
    if not valid_accounts:
        await event.respond("আপনার সেভ করা সব অ্যাকাউন্ট লগআউট হয়ে গেছে, তাই লিস্ট খালি।", buttons=main_menu_keyboard())
        return

    countries = {}
    for phone, info in valid_accounts.items():
        country = info.get('country', 'International 🌍')
        if country not in countries:
            countries[country] = []
        countries[country].append(phone)
    
    buttons = []
    for country in countries.keys():
        count = len(countries[country])
        buttons.append([Button.inline(f"{country} ({count} Numbers)", data=f"country_{country}")])
    
    await event.respond("আপনার সেভ করা দেশগুলোর লিস্ট নিচে দেওয়া হলো:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'country_'))
async def list_numbers_by_country(event):
    sender_id = str(event.sender_id)
    selected_country = event.data.decode().replace('country_', '')
    data = load_data()
    
    if sender_id in data:
        buttons = []
        for phone, info in data[sender_id].items():
            if info.get('country') == selected_country:
                buttons.append([Button.inline(f"📱 {phone}", data=f"getnum_{phone}")])
        
        buttons.append([Button.inline("🔙 Back to Countries", data="back_countries")])
        await event.edit(f"📂 **{selected_country}** এর আন্ডারে থাকা নম্বরগুলো:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'back_countries'))
async def back_to_countries(event):
    sender_id = str(event.sender_id)
    data = load_data()
    if sender_id not in data:
        return
    
    countries = {}
    for phone, info in data[sender_id].items():
        country = info.get('country', 'International 🌍')
        if country not in countries:
            countries[country] = []
        countries[country].append(phone)
    
    buttons = []
    for country in countries.keys():
        count = len(countries[country])
        buttons.append([Button.inline(f"{country} ({count} Numbers)", data=f"country_{country}")])
    
    await event.edit("আপনার সেভ করা দেশগুলোর লিস্ট নিচে দেওয়া হলো:", buttons=buttons)

@bot.on(events.CallbackQuery(pattern=b'getnum_'))
async def send_phone_number(event):
    sender_id = str(event.sender_id)
    phone = event.data.decode().replace('getnum_', '')
    data = load_data()
    
    if sender_id in data and phone in data[sender_id]:
        session_str = data[sender_id][phone]['session']
        two_fa_password = data[sender_id][phone].get('password', 'N/A')
        
        # নম্বরটি নরমাল টেক্সট আকারে পাঠানো হলো যাতে সহজে কপি করা যায়
        num_msg = await event.respond(f"📱 নম্বর: `{phone}`\n⏳ *১০ সেকেন্ড পর অটো ডিলিট হবে...*")
        
        msg = await event.respond(f"⏳ **Waiting for login code...**")
        
        otp_code = None
        try:
            client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await client.connect()
            
            start_time = datetime.now(timezone.utc)
            
            for _ in range(25):
                async for message in client.iter_messages(777000, limit=10):
                    if message.date and message.date >= (start_time - timedelta(seconds=15)):
                        text = message.text
                        match = re.search(r'\b(\d{5,6})\b', text)
                        if match and any(kw in text.lower() for kw in ["login", "code", "telegram", "signin"]):
                            otp_code = match.group(1)
                            break
                if otp_code:
                    break
                await asyncio.sleep(2)
            
            await client.disconnect()
        except Exception as e:
            pass

        if otp_code:
            final_text = f"🔑 **Code:** `{otp_code}`\n"
            if two_fa_password != 'N/A':
                final_text += f"🔐 **2FA:** `{two_fa_password}`\n"
            final_text += f"\n⏳ *১০ সেকেন্ড পর ডিলিট হবে...*"

            final_msg = await msg.edit(final_text)
            
            # ১০ সেকেন্ড পর কোড ও নম্বর উভয় মেসেজ ডিলিট হয়ে যাবে
            await asyncio.sleep(10)
            try:
                await final_msg.delete()
                await num_msg.delete()
            except:
                pass
        else:
            await msg.edit(f"❌ কোড পাওয়া যায়নি। আবার চেষ্টা করুন।")
            await asyncio.sleep(10)
            try:
                await num_msg.delete()
            except:
                pass
    else:
        await event.answer("নম্বর পাওয়া যায়নি বা লগআউট হয়ে গেছে!", alert=True)

@bot.on(events.NewMessage())
async def handle_user_input(event):
    text = event.raw_text.strip()
    if text in ['➕ New Number Add', '📂 Your Numbers', '/start']:
        return

    sender_id = event.sender_id
    if sender_id not in temp_storage:
        return
    
    if 'msg_ids' not in temp_storage[sender_id]:
        temp_storage[sender_id]['msg_ids'] = []
    temp_storage[sender_id]['msg_ids'].append(event.message.id)
    
    state = temp_storage[sender_id].get('step')
    
    if state == 'waiting_phone':
        phone = text if text.startswith("+") else "+" + text
        temp_storage[sender_id]['phone'] = phone
        
        waiting_msg = await event.respond("⏳ **Waiting for otp...**")
        temp_storage[sender_id]['msg_ids'].append(waiting_msg.id)
        
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        
        try:
            await client.connect()
            sent = await client.send_code_request(phone)
            temp_storage[sender_id]['client'] = client
            temp_storage[sender_id]['phone_code_hash'] = sent.phone_code_hash
            temp_storage[sender_id]['step'] = 'waiting_otp'
            
            msg = await waiting_msg.edit("✅ ওটিপি পাঠানো হয়েছে। অ্যাপে কোডটি আসলে সেটি এখানে দিন:")
            temp_storage[sender_id]['msg_ids'].append(msg.id)
        except Exception as e:
            try:
                await client.disconnect()
            except:
                pass
            if sender_id in temp_storage:
                del temp_storage[sender_id]
            await waiting_msg.edit(f"❌ সমস্যা হয়েছে: {str(e)}")
            
    elif state == 'waiting_otp':
        client = temp_storage[sender_id]['client']
        phone = temp_storage[sender_id]['phone']
        phone_code_hash = temp_storage[sender_id]['phone_code_hash']
        
        try:
            await client.sign_in(phone, text, phone_code_hash=phone_code_hash)
            await finalize_login(event, sender_id, client, phone, password=None)
        except SessionPasswordNeededError:
            temp_storage[sender_id]['step'] = 'waiting_password'
            msg = await event.respond("🔒 টু-স্টেপ ভেরিফিকেশন পাসওয়ার্ড দিন:")
            temp_storage[sender_id]['msg_ids'].append(msg.id)
        except Exception as e:
            msg = await event.respond(f"❌ ওটিপি ভুল হয়েছে। আবার সঠিক কোড দিন:")
            temp_storage[sender_id]['msg_ids'].append(msg.id)

    elif state == 'waiting_password':
        client = temp_storage[sender_id]['client']
        phone = temp_storage[sender_id]['phone']
        
        try:
            await client.sign_in(password=text)
            await finalize_login(event, sender_id, client, phone, password=text)
        except Exception as e:
            msg = await event.respond(f"❌ পাসওয়ার্ড ভুল: আবার সঠিক পাসওয়ার্ড দিন:")
            temp_storage[sender_id]['msg_ids'].append(msg.id)

async def finalize_login(event, sender_id, client, phone, password=None):
    session_string = client.session.save()
    country = get_country_name(phone)
    
    data = load_data()
    str_sender_id = str(sender_id)
    if str_sender_id not in data:
        data[str_sender_id] = {}
        
    data[str_sender_id][phone] = {
        'session': session_string,
        'country': country,
        'password': password if password else 'N/A'
    }
    save_data(data)
    
    await client.disconnect()
    
    if sender_id in temp_storage:
        msg_ids = temp_storage[sender_id].get('msg_ids', [])
        for m_id in msg_ids:
            try:
                await bot.delete_messages(sender_id, m_id)
            except:
                pass
        del temp_storage[sender_id]
    
    await event.respond(
        "Login Success ✅",
        buttons=main_menu_keyboard()
    )

print("Bot is running...")
bot.run_until_disconnected()
