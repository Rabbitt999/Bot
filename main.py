import telebot
import json
import os
import tempfile
import aiohttp
import asyncio
from datetime import datetime
import re
import shutil
from typing import Optional, Dict, Any

# ================== НАЛАШТУВАННЯ ==================
BOT_TOKEN = "8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g"
ADMIN_ID = 6974875043

# API alerts.in.ua
ALERTS_API_TOKEN = "f7f5a126f8865ad43bbd19d522d6c489b11486c9ab2203"
ALERTS_API_BASE_URL = "https://alerts.com.ua/api"
LVIV_REGION_ID = 25

TARGET_CHANNEL = "@Test_Chenal_0"
TARGET_CHANNEL_TITLE = "🧪 Test Channel"

# Файли для збереження даних
ALERT_STATE_FILE = "alert_state.json"
SCHEDULED_POSTS_FILE = "scheduled_posts.json"

# Максимальний розмір відео для завантаження (100 МБ)
MAX_VIDEO_SIZE = 100 * 1024 * 1024

# ================== ІНІЦІАЛІЗАЦІЯ БОТА ==================
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ================== СТАН ТРИВОГИ ==================
def load_alert_state():
    if not os.path.exists(ALERT_STATE_FILE):
        return {"active": False, "start_time": None}
    with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_alert_state(state: dict):
    with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)

def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    return f"{hours} год {minutes} хв" if hours else f"{minutes} хв"

# ================== ЗАПЛАНУВАНІ ПОСТИ ==================
def load_scheduled_posts():
    if not os.path.exists(SCHEDULED_POSTS_FILE):
        return {}
    try:
        with open(SCHEDULED_POSTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for post_id, post in data.items():
                if "scheduled_time" in post:
                    post["scheduled_time"] = datetime.fromisoformat(post["scheduled_time"])
            return data
    except Exception as e:
        print(f"Помилка при завантаженні запланованих постів: {e}")
        return {}

def save_scheduled_posts(posts: dict):
    serializable_posts = {}
    for post_id, post in posts.items():
        serializable_posts[post_id] = post.copy()
        if "scheduled_time" in serializable_posts[post_id]:
            serializable_posts[post_id]["scheduled_time"] = serializable_posts[post_id][
                "scheduled_time"].isoformat()
    
    with open(SCHEDULED_POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable_posts, f, ensure_ascii=False, indent=2)

# ================== API alerts.in.ua ==================
async def check_alerts_in_ua():
    headers = {
        "X-API-Key": ALERTS_API_TOKEN,
        "Accept": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ALERTS_API_BASE_URL}/states", headers=headers) as response:
                if response.status != 200:
                    print(f"Помилка API: {response.status}")
                    return None

                data = await response.json()
                lviv_region = None
                for region in data.get("states", []):
                    if region.get("id") == LVIV_REGION_ID:
                        lviv_region = region
                        break

                if not lviv_region:
                    print("Не знайдено Львівську область в даних API")
                    return None

                alert_active = lviv_region.get("alert", False)
                alert_state = load_alert_state()
                
                changed = False

                if alert_active != alert_state["active"]:
                    changed = True

                    if alert_active:
                        alert_state["active"] = True
                        alert_state["start_time"] = datetime.now().isoformat()
                        print(f"🚨 Тривога почалася у Львівській області")
                    else:
                        alert_state["active"] = False
                        alert_state["start_time"] = None
                        print(f"✅ Відбій тривоги у Львівській області")

                    save_alert_state(alert_state)

                return {
                    "active": alert_active,
                    "changed": changed,
                    "state": alert_state
                }

    except Exception as e:
        print(f"Помилка при перевірці API alerts.in.ua: {e}")
        return None

async def send_alert_to_channel(is_start: bool, duration_seconds: int = None):
    footer = f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

    if is_start:
        message_text = f"🚨УВАГА, повітряна тривога у Львівській області!{footer}"
        bot.send_message(TARGET_CHANNEL, message_text)
        print("📢 Надіслано повідомлення про початок тривоги")
    else:
        if duration_seconds:
            duration = format_duration(duration_seconds)
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!\n\n⏱ <b>Тривалість:</b> {duration}{footer}"
        else:
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!{footer}"

        bot.send_message(TARGET_CHANNEL, message_text)
        print("📢 Надіслано повідомлення про відбій тривоги")

# ================== ФОНОВА ЗАДАЧА ДЛЯ ПЕРЕВІРКИ ТРИВОГ ==================
async def alerts_monitoring_task():
    print("🔍 Запущено моніторинг тривог через API alerts.in.ua")

    while True:
        try:
            await asyncio.sleep(10)
            alert_status = await check_alerts_in_ua()

            if alert_status and alert_status["changed"]:
                if alert_status["active"]:
                    await send_alert_to_channel(is_start=True)
                else:
                    if alert_status["state"]["start_time"]:
                        start = datetime.fromisoformat(alert_status["state"]["start_time"])
                        seconds = int((datetime.now() - start).total_seconds())
                        await send_alert_to_channel(is_start=False, duration_seconds=seconds)
                    else:
                        await send_alert_to_channel(is_start=False)

        except Exception as e:
            print(f"Помилка в задачі моніторингу тривог: {e}")
            await asyncio.sleep(30)

# ================== ФОНОВА ЗАДАЧА ДЛЯ ПЕРЕВІРКИ ЗАПЛАНУВАНИХ ПОСТІВ ==================
async def scheduled_posts_monitoring_task():
    print("⏰ Запущено моніторинг запланованих постів")

    while True:
        try:
            await asyncio.sleep(60)
            scheduled_posts = load_scheduled_posts()
            now = datetime.now()
            
            posts_to_publish = []
            
            for post_id, post in list(scheduled_posts.items()):
                scheduled_time = post.get("scheduled_time")
                if scheduled_time and scheduled_time <= now:
                    posts_to_publish.append((post_id, post))
            
            for post_id, post in posts_to_publish:
                try:
                    scheduled_posts.pop(post_id, None)
                    
                    if post.get("media_path") and os.path.exists(post["media_path"]):
                        if post["media_type"] == "photo":
                            with open(post["media_path"], 'rb') as photo:
                                bot.send_photo(
                                    TARGET_CHANNEL,
                                    photo,
                                    caption=post["text"]
                                )
                        elif post["media_type"] == "video":
                            with open(post["media_path"], 'rb') as video:
                                bot.send_video(
                                    TARGET_CHANNEL,
                                    video,
                                    caption=post["text"]
                                )
                        os.remove(post["media_path"])
                    else:
                        bot.send_message(TARGET_CHANNEL, post["text"])
                    
                    scheduled_time_str = post.get("original_scheduled_time", "Невідомо")
                    bot.send_message(
                        ADMIN_ID,
                        f"✅ <b>Запланований пост опубліковано!</b>\n\n"
                        f"📅 Запланований час: {scheduled_time_str}\n"
                        f"🏷 ID: {post_id}",
                        parse_mode="HTML"
                    )
                    
                    print(f"⏰ Опубліковано запланований пост ID: {post_id}")
                    
                except Exception as e:
                    print(f"Помилка при публікації запланованого поста {post_id}: {e}")
                    bot.send_message(
                        ADMIN_ID,
                        f"❌ <b>Помилка при публікації запланованого поста!</b>\n\n"
                        f"🏷 ID: {post_id}\n"
                        f"📝 Помилка: {str(e)}",
                        parse_mode="HTML"
                    )
            
            if posts_to_publish:
                save_scheduled_posts(scheduled_posts)
                
        except Exception as e:
            print(f"Помилка в задачі моніторингу запланованих постів: {e}")
            await asyncio.sleep(300)

# ================== КОМАНДИ БОТА ==================
@bot.message_handler(commands=['start'])
def start_handler(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас немає доступу до цього бота.")
        return
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👑 Адмін-панель")
    bot.send_message(
        message.chat.id,
        "👋 <b>Вітаю в міні-боті!</b>\n\n"
        "Функції:\n"
        "🚨 Моніторинг тривог через API alerts.in.ua\n"
        "⏰ Заплановані пости\n\n"
        "Оберіть дію з меню:",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda message: message.text == "👑 Адмін-панель")
def admin_panel(message):
    if message.from_user.id != ADMIN_ID:
        bot.send_message(message.chat.id, "⛔ У вас немає доступу до адмін-панелі.")
        return
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("➕ Новий запланований пост")
    markup.add("📋 Список запланованих постів")
    markup.add("🗑 Видалити запланований пост")
    markup.add("📊 Статистика")
    markup.add("🔙 Головне меню")
    
    bot.send_message(
        message.chat.id,
        "👑 <b>Адмін-панель</b>\n\n"
        "Оберіть дію з меню:",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda message: message.text == "🔙 Головне меню")
def back_to_main_menu(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("👑 Адмін-панель")
    
    bot.send_message(
        message.chat.id,
        "🔙 <b>Повернуто до головного меню</b>",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda message: message.text == "📊 Статистика")
def stats_handler(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    alert_state = load_alert_state()
    scheduled_posts = load_scheduled_posts()
    
    stats_text = "📊 <b>Статистика:</b>\n\n"
    stats_text += f"⏰ <b>Запланованих постів:</b> {len(scheduled_posts)}\n\n"
    
    stats_text += f"🚨 <b>Тривога активна (API):</b> {'Так' if alert_state['active'] else 'Ні'}\n"
    if alert_state['active'] and alert_state['start_time']:
        start = datetime.fromisoformat(alert_state["start_time"])
        seconds = int((datetime.now() - start).total_seconds())
        duration = format_duration(seconds)
        stats_text += f"⏱ <b>Тривалість тривоги:</b> {duration}\n"
    
    bot.send_message(message.chat.id, stats_text, parse_mode="HTML")

# ================== ЗАПЛАНУВАНІ ПОСТИ ==================
class ScheduleState:
    def __init__(self):
        self.state = {}
    
    def set_data(self, user_id, key, value):
        if user_id not in self.state:
            self.state[user_id] = {}
        self.state[user_id][key] = value
    
    def get_data(self, user_id, key, default=None):
        return self.state.get(user_id, {}).get(key, default)
    
    def clear(self, user_id):
        if user_id in self.state:
            del self.state[user_id]

schedule_state = ScheduleState()

@bot.message_handler(func=lambda message: message.text == "➕ Новий запланований пост")
def start_scheduled_post(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    schedule_state.clear(message.from_user.id)
    schedule_state.set_data(message.from_user.id, 'step', 'waiting_content')
    
    bot.send_message(
        message.chat.id,
        "➕ <b>Новий запланований пост</b>\n\n"
        "Надішліть контент для посту (текст, фото, відео з описом).\n\n"
        "Щоб скасувати, напишіть /cancel",
        parse_mode="HTML"
    )

@bot.message_handler(func=lambda message: message.text == "📋 Список запланованих постів")
def list_scheduled_posts(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    scheduled_posts = load_scheduled_posts()
    
    if not scheduled_posts:
        bot.send_message(message.chat.id, "📭 Немає запланованих постів.")
        return
    
    sorted_posts = sorted(
        scheduled_posts.items(),
        key=lambda x: x[1].get("scheduled_time", datetime.now())
    )
    
    now = datetime.now()
    
    for i in range(0, len(sorted_posts), 5):
        batch = sorted_posts[i:i+5]
        response_text = "📋 <b>Заплановані пости:</b>\n\n"
        
        for post_id, post in batch:
            scheduled_time = post.get("scheduled_time")
            if isinstance(scheduled_time, str):
                scheduled_time = datetime.fromisoformat(scheduled_time)
            
            time_str = scheduled_time.strftime("%d.%m.%Y %H:%M")
            
            if scheduled_time <= now:
                status = "🟡 (Час настав)"
            else:
                time_left = scheduled_time - now
                hours_left = int(time_left.total_seconds() // 3600)
                days_left = hours_left // 24
                
                if days_left > 0:
                    status = f"🟢 ({days_left} дн.)"
                elif hours_left > 0:
                    status = f"🟢 ({hours_left} год.)"
                else:
                    minutes_left = int((time_left.total_seconds() % 3600) // 60)
                    status = f"🟢 ({minutes_left} хв.)"
            
            post_text = post.get("text", "Без тексту")
            if len(post_text) > 50:
                preview_text = post_text[:50] + "..."
            else:
                preview_text = post_text
            
            response_text += f"<b>ID:</b> {post_id}\n"
            response_text += f"<b>Час:</b> {time_str} {status}\n"
            response_text += f"<b>Текст:</b> {preview_text}\n"
            
            if post.get("media_type"):
                response_text += f"<b>Медіа:</b> {post['media_type'].upper()}\n"
            
            response_text += "─" * 20 + "\n\n"
        
        bot.send_message(message.chat.id, response_text, parse_mode="HTML")
    
    # Загальна статистика
    stats_text = f"\n📊 <b>Загальна статистика:</b>\n"
    stats_text += f"• Всього заплановано: {len(scheduled_posts)} постів\n"
    
    upcoming = sum(1 for post in scheduled_posts.values() 
                  if isinstance(post.get("scheduled_time"), datetime) and post["scheduled_time"] > now)
    stats_text += f"• Очікують публікації: {upcoming} постів\n"
    
    overdue = len(scheduled_posts) - upcoming
    if overdue > 0:
        stats_text += f"• Час настав: {overdue} постів\n"
    
    bot.send_message(message.chat.id, stats_text, parse_mode="HTML")

@bot.message_handler(func=lambda message: message.text == "🗑 Видалити запланований пост")
def delete_scheduled_post_menu(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    scheduled_posts = load_scheduled_posts()
    
    if not scheduled_posts:
        bot.send_message(message.chat.id, "📭 Немає запланованих постів для видалення.")
        return
    
    markup = telebot.types.InlineKeyboardMarkup()
    
    for post_id, post in list(scheduled_posts.items())[:10]:
        scheduled_time = post.get("scheduled_time")
        if isinstance(scheduled_time, str):
            scheduled_time = datetime.fromisoformat(scheduled_time)
        
        time_str = scheduled_time.strftime("%d.%m %H:%M")
        
        markup.add(
            telebot.types.InlineKeyboardButton(
                text=f"🗑 {post_id} ({time_str})",
                callback_data=f"delete_post:{post_id}"
            )
        )
    
    bot.send_message(
        message.chat.id,
        "🗑 <b>Видалити запланований пост</b>\n\n"
        "Оберіть пост для видалення:",
        reply_markup=markup,
        parse_mode="HTML"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('delete_post:'))
def delete_scheduled_post_callback(call):
    if call.from_user.id != ADMIN_ID:
        return
    
    post_id = call.data.split(':')[1]
    
    scheduled_posts = load_scheduled_posts()
    
    if post_id not in scheduled_posts:
        bot.answer_callback_query(call.id, "⚠️ Пост не знайдено")
        return
    
    post = scheduled_posts.pop(post_id)
    
    if post.get("media_path") and os.path.exists(post["media_path"]):
        os.remove(post["media_path"])
    
    save_scheduled_posts(scheduled_posts)
    
    bot.edit_message_text(
        "🗑 Запланований пост видалено!",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "🗑 Пост видалено")

# Обробка контенту для запланованого поста
@bot.message_handler(content_types=['text', 'photo', 'video', 'document'])
def handle_content(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    step = schedule_state.get_data(message.from_user.id, 'step')
    
    if step == 'waiting_content':
        # Зберігаємо контент
        text = message.text or message.caption or ""
        
        if not text and not (message.photo or message.video or (message.document and message.document.mime_type and 'video' in message.document.mime_type)):
            bot.send_message(message.chat.id, "❌ Потрібно надіслати текст або медіа з описом.")
            return
        
        # Обробляємо медіа
        media_file = None
        media_type = None
        
        if message.photo:
            media_type = "photo"
            file_info = bot.get_file(message.photo[-1].file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(downloaded_file)
            temp_file.close()
            media_file = temp_file.name
            
        elif message.video:
            if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
                bot.send_message(
                    message.chat.id,
                    f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                    f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ."
                )
                return
            
            media_type = "video"
            file_info = bot.get_file(message.video.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
            temp_file.write(downloaded_file)
            temp_file.close()
            media_file = temp_file.name
            
        elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
            if message.document.file_size and message.document.file_size > MAX_VIDEO_SIZE:
                bot.send_message(
                    message.chat.id,
                    f"❌ Відео занадто велике ({message.document.file_size // (1024 * 1024)} МБ). "
                    f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ."
                )
                return
            
            media_type = "video"
            file_info = bot.get_file(message.document.file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            
            file_name = message.document.file_name or "video.mp4"
            if '.' in file_name:
                ext = '.' + file_name.split('.')[-1]
            else:
                ext = '.mp4'
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
            temp_file.write(downloaded_file)
            temp_file.close()
            media_file = temp_file.name
        
        # Зберігаємо дані
        schedule_state.set_data(message.from_user.id, 'text', text)
        schedule_state.set_data(message.from_user.id, 'media_file', media_file)
        schedule_state.set_data(message.from_user.id, 'media_type', media_type)
        schedule_state.set_data(message.from_user.id, 'step', 'waiting_date')
        
        bot.send_message(
            message.chat.id,
            "⏰ <b>Запланувати пост</b>\n\n"
            "Введіть дату для публікації у форматі <b>DD.MM.YYYY</b>\n"
            "Наприклад: <code>01.01.2026</code>\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode="HTML"
        )
    
    elif step == 'waiting_date':
        if message.text == '/cancel':
            cancel_schedule(message)
            return
        
        date_text = message.text.strip()
        
        date_pattern = r'^\d{2}\.\d{2}\.\d{4}$'
        if not re.match(date_pattern, date_text):
            bot.send_message(
                message.chat.id,
                "❌ Неправильний формат дати!\n\n"
                "Введіть дату у форматі <b>DD.MM.YYYY</b>\n"
                "Наприклад: <code>01.01.2026</code>\n\n"
                "Спробуйте ще раз:",
                parse_mode="HTML"
            )
            return
        
        try:
            day, month, year = map(int, date_text.split('.'))
            date_obj = datetime(year, month, day)
            
            if date_obj.date() < datetime.now().date():
                bot.send_message(
                    message.chat.id,
                    "❌ Дата не може бути в минулому!\n\n"
                    "Введіть майбутню дату:",
                    parse_mode="HTML"
                )
                return
            
            schedule_state.set_data(message.from_user.id, 'date', date_text)
            schedule_state.set_data(message.from_user.id, 'date_obj', date_obj)
            schedule_state.set_data(message.from_user.id, 'step', 'waiting_time')
            
            bot.send_message(
                message.chat.id,
                "⏰ <b>Запланувати пост</b>\n\n"
                "Введіть час для публікації у форматі <b>HH:MM</b>\n"
                "Наприклад: <code>08:00</code>\n\n"
                "Щоб скасувати, напишіть /cancel",
                parse_mode="HTML"
            )
            
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Неправильна дата!\n\n"
                "Перевірте, чи існує така дата (наприклад, 30.02 - неправильна).\n"
                "Спробуйте ще раз:",
                parse_mode="HTML"
            )
    
    elif step == 'waiting_time':
        if message.text == '/cancel':
            cancel_schedule(message)
            return
        
        time_text = message.text.strip()
        
        time_pattern = r'^\d{2}:\d{2}$'
        if not re.match(time_pattern, time_text):
            bot.send_message(
                message.chat.id,
                "❌ Неправильний формат часу!\n\n"
                "Введіть час у форматі <b>HH:MM</b>\n"
                "Наприклад: <code>08:00</code>\n\n"
                "Спробуйте ще раз:",
                parse_mode="HTML"
            )
            return
        
        try:
            hours, minutes = map(int, time_text.split(':'))
            
            if not (0 <= hours < 24) or not (0 <= minutes < 60):
                raise ValueError
            
            # Отримуємо всі дані
            text = schedule_state.get_data(message.from_user.id, 'text')
            media_file = schedule_state.get_data(message.from_user.id, 'media_file')
            media_type = schedule_state.get_data(message.from_user.id, 'media_type')
            date_text = schedule_state.get_data(message.from_user.id, 'date')
            date_obj = schedule_state.get_data(message.from_user.id, 'date_obj')
            
            # Створюємо повний об'єкт datetime
            scheduled_time = datetime(
                date_obj.year, date_obj.month, date_obj.day,
                hours, minutes
            )
            
            if scheduled_time <= datetime.now():
                bot.send_message(
                    message.chat.id,
                    "❌ Час не може бути в минулому!\n\n"
                    "Введіть майбутній час:",
                    parse_mode="HTML"
                )
                return
            
            # Готуємо дані для збереження
            scheduled_posts = load_scheduled_posts()
            
            # Створюємо унікальний ID для запланованого поста
            scheduled_post_id = int(datetime.now().timestamp() * 1000)
            
            # Копіюємо медіа файл, якщо він є
            media_path = None
            if media_file and os.path.exists(media_file):
                ext = os.path.splitext(media_file)[1]
                media_path = os.path.join(tempfile.gettempdir(), f"scheduled_{scheduled_post_id}{ext}")
                shutil.copy2(media_file, media_path)
                
                # Видаляємо оригінальний тимчасовий файл
                os.remove(media_file)
            
            # Додаємо футер до тексту
            final_text = text + f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"
            
            # Зберігаємо запланований пост
            scheduled_posts[str(scheduled_post_id)] = {
                "text": final_text,
                "media_path": media_path,
                "media_type": media_type,
                "scheduled_time": scheduled_time,
                "original_scheduled_time": f"{date_text} {time_text}",
                "created_at": datetime.now().isoformat(),
                "source": "admin_created"
            }
            
            save_scheduled_posts(scheduled_posts)
            
            # Очищаємо стан
            schedule_state.clear(message.from_user.id)
            
            # Відправляємо підтвердження
            formatted_time = scheduled_time.strftime("%d.%m.%Y %H:%M")
            bot.send_message(
                message.chat.id,
                f"✅ <b>Новий запланований пост створено!</b>\n\n"
                f"📅 <b>Дата публікації:</b> {formatted_time}\n"
                f"🏷 <b>ID запланованого поста:</b> {scheduled_post_id}\n\n"
                f"Пост буде автоматично опубліковано у вказаний час.",
                parse_mode="HTML"
            )
            
            # Відправляємо попередній перегляд
            preview_text = f"⏰ <b>Новий запланований пост</b> (ID: {scheduled_post_id})\n\n"
            preview_text += f"📅 <b>Заплановано на:</b> {formatted_time}\n\n"
            
            if len(final_text) > 500:
                preview_text += f"{final_text[:500]}..."
            else:
                preview_text += final_text
            
            bot.send_message(message.chat.id, preview_text, parse_mode="HTML")
            
            print(f"⏰ Створено новий запланований пост ID: {scheduled_post_id} на {formatted_time}")
            
        except ValueError:
            bot.send_message(
                message.chat.id,
                "❌ Неправильний час!\n\n"
                "Години повинні бути від 00 до 23, хвилини від 00 до 59.\n"
                "Спробуйте ще раз:",
                parse_mode="HTML"
            )

def cancel_schedule(message):
    # Очищаємо тимчасові файли
    media_file = schedule_state.get_data(message.from_user.id, 'media_file')
    if media_file and os.path.exists(media_file):
        os.remove(media_file)
    
    schedule_state.clear(message.from_user.id)
    
    bot.send_message(
        message.chat.id,
        "❌ Запланування скасовано.",
        parse_mode="HTML"
    )

@bot.message_handler(commands=['cancel'])
def cancel_handler(message):
    if message.from_user.id != ADMIN_ID:
        return
    
    cancel_schedule(message)

# ================== ЗАПУСК ==================
async def main():
    print("🚀 Міні-бот запущений!")
    print("🎯 Цільовий канал:", TARGET_CHANNEL)
    print("🚨 Моніторинг тривог: API alerts.in.ua")
    print("⏰ Заплановані пости: активовано")
    print("👑 Доступ: лише адмін")
    print("📱 Бот готовий до роботи")
    
    # Запускаємо фоновий моніторинг тривог
    asyncio.create_task(alerts_monitoring_task())
    
    # Запускаємо фоновий моніторинг запланованих постів
    asyncio.create_task(scheduled_posts_monitoring_task())
    
    # Запускаємо бота
    print("🤖 Бот починає працювати...")
    bot.infinity_polling()

if __name__ == "__main__":
    asyncio.run(main())
