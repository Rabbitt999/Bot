import asyncio
import os
import tempfile
import json
import html
import aiohttp
from datetime import datetime, timedelta
from telethon import TelegramClient, events, types
from telethon.sessions import StringSession
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, CallbackQuery, Message,
    ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
)
from aiogram.enums import ParseMode, ContentType
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, CommandStart
import re
from typing import Optional, Dict, Any, Tuple
import shutil
import logging

# ================== НАЛАШТУВАННЯ ЛОГУВАННЯ ==================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

# ================== НАЛАШТУВАННЯ ==================
API_ID = 30210758
API_HASH = "1e9b089b6a38dc9cd5e8978d03f5dd33"
SESSION_NAME = "SambrNewsBot"

BOT_TOKEN = "8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g"
ADMIN_ID = 6974875043

# API alerts.in.ua
ALERTS_API_TOKEN = "f7f5a126f8865ad43bbd19d522d6c489b11486c9ab2203"
ALERTS_API_BASE_URL = "https://alerts.com.ua/api"

# ID області для Львівської області (25 - Львівська область)
LVIV_REGION_ID = 25

SOURCE_CHANNELS = [
    "dsns_lviv",
    "lviv_region_poluce",
    "lvivpatrolpolice",
    "lvivoblprok",
    "lvivych_news"
]

TARGET_CHANNEL = "@Test_Chenal_0"
TARGET_CHANNEL_USERNAME = "Test_Chenal_0"
TARGET_CHANNEL_TITLE = "🧪 Test Channel"

# Розширені ключові слова для відключень світла та графіків
POWER_KEYWORDS = [
    "відключення", "відключення світла", "відключення електроенергії",
    "аварійне відключення", "планові відключення",
    "графік", "графіка", "графіку", "графіки",
    "графік відключень", "графіки відключень",
    "розклад відключень", "початок відключень",
    "енергетика", "енергопостачання", "енергозабезпечення",
    "електроенергії", "електроенергія", "електропостачання",
    "світло", "світла", "світлу",
    "аварія", "ремонт", "відновлення",
    "обленерго", "енерго", "постачання",
    "подача", "енергокомпанія", "електромережі",
    "ЛЬВІВОБЛЕНЕРГО", "ЛЬВІВЕНЕРГО", "ДТЕК",
    "енергоремонт", "аварійні роботи", "планові роботи"
]

# Словник для визначення джерел новин
SOURCE_NAMES = {
    "dsns_lviv": "ДСНС Львівщини",
    "lviv_region_poluce": "Поліція Львівської області",
    "lvivpatrolpolice": "Патрульна поліція Львова",
    "lvivoblprok": "Львівська обласна прокуратура",
    "lvivych_news": "Львич News"
}

SAMBIR_KEYWORDS = [
    "самбір", "Самборі", "самбірського", "самбірський", "самбірському",
    "самбірська", "самбірські", "самбірських", "самбіряни", "самбірщина",
    "самбірський район", "самбірщини", "самбірську", "самбірським",
    "Львів", "Львова", "Львові", "Львівський"
]

DB_FILE = "database.json"
ALERT_STATE_FILE = "alert_state.json"
LAST_ALERT_CHECK_FILE = "last_alert_check.json"
SCHEDULED_POSTS_FILE = "scheduled_posts.json"
SCHEDULED_TEMP_FILE = "scheduled_temp.json"
SESSION_FILE = "telethon_session.txt"

MAX_VIDEO_SIZE = 100 * 1024 * 1024

# ================== FSM ==================
class ShareStates(StatesGroup):
    waiting_info = State()
    waiting_ad = State()


class EditStates(StatesGroup):
    waiting_edit_text = State()
    waiting_edit_media = State()


class ScheduledPostStates(StatesGroup):
    waiting_date = State()
    waiting_time = State()


class NewScheduledPostStates(StatesGroup):
    waiting_text = State()
    waiting_date = State()
    waiting_time = State()


class TelegramLoginStates(StatesGroup):
    waiting_phone = State()
    waiting_code = State()
    waiting_password = State()


# ================== ТЕЛЕГРАМ АВТОРИЗАЦІЯ ==================
def save_session(session_string: str):
    """Зберігає сесію Telethon у файл"""
    try:
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(session_string)
        logger.info("✅ Сесія збережена")
        return True
    except Exception as e:
        logger.error(f"❌ Помилка збереження сесії: {e}")
        return False


def load_session() -> Optional[str]:
    """Завантажує сесію Telethon з файлу"""
    if not os.path.exists(SESSION_FILE):
        return None
    try:
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_string = f.read().strip()
        if session_string:
            logger.info("✅ Сесія завантажена з файлу")
            return session_string
    except Exception as e:
        logger.error(f"❌ Помилка завантаження сесії: {e}")
    return None


async def create_telegram_client():
    """Створює Telethon клієнт зі збереженої сесії або нова сесія"""
    session_string = load_session()
    
    if session_string:
        try:
            client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
            await client.connect()
            
            # Перевіряємо, чи сесія дійсна
            if await client.is_user_authorized():
                logger.info("✅ Авторизовано з існуючої сесії")
                return client
            else:
                logger.warning("❌ Сесія недійсна, потрібна нова авторизація")
        except Exception as e:
            logger.error(f"❌ Помилка підключення: {e}")
    
    # Якщо немає сесії або вона недійсна
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    return client


# ================== СТАН ТРИВОГИ ==================
def load_alert_state():
    if not os.path.exists(ALERT_STATE_FILE):
        return {"active": False, "start_time": None}
    try:
        with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"active": False, "start_time": None}


def save_alert_state(state: dict):
    with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_last_alert_check():
    if not os.path.exists(LAST_ALERT_CHECK_FILE):
        return {"last_check": datetime.now().isoformat()}
    try:
        with open(LAST_ALERT_CHECK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"last_check": datetime.now().isoformat()}


def save_last_alert_check(state: dict):
    with open(LAST_ALERT_CHECK_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def format_duration(seconds: int) -> str:
    minutes = seconds // 60
    hours = minutes // 60
    minutes = minutes % 60
    if hours > 0:
        return f"{hours} год {minutes} хв"
    return f"{minutes} хв"


# ================== БАЗА ==================
def load_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ================== ЗАПЛАНУВАНІ ПОСТИ ==================
def load_scheduled_posts():
    """Завантажує список запланованих постів з файлу"""
    if not os.path.exists(SCHEDULED_POSTS_FILE):
        return {}
    try:
        with open(SCHEDULED_POSTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Конвертуємо строки дат назад в datetime об'єкти
            for post_id, post in data.items():
                if "scheduled_time" in post:
                    post["scheduled_time"] = datetime.fromisoformat(post["scheduled_time"])
            return data
    except Exception as e:
        logger.error(f"Помилка при завантаженні запланованих постів: {e}")
        return {}


def save_scheduled_posts(posts: dict):
    """Зберігає список запланованих постів у файл"""
    serializable_posts = {}
    for post_id, post in posts.items():
        serializable_posts[post_id] = post.copy()
        if "scheduled_time" in serializable_posts[post_id]:
            serializable_posts[post_id]["scheduled_time"] = serializable_posts[post_id][
                "scheduled_time"].isoformat()

    with open(SCHEDULED_POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(serializable_posts, f, ensure_ascii=False, indent=2)


# ================== ТИМЧАСОВЕ ЗБЕРЕЖЕННЯ ДАНИХ ПОСТА ==================
def save_temp_post_data(post_id: int, post_data: dict):
    """Зберігає дані поста в тимчасовий файл"""
    try:
        temp_data = post_data.copy()
        with open(SCHEDULED_TEMP_FILE, "w", encoding="utf-8") as f:
            json.dump({str(post_id): temp_data}, f, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Помилка збереження тимчасових даних: {e}")
        return False


def load_temp_post_data(post_id: int) -> Optional[dict]:
    """Завантажує дані поста з тимчасового файлу"""
    if not os.path.exists(SCHEDULED_TEMP_FILE):
        return None

    try:
        with open(SCHEDULED_TEMP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get(str(post_id))
    except Exception as e:
        logger.error(f"Помилка завантаження тимчасових даних: {e}")
        return None


def delete_temp_post_data(post_id: int):
    """Видаляє тимчасові дані поста"""
    if not os.path.exists(SCHEDULED_TEMP_FILE):
        return

    try:
        with open(SCHEDULED_TEMP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if str(post_id) in data:
            del data[str(post_id)]

            if data:
                with open(SCHEDULED_TEMP_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
            else:
                os.remove(SCHEDULED_TEMP_FILE)
    except Exception as e:
        logger.error(f"Помилка видалення тимчасових даних: {e}")


# ================== ФУНКЦІЯ ЕКРАНУВАННЯ HTML ==================
def escape_html(text: str) -> str:
    """Екранує спеціальні символи для HTML"""
    if not text:
        return ""
    return html.escape(text)


# ================== ОЧИСТКА ТЕКСТУ ==================
def clean_text(text: str) -> str:
    if not text:
        return ""

    lines = text.splitlines()
    result = []

    for line in lines:
        low = line.lower()
        if "підписатися" in low:
            continue
        if "перейти" in low and "канал" in low:
            continue
        if "наш канал" in low:
            continue
        if "наш сайт" in low:
            continue
        if "|" in line and "@" not in line:
            continue
        if any(x in low for x in ["facebook", "instagram", "twitter", "t.me/", "https://"]):
            if len(lines) > 1:
                continue

        result.append(line)

    return "\n".join(result).strip()


def contains_sambir(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(word.lower() in text_lower for word in SAMBIR_KEYWORDS)


def contains_power_keywords(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword in text_lower for keyword in POWER_KEYWORDS)


# ================== API alerts.in.ua ==================
async def check_alerts_in_ua():
    """Перевіряє статус повітряної тривоги через API alerts.in.ua"""
    headers = {
        "X-API-Key": ALERTS_API_TOKEN,
        "Accept": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{ALERTS_API_BASE_URL}/states", headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Помилка API: {response.status}")
                    return None

                data = await response.json()
                lviv_region = None
                for region in data.get("states", []):
                    if region.get("id") == LVIV_REGION_ID:
                        lviv_region = region
                        break

                if not lviv_region:
                    logger.warning("Не знайдено Львівську область в даних API")
                    return None

                alert_active = lviv_region.get("alert", False)
                alert_state = load_alert_state()
                last_check_data = load_last_alert_check()

                changed = False

                if alert_active != alert_state["active"]:
                    changed = True

                    if alert_active:
                        alert_state["active"] = True
                        alert_state["start_time"] = datetime.now().isoformat()
                        logger.info(f"🚨 Тривога почалася у Львівській області")
                    else:
                        alert_state["active"] = False
                        alert_state["start_time"] = None
                        logger.info(f"✅ Відбій тривоги у Львівській області")

                    save_alert_state(alert_state)

                last_check_data["last_check"] = datetime.now().isoformat()
                save_last_alert_check(last_check_data)

                return {
                    "active": alert_active,
                    "changed": changed,
                    "state": alert_state
                }

    except Exception as e:
        logger.error(f"Помилка при перевірці API alerts.in.ua: {e}")
        return None


async def send_alert_to_channel(is_start: bool, duration_seconds: int = None):
    """Надсилає повідомлення про тривогу або відбій у канал"""
    footer = f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

    if is_start:
        message_text = f"🚨УВАГА, повітряна тривога у Львівській області!{footer}"
        await bot.send_message(TARGET_CHANNEL, message_text)
        logger.info("📢 Надіслано повідомлення про початок тривоги")
    else:
        if duration_seconds:
            duration = format_duration(duration_seconds)
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!\n\n⏱ <b>Тривалість:</b> {duration}{footer}"
        else:
            message_text = f"✅УВАГА, відбій повітряної тривоги у Львівській області!{footer}"

        await bot.send_message(TARGET_CHANNEL, message_text)
        logger.info("📢 Надіслано повідомлення про відбій тривоги")


# ================== ФОНОВА ЗАДАЧА ДЛЯ ПЕРЕВІРКИ ТРИВОГ ==================
async def alerts_monitoring_task():
    """Фонова задача для регулярної перевірки статусу тривоги"""
    logger.info("🔍 Запущено моніторинг тривог через API alerts.in.ua")

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
            logger.error(f"Помилка в задачі моніторингу тривог: {e}")
            await asyncio.sleep(30)


# ================== ФОНОВА ЗАДАЧА ДЛЯ ПЕРЕВІРКИ ЗАПЛАНУВАНИХ ПОСТІВ ==================
async def scheduled_posts_monitoring_task():
    """Фонова задача для перевірки та публікації запланованих постів"""
    logger.info("⏰ Запущено моніторинг запланованих постів")

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
                            await bot.send_photo(
                                TARGET_CHANNEL,
                                FSInputFile(post["media_path"]),
                                caption=post["text"]
                            )
                        elif post["media_type"] == "video":
                            await bot.send_video(
                                TARGET_CHANNEL,
                                FSInputFile(post["media_path"]),
                                caption=post["text"]
                            )
                        os.remove(post["media_path"])
                    else:
                        await bot.send_message(TARGET_CHANNEL, post["text"])

                    scheduled_time_str = post.get("original_scheduled_time", "Невідомо")
                    await bot.send_message(
                        ADMIN_ID,
                        f"✅ <b>Запланований пост опубліковано!</b>\n\n"
                        f"📅 Запланований час: {scheduled_time_str}\n"
                        f"🏷 ID: {post_id}",
                        parse_mode=ParseMode.HTML
                    )

                    logger.info(f"⏰ Опубліковано запланований пост ID: {post_id}")

                except Exception as e:
                    logger.error(f"Помилка при публікації запланованого поста {post_id}: {e}")
                    await bot.send_message(
                        ADMIN_ID,
                        f"❌ <b>Помилка при публікації запланованого поста!</b>\n\n"
                        f"🏷 ID: {post_id}\n"
                        f"📝 Помилка: {str(e)}",
                        parse_mode=ParseMode.HTML
                    )

            if posts_to_publish:
                save_scheduled_posts(scheduled_posts)

        except Exception as e:
            logger.error(f"Помилка в задачі моніторингу запланованих постів: {e}")
            await asyncio.sleep(300)


# ================== GLOBALS ==================
telegram_client = None
client_authorized = False
pending_posts = {}
phone_code_hash = None

# ================== AIROGRAM ==================
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ================== ПАНЕЛЬ МЕНЮ (REPLY KEYBOARD) ==================
def get_main_menu_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📤 Поділитися інформацією")],
        [KeyboardButton(text="📢 Розмістити рекламу")]
    ]

    if user_id == ADMIN_ID:
        keyboard.append([KeyboardButton(text="👑 Адмін-панель")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть опцію з меню"
    )


def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📋 Очікуючі пости")],
        [KeyboardButton(text="📊 Статистика")],
        [KeyboardButton(text="⏰ Заплановані пости")],
        [KeyboardButton(text="➕ Новий запланований пост")],
        [KeyboardButton(text="🔐 Налаштування Telethon")],
        [KeyboardButton(text="🔙 Головне меню")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію в адмін-панелі"
    )


def get_telethon_setup_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📱 Ввести номер телефону")],
        [KeyboardButton(text="🔢 Ввести код з Telegram")],
        [KeyboardButton(text="✅ Перевірити статус Telethon")],
        [KeyboardButton(text="🔙 Назад в адмін-панель")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію з Telethon"
    )


def get_scheduled_posts_keyboard() -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text="📋 Список запланованих постів")],
        [KeyboardButton(text="🗑 Видалити запланований пост")],
        [KeyboardButton(text="🔙 Назад в адмін-панель")]
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        input_field_placeholder="Оберіть дію з запланованими постами"
    )


# ================== КНОПКИ ДЛЯ МОДЕРАЦІЇ (INLINE) ==================
def moderation_keyboard(post_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Опублікувати", callback_data=f"publish:{post_id}"),
                InlineKeyboardButton(text="✏️ Редагувати", callback_data=f"edit:{post_id}")
            ],
            [
                InlineKeyboardButton(text="⏰ Запланувати", callback_data=f"schedule:{post_id}"),
                InlineKeyboardButton(text="❌ Відмінити", callback_data=f"cancel:{post_id}")
            ]
        ]
    )


def edit_options_keyboard(post_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📝 Текст", callback_data=f"edit_text:{post_id}"),
                InlineKeyboardButton(text="🖼 Медіа", callback_data=f"edit_media:{post_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Назад", callback_data=f"back_edit:{post_id}")
            ]
        ]
    )


def scheduled_post_options_keyboard(post_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Публікувати зараз", callback_data=f"schedule_publish_now:{post_id}"),
                InlineKeyboardButton(text="🗑 Видалити", callback_data=f"schedule_delete:{post_id}")
            ],
            [
                InlineKeyboardButton(text="🔙 Скасувати", callback_data=f"schedule_cancel:{post_id}")
            ]
        ]
    )


# ================== ФУНКЦІЯ ДЛЯ ЗАВАНТАЖЕННЯ МЕДІА ==================
async def download_media(event, media_type: str):
    if not event.message.media:
        return None, None

    file_ext = ""

    if media_type == "photo":
        file_ext = ".jpg"
    elif media_type == "video":
        if hasattr(event.message, 'video') and event.message.video:
            mime_type = event.message.video.mime_type
            if mime_type:
                if 'mp4' in mime_type:
                    file_ext = ".mp4"
                elif 'avi' in mime_type:
                    file_ext = ".avi"
                elif 'mov' in mime_type:
                    file_ext = ".mov"
                else:
                    file_ext = ".mp4"
            else:
                file_ext = ".mp4"
    elif media_type == "document":
        if hasattr(event.message, 'document') and event.message.document:
            mime_type = event.message.document.mime_type
            if mime_type and 'video' in mime_type:
                file_name = event.message.document.attributes[
                    0].file_name if event.message.document.attributes else f"video_{event.message.id}"
                if '.' in file_name:
                    file_ext = '.' + file_name.split('.')[-1]
                else:
                    file_ext = ".mp4"

    file_name = f"{event.message.id}_{media_type}{file_ext}"
    file_path = os.path.join(tempfile.gettempdir(), file_name)

    try:
        await event.message.download_media(file_path)
        return file_path, file_ext
    except Exception as e:
        logger.error(f"Помилка завантаження {media_type}: {e}")
        return None, None


def get_media_type(event):
    if event.message.photo:
        return "photo"
    elif event.message.video:
        return "video"
    elif event.message.document:
        if hasattr(event.message, 'document') and event.message.document:
            mime_type = event.message.document.mime_type
            if mime_type and 'video' in mime_type:
                return "video"
    return None


async def remove_buttons_after_action(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=None
        )
    except Exception as e:
        logger.error(f"Не вдалося видалити кнопки: {e}")


# ================== TELETHON АВТОРИЗАЦІЯ ==================
async def setup_telegram_client():
    """Налаштування Telethon клієнта"""
    global telegram_client, client_authorized
    
    telegram_client = await create_telegram_client()
    
    if await telegram_client.is_user_authorized():
        client_authorized = True
        logger.info("✅ Telethon клієнт авторизовано")
        return True
    else:
        logger.warning("⚠️ Telethon клієнт не авторизовано")
        client_authorized = False
        return False


async def send_code_request(phone: str):
    """Надсилання запиту на код для Telethon"""
    global telegram_client, phone_code_hash
    
    try:
        if not telegram_client.is_connected():
            await telegram_client.connect()
        
        # Надсилаємо код
        result = await telegram_client.send_code_request(phone)
        phone_code_hash = result.phone_code_hash
        logger.info(f"✅ Код надіслано на номер: {phone}")
        return True, "✅ Код надіслано! Перевірте Telegram та введіть код"
    except Exception as e:
        logger.error(f"❌ Помилка при надсиланні коду: {e}")
        return False, f"❌ Помилка: {str(e)}"


async def sign_in_with_code(code: str):
    """Авторизація з кодом"""
    global telegram_client, client_authorized, phone_code_hash
    
    try:
        if not telegram_client or not phone_code_hash:
            return False, "❌ Спочатку введіть номер телефону"
        
        await telegram_client.sign_in(code=code, phone_code_hash=phone_code_hash)
        
        # Зберігаємо сесію
        session_string = telegram_client.session.save()
        save_session(session_string)
        
        client_authorized = True
        logger.info("✅ Успішно авторизовано!")
        return True, "✅ Успішно авторизовано! Telethon готовий до роботи"
    except Exception as e:
        logger.error(f"❌ Помилка при авторизації: {e}")
        return False, f"❌ Помилка: {str(e)}"


async def sign_in_with_password(password: str):
    """Авторизація з паролем (для 2FA)"""
    global telegram_client, client_authorized
    
    try:
        await telegram_client.sign_in(password=password)
        
        # Зберігаємо сесію
        session_string = telegram_client.session.save()
        save_session(session_string)
        
        client_authorized = True
        logger.info("✅ Успішно авторизовано з паролем!")
        return True, "✅ Успішно авторизовано! Telethon готовий до роботи"
    except Exception as e:
        logger.error(f"❌ Помилка при авторизації з паролем: {e}")
        return False, f"❌ Помилка: {str(e)}"


async def check_telethon_status():
    """Перевірка статусу Telethon"""
    global telegram_client, client_authorized
    
    if not telegram_client:
        return "❌ Telethon клієнт не ініціалізовано"
    
    try:
        if await telegram_client.is_user_authorized():
            me = await telegram_client.get_me()
            return f"✅ Telethon авторизовано\n👤 Користувач: @{me.username or me.first_name}\n📱 Номер: {me.phone}"
        else:
            return "⚠️ Telethon не авторизовано. Введіть номер телефону та код"
    except Exception as e:
        return f"❌ Помилка перевірки статусу: {str(e)}"


async def start_telethon_monitoring():
    """Запуск моніторингу Telethon"""
    global telegram_client, client_authorized
    
    if not telegram_client or not client_authorized:
        logger.error("❌ Telethon не авторизовано, моніторинг не можна запустити")
        return False
    
    try:
        # Додаємо обробник повідомлень
        @telegram_client.on(events.NewMessage(chats=SOURCE_CHANNELS))
        async def new_message_handler(event):
            await handle_telegram_message(event)
        
        logger.info("✅ Моніторинг Telethon запущено")
        return True
    except Exception as e:
        logger.error(f"❌ Помилка запуску моніторингу: {e}")
        return False


async def handle_telegram_message(event):
    """Обробка повідомлень з Telegram через Telethon"""
    source_channel = ""
    if hasattr(event.chat, 'username') and event.chat.username:
        source_channel = event.chat.username
    elif hasattr(event.chat, 'title'):
        source_channel = event.chat.title

    text = event.message.message or ""
    media_type = get_media_type(event)
    has_media = media_type is not None

    if not text and not has_media:
        return

    text_lower = text.lower() if text else ""
    is_power = contains_power_keywords(text)
    is_sambir = contains_sambir(text)

    if is_power:
        if source_channel == "lvivych_news":
            logger.info(f"⚡ Знайдено відключення світла з Lvivych_news: {text[:50]}...")
        else:
            logger.info(f"⏭ Пропускаємо відключення світла з {source_channel} (тільки з Lvivych_news)")
            if not is_sambir:
                return
            is_power = False

    if not (is_power or is_sambir):
        return

    db = load_db()
    msg_uid = f"{event.chat_id}_{event.message.id}"
    if msg_uid in db:
        return
    db.append(msg_uid)
    save_db(db)

    cleaned = clean_text(text) if text else ""
    source_info = ""
    if source_channel in SOURCE_NAMES:
        source_info = f"\n\n📰 <b>Джерело:</b> {SOURCE_NAMES[source_channel]}"

    footer = f"{source_info}\n\n<b>{TARGET_CHANNEL_TITLE}</b>"
    final_text = cleaned + footer if cleaned else footer

    media_file = None
    if has_media:
        media_file, _ = await download_media(event, media_type)

    pending_posts[event.message.id] = {
        "text": final_text,
        "media": media_file,
        "media_type": media_type,
        "source": source_channel,
        "is_power": is_power,
        "is_sambir": is_sambir,
        "admin_message_id": None
    }

    if is_power:
        preview_type = "⚡ Відключення світла / графіки"
    else:
        preview_type = "📍 Новина з Самбірщини"

    if source_channel in SOURCE_NAMES:
        preview_type += f" | {SOURCE_NAMES[source_channel]}"

    preview = f"{preview_type}\n\n{cleaned}" if cleaned else preview_type

    if media_file:
        if media_type == "photo":
            sent_message = await bot.send_photo(ADMIN_ID, FSInputFile(media_file), caption=preview,
                                                reply_markup=moderation_keyboard(event.message.id))
        elif media_type == "video":
            sent_message = await bot.send_video(ADMIN_ID, FSInputFile(media_file), caption=preview,
                                                reply_markup=moderation_keyboard(event.message.id))

        if sent_message:
            pending_posts[event.message.id]["admin_message_id"] = sent_message.message_id
    else:
        sent_message = await bot.send_message(ADMIN_ID, preview, reply_markup=moderation_keyboard(event.message.id))
        if sent_message:
            pending_posts[event.message.id]["admin_message_id"] = sent_message.message_id

    logger.info(f"📥 Отримано нове повідомлення з {source_channel}: {'🔋 Відключення' if is_power else '📍 Самбір'}")


# ================== CALLBACK ДЛЯ INLINE КНОПОК ==================
@dp.callback_query(F.data)
async def handle_callbacks(call: CallbackQuery, state: FSMContext):
    user_id = call.from_user.id
    data = call.data

    if data.startswith("publish"):
        pid = int(data.split(":")[1])
        item = pending_posts.pop(pid, None)
        if not item:
            await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        try:
            if item["media"]:
                escaped_text = item["text"].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')

                if item["media_type"] == "photo":
                    await bot.send_photo(TARGET_CHANNEL, FSInputFile(item["media"]), caption=escaped_text)
                elif item["media_type"] == "video":
                    await bot.send_video(TARGET_CHANNEL, FSInputFile(item["media"]), caption=escaped_text)

                if os.path.exists(item["media"]):
                    os.remove(item["media"])
            else:
                escaped_text = item["text"].replace('_', '\\_').replace('*', '\\*').replace('`', '\\`')
                await bot.send_message(TARGET_CHANNEL, escaped_text)

            await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
            await call.answer("✅ Опубліковано", show_alert=True)

            logger.info(f"📤 Опубліковано пост у {TARGET_CHANNEL}: {'🔋 Відключення' if item.get('is_power') else '📍 Самбір'}")

        except Exception as e:
            await call.answer(f"❌ Помилка при публікації: {str(e)}", show_alert=True)

        return

    if data.startswith("cancel"):
        pid = int(data.split(":")[1])
        item = pending_posts.pop(pid, None)
        if item and item["media"]:
            if os.path.exists(item["media"]):
                os.remove(item["media"])

        await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
        await call.answer("❌ Відмінено", show_alert=True)
        return

    if data.startswith("edit:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        await call.message.edit_reply_markup(reply_markup=edit_options_keyboard(pid))
        await call.answer("✏️ Оберіть що редагувати", show_alert=False)
        return

    if data.startswith("back_edit:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        await call.message.edit_reply_markup(reply_markup=moderation_keyboard(pid))
        await call.answer("🔙 Повернуто", show_alert=False)
        return

    # ===== ЗАПЛАНУВАТИ ПОСТ =====
    if data.startswith("schedule:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        post_data = pending_posts[pid]
        if save_temp_post_data(pid, post_data):
            await state.update_data(
                schedule_post_id=pid,
                schedule_message_id=call.message.message_id
            )

            await call.message.answer(
                "⏰ <b>Запланувати пост</b>\n\n"
                "Введіть дату для публікації у форматі <b>DD.MM.YYYY</b>\n"
                "Наприклад: <code>01.01.2026</code>\n\n"
                "Щоб скасувати, напишіть /cancel",
                parse_mode=ParseMode.HTML
            )
            await state.set_state(ScheduledPostStates.waiting_date)
            await call.answer("📅 Введіть дату", show_alert=False)
        else:
            await call.answer("❌ Помилка збереження даних поста", show_alert=True)
        return

    if data.startswith("edit_text:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        await state.update_data(edit_post_id=pid, edit_message_id=call.message.message_id)
        await call.message.answer(
            "📝 <b>Редагування тексту</b>\n\n"
            "Надішліть новий текст для посту. Ви можете використовувати HTML-розмітку.\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(EditStates.waiting_edit_text)
        await call.answer("✏️ Надішліть новий текст", show_alert=False)
        return

    if data.startswith("edit_media:"):
        pid = int(data.split(":")[1])
        if pid not in pending_posts:
            await call.answer("⚠️ Пост не знайдено", show_alert=True)
            return

        await state.update_data(edit_post_id=pid, edit_message_id=call.message.message_id)
        await call.message.answer(
            "🖼 <b>Редагування медіа</b>\n\n"
            "Надішліть нове фото або відео. Якщо хочете видалити медіа, надішліть текст 'видалити'.\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(EditStates.waiting_edit_media)
        await call.answer("🖼 Надішліть нове медіа", show_alert=False)
        return

    # ===== ОПРАЦЮВАННЯ ЗАПЛАНУВАНИХ ПОСТІВ =====
    if data.startswith("schedule_publish_now:"):
        pid = int(data.split(":")[1])

        scheduled_posts = load_scheduled_posts()

        if str(pid) not in scheduled_posts:
            await call.answer("⚠️ Запланований пост не знайдено", show_alert=True)
            return

        post = scheduled_posts.pop(str(pid))

        try:
            if post.get("media_path") and os.path.exists(post["media_path"]):
                if post["media_type"] == "photo":
                    await bot.send_photo(
                        TARGET_CHANNEL,
                        FSInputFile(post["media_path"]),
                        caption=post["text"]
                    )
                elif post["media_type"] == "video":
                    await bot.send_video(
                        TARGET_CHANNEL,
                        FSInputFile(post["media_path"]),
                        caption=post["text"]
                    )
                os.remove(post["media_path"])
            else:
                await bot.send_message(TARGET_CHANNEL, post["text"])

            await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)

            await call.message.answer("✅ Запланований пост опубліковано зараз!")
            await call.answer("✅ Опубліковано", show_alert=True)

            save_scheduled_posts(scheduled_posts)

        except Exception as e:
            await call.answer(f"❌ Помилка: {str(e)}", show_alert=True)

        return

    if data.startswith("schedule_delete:"):
        pid = int(data.split(":")[1])

        scheduled_posts = load_scheduled_posts()

        if str(pid) not in scheduled_posts:
            await call.answer("⚠️ Запланований пост не знайдено", show_alert=True)
            return

        post = scheduled_posts.pop(str(pid))

        if post.get("media_path") and os.path.exists(post["media_path"]):
            os.remove(post["media_path"])

        await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)

        await call.message.answer("🗑 Запланований пост видалено!")
        await call.answer("🗑 Видалено", show_alert=True)

        save_scheduled_posts(scheduled_posts)

        return

    if data.startswith("schedule_cancel:"):
        await remove_buttons_after_action(bot, call.message.chat.id, call.message.message_id)
        await call.answer("🔙 Скасовано", show_alert=True)
        return


# ================== ОБРОБКА ЗАПЛАНУВАНИХ ПОСТІВ ==================
@dp.message(ScheduledPostStates.waiting_date)
async def handle_schedule_date(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Запланування скасовано.")
        data = await state.get_data()
        post_id = data.get("schedule_post_id")
        if post_id:
            delete_temp_post_data(post_id)
        await state.clear()
        return

    date_text = message.text.strip()

    date_pattern = r'^\d{2}\.\d{2}\.\d{4}$'
    if not re.match(date_pattern, date_text):
        await message.answer(
            "❌ Неправильний формат дати!\n\n"
            "Введіть дату у форматі <b>DD.MM.YYYY</b>\n"
            "Наприклад: <code>01.01.2026</code>\n\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        day, month, year = map(int, date_text.split('.'))
        date_obj = datetime(year, month, day)

        if date_obj.date() < datetime.now().date():
            await message.answer(
                "❌ Дата не може бути в минулому!\n\n"
                "Введіть майбутню дату:",
                parse_mode=ParseMode.HTML
            )
            return

        await state.update_data(schedule_date=date_text, schedule_date_obj=date_obj)

        await message.answer(
            "⏰ <b>Запланувати пост</b>\n\n"
            "Введіть час для публікації у форматі <b>HH:MM</b>\n"
            "Наприклад: <code>08:00</code>\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(ScheduledPostStates.waiting_time)

    except ValueError:
        await message.answer(
            "❌ Неправильна дата!\n\n"
            "Перевірте, чи існує така дата (наприклад, 30.02 - неправильна).\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )


@dp.message(ScheduledPostStates.waiting_time)
async def handle_schedule_time(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Запланування скасовано.")
        data = await state.get_data()
        post_id = data.get("schedule_post_id")
        if post_id:
            delete_temp_post_data(post_id)
        await state.clear()
        return

    time_text = message.text.strip()

    time_pattern = r'^\d{2}:\d{2}$'
    if not re.match(time_pattern, time_text):
        await message.answer(
            "❌ Неправильний формат часу!\n\n"
            "Введіть час у форматі <b>HH:MM</b>\n"
            "Наприклад: <code>08:00</code>\n\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        hours, minutes = map(int, time_text.split(':'))

        if not (0 <= hours < 24) or not (0 <= minutes < 60):
            raise ValueError

        data = await state.get_data()
        date_obj = data.get("schedule_date_obj")
        post_id = data.get("schedule_post_id")
        message_id = data.get("schedule_message_id")

        if not all([date_obj, post_id, message_id]):
            await message.answer("❌ Помилка: дані втрачено. Спробуйте ще раз.")
            await state.clear()
            return

        post_data = load_temp_post_data(post_id)
        if not post_data:
            await message.answer("❌ Дані поста не знайдено. Можливо, вони були видалені.")
            await state.clear()
            return

        scheduled_time = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            hours, minutes
        )

        if scheduled_time <= datetime.now():
            await message.answer(
                "❌ Час не може бути в минулому!\n\n"
                "Введіть майбутній час:",
                parse_mode=ParseMode.HTML
            )
            return

        scheduled_posts = load_scheduled_posts()
        scheduled_post_id = int(datetime.now().timestamp() * 1000)

        media_path = None
        if post_data.get("media") and os.path.exists(post_data["media"]):
            ext = os.path.splitext(post_data["media"])[1]
            media_path = os.path.join(tempfile.gettempdir(), f"scheduled_{scheduled_post_id}{ext}")
            shutil.copy2(post_data["media"], media_path)

        scheduled_posts[str(scheduled_post_id)] = {
            "text": post_data["text"],
            "media_path": media_path,
            "media_type": post_data.get("media_type"),
            "scheduled_time": scheduled_time,
            "original_scheduled_time": f"{data.get('schedule_date')} {time_text}",
            "created_at": datetime.now().isoformat(),
            "source_post_id": post_id
        }

        save_scheduled_posts(scheduled_posts)

        if post_id in pending_posts:
            if pending_posts[post_id].get("media") and os.path.exists(pending_posts[post_id]["media"]):
                os.remove(pending_posts[post_id]["media"])
            pending_posts.pop(post_id, None)

        delete_temp_post_data(post_id)

        try:
            await bot.edit_message_reply_markup(
                chat_id=ADMIN_ID,
                message_id=message_id,
                reply_markup=None
            )
        except:
            pass

        formatted_time = scheduled_time.strftime("%d.%m.%Y %H:%M")
        await message.answer(
            f"✅ <b>Пост заплановано!</b>\n\n"
            f"📅 <b>Дата публікації:</b> {formatted_time}\n"
            f"🏷 <b>ID запланованого поста:</b> {scheduled_post_id}\n\n"
            f"Пост буде автоматично опубліковано у вказаний час.",
            parse_mode=ParseMode.HTML
        )

        preview_text = f"⏰ <b>Запланований пост</b> (ID: {scheduled_post_id})\n\n"
        preview_text += f"📅 <b>Заплановано на:</b> {formatted_time}\n\n"

        post_text = post_data["text"]
        if len(post_text) > 500:
            preview_text += f"{post_text[:500]}..."
        else:
            preview_text += post_text

        await message.answer(preview_text, parse_mode=ParseMode.HTML)

        logger.info(f"⏰ Заплановано пост ID: {scheduled_post_id} на {formatted_time}")

    except ValueError:
        await message.answer(
            "❌ Неправильний час!\n\n"
            "Години повинні бути від 00 до 23, хвилини від 00 до 59.\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )

    await state.clear()


# ================== НОВИЙ СПОСІБ ДОДАВАННЯ ЗАПЛАНУВАНИХ ПОСТІВ ==================
@dp.message(F.text == "➕ Новий запланований пост")
async def handle_new_scheduled_post(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    await message.answer(
        "➕ <b>Новий запланований пост</b>\n\n"
        "Надішліть текст для посту.\n\n"
        "Щоб скасувати, напишіть /cancel",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(NewScheduledPostStates.waiting_text)


@dp.message(NewScheduledPostStates.waiting_text)
async def handle_new_schedule_text(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Додавання запланованого поста скасовано.")
        await state.clear()
        return

    text = message.text or message.caption or ""

    if not text:
        await message.answer("❌ Текст не може бути порожнім. Спробуйте ще раз:")
        return

    media_file = None
    media_type = None

    if message.photo:
        media_type = "photo"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.photo[-1],
            destination=media_file
        )
    elif message.video:
        if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.video,
            destination=media_file
        )
    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
        if message.document.file_size and message.document.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.document.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        file_name = message.document.file_name or "video.mp4"
        if '.' in file_name:
            ext = '.' + file_name.split('.')[-1]
        else:
            ext = '.mp4'

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.document,
            destination=media_file
        )

    await state.update_data(
        schedule_text=text,
        schedule_media_file=media_file,
        schedule_media_type=media_type
    )

    await message.answer(
        "⏰ <b>Запланувати пост</b>\n\n"
        "Введіть дату для публікації у форматі <b>DD.MM.YYYY</b>\n"
        "Наприклад: <code>01.01.2026</code>\n\n"
        "Щоб скасувати, напишіть /cancel",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(NewScheduledPostStates.waiting_date)


@dp.message(NewScheduledPostStates.waiting_date)
async def handle_new_schedule_date(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Запланування скасовано.")
        data = await state.get_data()
        media_file = data.get("schedule_media_file")
        if media_file and os.path.exists(media_file):
            os.remove(media_file)
        await state.clear()
        return

    date_text = message.text.strip()

    date_pattern = r'^\d{2}\.\d{2}\.\d{4}$'
    if not re.match(date_pattern, date_text):
        await message.answer(
            "❌ Неправильний формат дати!\n\n"
            "Введіть дату у форматі <b>DD.MM.YYYY</b>\n"
            "Наприклад: <code>01.01.2026</code>\n\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        day, month, year = map(int, date_text.split('.'))
        date_obj = datetime(year, month, day)

        if date_obj.date() < datetime.now().date():
            await message.answer(
                "❌ Дата не може бути в минулому!\n\n"
                "Введіть майбутню дату:",
                parse_mode=ParseMode.HTML
            )
            return

        await state.update_data(schedule_date=date_text, schedule_date_obj=date_obj)

        await message.answer(
            "⏰ <b>Запланувати пост</b>\n\n"
            "Введіть час для публікації у форматі <b>HH:MM</b>\n"
            "Наприклад: <code>08:00</code>\n\n"
            "Щоб скасувати, напишіть /cancel",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(NewScheduledPostStates.waiting_time)

    except ValueError:
        await message.answer(
            "❌ Неправильна дата!\n\n"
            "Перевірте, чи існує така дата (наприклад, 30.02 - неправильна).\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )


@dp.message(NewScheduledPostStates.waiting_time)
async def handle_new_schedule_time(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Запланування скасовано.")
        data = await state.get_data()
        media_file = data.get("schedule_media_file")
        if media_file and os.path.exists(media_file):
            os.remove(media_file)
        await state.clear()
        return

    time_text = message.text.strip()

    time_pattern = r'^\d{2}:\d{2}$'
    if not re.match(time_pattern, time_text):
        await message.answer(
            "❌ Неправильний формат часу!\n\n"
            "Введіть час у форматі <b>HH:MM</b>\n"
            "Наприклад: <code>08:00</code>\n\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        hours, minutes = map(int, time_text.split(':'))

        if not (0 <= hours < 24) or not (0 <= minutes < 60):
            raise ValueError

        data = await state.get_data()
        date_obj = data.get("schedule_date_obj")
        text = data.get("schedule_text", "")
        media_file = data.get("schedule_media_file")
        media_type = data.get("schedule_media_type")

        if not date_obj:
            await message.answer("❌ Помилка: дані втрачено. Спробуйте ще раз.")
            await state.clear()
            return

        scheduled_time = datetime(
            date_obj.year, date_obj.month, date_obj.day,
            hours, minutes
        )

        if scheduled_time <= datetime.now():
            await message.answer(
                "❌ Час не може бути в минулому!\n\n"
                "Введіть майбутній час:",
                parse_mode=ParseMode.HTML
            )
            return

        scheduled_posts = load_scheduled_posts()
        scheduled_post_id = int(datetime.now().timestamp() * 1000)

        media_path = None
        if media_file and os.path.exists(media_file):
            ext = os.path.splitext(media_file)[1]
            media_path = os.path.join(tempfile.gettempdir(), f"scheduled_{scheduled_post_id}{ext}")
            shutil.copy2(media_file, media_path)
            os.remove(media_file)

        final_text = text + f"\n\n<b>{TARGET_CHANNEL_TITLE}</b>"

        scheduled_posts[str(scheduled_post_id)] = {
            "text": final_text,
            "media_path": media_path,
            "media_type": media_type,
            "scheduled_time": scheduled_time,
            "original_scheduled_time": f"{data.get('schedule_date')} {time_text}",
            "created_at": datetime.now().isoformat(),
            "source": "admin_created"
        }

        save_scheduled_posts(scheduled_posts)

        formatted_time = scheduled_time.strftime("%d.%m.%Y %H:%M")
        await message.answer(
            f"✅ <b>Новий запланований пост створено!</b>\n\n"
            f"📅 <b>Дата публікації:</b> {formatted_time}\n"
            f"🏷 <b>ID запланованого поста:</b> {scheduled_post_id}\n\n"
            f"Пост буде автоматично опубліковано у вказаний час.",
            parse_mode=ParseMode.HTML
        )

        preview_text = f"⏰ <b>Новий запланований пост</b> (ID: {scheduled_post_id})\n\n"
        preview_text += f"📅 <b>Заплановано на:</b> {formatted_time}\n\n"

        if len(final_text) > 500:
            preview_text += f"{final_text[:500]}..."
        else:
            preview_text += final_text

        await message.answer(preview_text, parse_mode=ParseMode.HTML)

        logger.info(f"⏰ Створено новий запланований пост ID: {scheduled_post_id} на {formatted_time}")

    except ValueError:
        await message.answer(
            "❌ Неправильний час!\n\n"
            "Години повинні бути від 00 до 23, хвилини від 00 до 59.\n"
            "Спробуйте ще раз:",
            parse_mode=ParseMode.HTML
        )

    await state.clear()


# ================== TELETHON АВТОРИЗАЦІЯ ЧЕРЕЗ БОТА ==================
@dp.message(F.text == "🔐 Налаштування Telethon")
async def handle_telethon_setup(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    await message.answer(
        "🔐 <b>Налаштування Telethon</b>\n\n"
        "Telethon потрібен для моніторингу каналів новин.\n"
        "Оберіть дію з меню нижче:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_telethon_setup_keyboard()
    )


@dp.message(F.text == "📱 Ввести номер телефону")
async def handle_enter_phone(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    await message.answer(
        "📱 <b>Введення номера телефону</b>\n\n"
        "Введіть ваш номер телефону в міжнародному форматі:\n"
        "Наприклад: <code>+380123456789</code>\n\n"
        "Цей номер буде використано для авторизації Telethon.\n\n"
        "Щоб скасувати, напишіть /cancel",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(TelegramLoginStates.waiting_phone)


@dp.message(TelegramLoginStates.waiting_phone)
async def handle_phone_input(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Введення номера скасовано.")
        await state.clear()
        return

    phone = message.text.strip()
    
    # Проста перевірка формату номера
    if not phone.startswith('+'):
        await message.answer(
            "❌ Невірний формат номера!\n\n"
            "Номер повинен починатися з '+' та містити код країни.\n"
            "Наприклад: <code>+380123456789</code>\n\n"
            "Введіть номер ще раз:",
            parse_mode=ParseMode.HTML
        )
        return
    
    await state.update_data(phone=phone)
    
    success, result_message = await send_code_request(phone)
    
    if success:
        await message.answer(
            f"{result_message}\n\n"
            "Тепер введіть код, який ви отримали в Telegram:",
            parse_mode=ParseMode.HTML
        )
        await state.set_state(TelegramLoginStates.waiting_code)
    else:
        await message.answer(
            f"{result_message}\n\n"
            "Спробуйте ще раз або перевірте номер телефону.",
            parse_mode=ParseMode.HTML
        )
        await state.clear()


@dp.message(TelegramLoginStates.waiting_code)
async def handle_code_input(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Введення коду скасовано.")
        await state.clear()
        return

    code = message.text.strip()
    
    # Видаляємо всі нецифрові символи
    code = ''.join(filter(str.isdigit, code))
    
    if not code or len(code) < 4:
        await message.answer(
            "❌ Код повинен містити щонайменше 4 цифри!\n\n"
            "Введіть код ще раз:",
            parse_mode=ParseMode.HTML
        )
        return
    
    success, result_message = await sign_in_with_code(code)
    
    if success:
        await message.answer(
            f"{result_message}\n\n"
            "Тепер можете запустити моніторинг каналів.",
            parse_mode=ParseMode.HTML
        )
        
        # Запускаємо моніторинг
        await start_telethon_monitoring()
    else:
        if "password" in result_message.lower():
            await message.answer(
                "🔐 <b>Потрібен пароль двофакторної аутентифікації</b>\n\n"
                "Введіть ваш пароль 2FA:",
                parse_mode=ParseMode.HTML
            )
            await state.set_state(TelegramLoginStates.waiting_password)
        else:
            await message.answer(
                f"{result_message}\n\n"
                "Спробуйте ще раз:",
                parse_mode=ParseMode.HTML
            )
    
    await state.clear()


@dp.message(TelegramLoginStates.waiting_password)
async def handle_password_input(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Введення паролю скасовано.")
        await state.clear()
        return

    password = message.text.strip()
    
    success, result_message = await sign_in_with_password(password)
    
    if success:
        await message.answer(
            f"{result_message}\n\n"
            "Тепер можете запустити моніторинг каналів.",
            parse_mode=ParseMode.HTML
        )
        
        # Запускаємо моніторинг
        await start_telethon_monitoring()
    else:
        await message.answer(
            f"{result_message}\n\n"
            "Спробуйте ще раз або перезапустіть процес авторизації.",
            parse_mode=ParseMode.HTML
        )
    
    await state.clear()


@dp.message(F.text == "🔢 Ввести код з Telegram")
async def handle_enter_code_directly(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    await message.answer(
        "🔢 <b>Введення коду з Telegram</b>\n\n"
        "Введіть код, який ви отримали в Telegram:\n\n"
        "Щоб скасувати, напишіть /cancel",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(TelegramLoginStates.waiting_code)


@dp.message(F.text == "✅ Перевірити статус Telethon")
async def handle_check_telethon_status(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return
    
    status = await check_telethon_status()
    await message.answer(
        f"📊 <b>Статус Telethon:</b>\n\n{status}",
        parse_mode=ParseMode.HTML
    )


@dp.message(F.text == "🔙 Назад в адмін-панель")
async def handle_back_to_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    await handle_admin_panel(message)


# ================== ОБРОБКА ПОВІДОМЛЕНЬ З ПАНЕЛІ МЕНЮ ==================
@dp.message(F.text == "📤 Поділитися інформацією")
async def handle_share_info(message: Message, state: FSMContext):
    await message.answer(
        "📤 <b>Поділитися інформацією</b>\n\n"
        "Надішліть вашу інформацію (текст, фото, відео з описом), я передам адміну для перевірки та публікації.\n\n"
        "❗️ Надсилаючи матеріали, ви підтверджуєте згоду на їх публікацію в нашому Telegram-каналі. (Самбірчанин | Новини.)\n\n"
        "Щоб відмінити, напишіть /menu",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(ShareStates.waiting_info)


@dp.message(F.text == "📢 Розмістити рекламу")
async def handle_advertise(message: Message, state: FSMContext):
    await message.answer(
        "📢 <b>Розмістити рекламу</b>\n\n"
        "Опишіть коротко, що ви хочете прорекламувати в нашому каналі.\n\n"
        "Обв'язково, залиште ваші контактні дані (наприклад Telegram), щоб ми могли з вами зв'язатися.\n\n"
        "Щоб відмінити, напишіть /menu",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(ShareStates.waiting_ad)


@dp.message(F.text == "👑 Адмін-панель")
async def handle_admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до адмін-панелі.")
        return

    await message.answer(
        "👑 <b>Адмін-панель</b>\n\n"
        "Оберіть дію з меню нижче:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_admin_panel_keyboard()
    )


@dp.message(F.text == "📋 Очікуючі пости")
async def handle_pending_posts(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    if not pending_posts:
        await message.answer("📭 Немає постів, які очікують на модерацію.")
    else:
        count = len(pending_posts)
        media_stats = {"photo": 0, "video": 0, "text_only": 0}
        category_stats = {"power": 0, "sambir": 0}

        for post in pending_posts.values():
            if post.get("media_type") == "photo":
                media_stats["photo"] += 1
            elif post.get("media_type") == "video":
                media_stats["video"] += 1
            else:
                media_stats["text_only"] += 1

            if post.get("is_power"):
                category_stats["power"] += 1
            if post.get("is_sambir"):
                category_stats["sambir"] += 1

        stats_text = f"📋 <b>Постів в очікуванні:</b> {count}\n\n"
        stats_text += f"<b>Категорії:</b>\n"
        stats_text += f"  ⚡ Відключення світла: {category_stats['power']}\n"
        stats_text += f"  📍 Самбірські новини: {category_stats['sambir']}\n\n"

        stats_text += f"<b>Типи медіа:</b>\n"
        stats_text += f"  📷 Фото: {media_stats['photo']}\n"
        stats_text += f"  🎬 Відео: {media_stats['video']}\n"
        stats_text += f"  📝 Текст: {media_stats['text_only']}\n\n"

        sources = {}
        for post in pending_posts.values():
            source = post.get("source", "Невідомо")
            sources[source] = sources.get(source, 0) + 1

        if sources:
            stats_text += "<b>Джерела:</b>\n"
            for source, count in sources.items():
                source_name = SOURCE_NAMES.get(source, source)
                stats_text += f"  • {source_name}: {count}\n"

        await message.answer(stats_text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "📊 Статистика")
async def handle_admin_stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    alert_state = load_alert_state()
    scheduled_posts = load_scheduled_posts()

    stats_text = "📊 <b>Статистика:</b>\n\n"
    stats_text += f"📝 <b>Постів в очікуванні:</b> {len(pending_posts)}\n"
    stats_text += f"⏰ <b>Запланованих постів:</b> {len(scheduled_posts)}\n"

    media_stats = {"photo": 0, "video": 0, "text_only": 0}
    category_stats = {"power": 0, "sambir": 0}

    for post in pending_posts.values():
        if post.get("media_type") == "photo":
            media_stats["photo"] += 1
        elif post.get("media_type") == "video":
            media_stats["video"] += 1
        else:
            media_stats["text_only"] += 1

        if post.get("is_power"):
            category_stats["power"] += 1
        if post.get("is_sambir"):
            category_stats["sambir"] += 1

    stats_text += f"\n<b>Категорії:</b>\n"
    stats_text += f"  ⚡ Відключення світла: {category_stats['power']}\n"
    stats_text += f"  📍 Самбірські новини: {category_stats['sambir']}\n\n"

    stats_text += f"<b>Типи медіа:</b>\n"
    stats_text += f"  📷 Фото: {media_stats['photo']}\n"
    stats_text += f"  🎬 Відео: {media_stats['video']}\n"
    stats_text += f"  📝 Текст: {media_stats['text_only']}\n\n"

    stats_text += f"🚨 <b>Тривога активна (API):</b> {'Так' if alert_state['active'] else 'Ні'}\n"
    if alert_state['active'] and alert_state['start_time']:
        start = datetime.fromisoformat(alert_state["start_time"])
        seconds = int((datetime.now() - start).total_seconds())
        duration = format_duration(seconds)
        stats_text += f"⏱ <b>Тривалість тривоги:</b> {duration}\n"

    stats_text += f"\n🔍 <b>Джерело тривог:</b> API alerts.in.ua"

    await message.answer(stats_text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "⏰ Заплановані пости")
async def handle_scheduled_posts_menu(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    await message.answer(
        "⏰ <b>Заплановані пости</b>\n\n"
        "Оберіть дію з меню нижче:",
        parse_mode=ParseMode.HTML,
        reply_markup=get_scheduled_posts_keyboard()
    )


@dp.message(F.text == "📋 Список запланованих постів")
async def handle_scheduled_posts_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    scheduled_posts = load_scheduled_posts()

    if not scheduled_posts:
        await message.answer("📭 Немає запланованих постів.")
        return

    sorted_posts = sorted(
        scheduled_posts.items(),
        key=lambda x: x[1].get("scheduled_time", datetime.now())
    )

    now = datetime.now()

    for i in range(0, len(sorted_posts), 5):
        batch = sorted_posts[i:i + 5]
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

        await message.answer(response_text, parse_mode=ParseMode.HTML)

    stats_text = f"\n📊 <b>Загальна статистика:</b>\n"
    stats_text += f"• Всього заплановано: {len(scheduled_posts)} постів\n"

    upcoming = sum(1 for post in scheduled_posts.values()
                   if isinstance(post.get("scheduled_time"), datetime) and post["scheduled_time"] > now)
    stats_text += f"• Очікують публікації: {upcoming} постів\n"

    overdue = len(scheduled_posts) - upcoming
    if overdue > 0:
        stats_text += f"• Час настав: {overdue} постів\n"

    await message.answer(stats_text, parse_mode=ParseMode.HTML)


@dp.message(F.text == "🗑 Видалити запланований пост")
async def handle_delete_scheduled_post(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї функції.")
        return

    scheduled_posts = load_scheduled_posts()

    if not scheduled_posts:
        await message.answer("📭 Немає запланованих постів для видалення.")
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[])

    for post_id, post in list(scheduled_posts.items())[:10]:
        scheduled_time = post.get("scheduled_time")
        if isinstance(scheduled_time, str):
            scheduled_time = datetime.fromisoformat(scheduled_time)

        time_str = scheduled_time.strftime("%d.%m %H:%M")
        button_text = f"🗑 {post_id} ({time_str})"

        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text=button_text, callback_data=f"schedule_delete:{post_id}")
        ])

    await message.answer(
        "🗑 <b>Видалити запланований пост</b>\n\n"
        "Оберіть пост для видалення:",
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard
    )


@dp.message(F.text == "🔙 Головне меню")
async def handle_back_to_menu(message: Message):
    await show_main_menu(message)


# ================== ОТРИМАННЯ ПОВІДОМЛЕНЬ ВІД КОРИСТУВАЧА В СТАНАХ ==================
@dp.message(ShareStates.waiting_info)
async def receive_info(message: Message, state: FSMContext):
    if message.text and message.text == "/menu":
        await message.answer("📤 Поділення інформації скасовано.")
        await show_main_menu(message)
        await state.clear()
        return

    text = message.text or message.caption or ""
    media_file = None
    media_type = None

    if message.photo:
        media_type = "photo"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.photo[-1],
            destination=media_file
        )

    elif message.video:
        if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.video,
            destination=media_file
        )

    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
        if message.document.file_size and message.document.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.document.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        file_name = message.document.file_name or "video.mp4"
        if '.' in file_name:
            ext = '.' + file_name.split('.')[-1]
        else:
            ext = '.mp4'

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.document,
            destination=media_file
        )

    post_id = message.message_id
    pending_posts[post_id] = {"text": text, "media": media_file, "media_type": media_type}

    username = message.from_user.username or message.from_user.full_name
    user_info = f"👤 Від: @{username} (ID: {message.from_user.id})"

    escaped_text = escape_html(text) if text else '📁 Медіа без тексту'
    caption_text = f"{user_info}\n\n📤 Інформація:\n{escaped_text}"

    if media_type:
        caption_text += f"\n\n📁 Тип: {media_type.upper()}"

    if media_file:
        if os.path.exists(media_file) and os.path.getsize(media_file) > 0:
            if media_type == "photo":
                sent_message = await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=caption_text,
                    reply_markup=moderation_keyboard(post_id)
                )
            elif media_type == "video":
                sent_message = await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=caption_text,
                    reply_markup=moderation_keyboard(post_id)
                )

            if sent_message:
                pending_posts[post_id]["admin_message_id"] = sent_message.message_id
        else:
            sent_message = await bot.send_message(
                ADMIN_ID,
                f"{caption_text}\n\n⚠️ Медіа не вдалося завантажити",
                reply_markup=moderation_keyboard(post_id)
            )
            if sent_message:
                pending_posts[post_id]["admin_message_id"] = sent_message.message_id
    else:
        sent_message = await bot.send_message(
            ADMIN_ID,
            caption_text,
            reply_markup=moderation_keyboard(post_id)
        )
        if sent_message:
            pending_posts[post_id]["admin_message_id"] = sent_message.message_id

    await message.answer(
        "✅ Ваша інформація надіслана адміну для перевірки. Дякуємо!\n\n"
        "Меню знову доступне:",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )
    await state.clear()


@dp.message(ShareStates.waiting_ad)
async def receive_ad(message: Message, state: FSMContext):
    if message.text and message.text == "/menu":
        await message.answer("📢 Розміщення реклами скасовано.")
        await show_main_menu(message)
        await state.clear()
        return

    text = message.text or message.caption or ""
    media_file = None
    media_type = None

    if message.photo:
        media_type = "photo"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.photo[-1],
            destination=media_file
        )

    elif message.video:
        if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.video,
            destination=media_file
        )

    username = message.from_user.username or message.from_user.full_name
    user_info = f"👤 Від: @{username} (ID: {message.from_user.id})"

    escaped_text = escape_html(text) if text else "📁 Медіа без тексту"

    admin_message = f"📢 Реклама:\n{user_info}\n\n{escaped_text}"

    if media_type:
        admin_message += f"\n\n📁 Тип медіа: {media_type.upper()}"

    if media_file:
        if os.path.exists(media_file) and os.path.getsize(media_file) > 0:
            if media_type == "photo":
                await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=admin_message
                )
            elif media_type == "video":
                await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=admin_message
                )
            os.remove(media_file)
        else:
            await bot.send_message(
                ADMIN_ID,
                f"{admin_message}\n\n⚠️ Медіа не вдалося завантажити"
            )
    else:
        await bot.send_message(
            ADMIN_ID,
            admin_message
        )

    await message.answer(
        "✅ Ваша заявка на рекламу прийнята!\n\n"
        "Адмін розгляне ваше повідомлення і зв'яжеться з вами в найближчий час.\n\n"
        "Будь ласка, не видаляйте і не блокуйте бота поки з вами не зв'яжиться адмін.\n\n"
        "Дякуємо, що обрали наш канал!\n\n"
        "Меню знову доступне:",
        reply_markup=get_main_menu_keyboard(message.from_user.id)
    )

    await state.clear()


# ================== ФУНКЦІЯ ДЛЯ ПОКАЗУ ГОЛОВНОГО МЕНЮ ==================
async def show_main_menu(message: Message):
    welcome_text = (
        "🏠 <b>Головне меню</b>\n\n"
        "Оберіть одну з опцій:\n\n"
        "• 📤 <b>Поділитися інформацією</b> - надіслати новину чи інформацію для публікації\n"
        "• 📢 <b>Розмістити рекламу</b> - залишити заявку на розміщення реклами\n"
    )

    await message.answer(
        welcome_text,
        reply_markup=get_main_menu_keyboard(message.from_user.id),
        parse_mode=ParseMode.HTML
    )


# ================== ОБРОБКА РЕДАГУВАННЯ ТЕКСТУ ==================
@dp.message(EditStates.waiting_edit_text)
async def handle_edit_text(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Редагування тексту скасовано.")
        await state.clear()
        return

    data = await state.get_data()
    pid = data.get("edit_post_id")
    edit_message_id = data.get("edit_message_id")

    if pid not in pending_posts:
        await message.answer("⚠️ Пост не знайдено. Редагування скасовано.")
        await state.clear()
        return

    pending_posts[pid]["text"] = message.text or message.caption or ""

    item = pending_posts[pid]
    preview_type = "⚡ Відключення світла / графіки" if item.get("is_power") else "📍 Новина з Самбірщини"

    if item.get("source") in SOURCE_NAMES:
        preview_type += f" | {SOURCE_NAMES[item.get('source')]}"

    full_text = item["text"]
    lines = full_text.split('\n')
    main_text_lines = []
    for line in lines:
        if not (line.startswith('📰 <b>Джерело:') or line.startswith(f'<b>{TARGET_CHANNEL_TITLE}</b>')):
            main_text_lines.append(line)
    cleaned_text = '\n'.join(main_text_lines).strip()

    preview = f"{preview_type}\n\n{cleaned_text}" if cleaned_text else preview_type

    try:
        if item["media"] and os.path.exists(item["media"]):
            if item["media_type"] == "photo":
                await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)
                sent_message = await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(item["media"]),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )
            elif item["media_type"] == "video":
                await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)
                sent_message = await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(item["media"]),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )

            if sent_message:
                pending_posts[pid]["admin_message_id"] = sent_message.message_id
        else:
            await bot.edit_message_caption(
                chat_id=ADMIN_ID,
                message_id=edit_message_id,
                caption=preview,
                reply_markup=moderation_keyboard(pid)
            )

        await message.answer("✅ Текст успішно оновлено!")

    except Exception as e:
        await message.answer(f"❌ Помилка при оновленні: {str(e)}")

    await state.clear()


# ================== ОБРОБКА РЕДАГУВАННЯ МЕДІА ==================
@dp.message(EditStates.waiting_edit_media)
async def handle_edit_media(message: Message, state: FSMContext):
    if message.text and message.text == "/cancel":
        await message.answer("❌ Редагування медіа скасовано.")
        await state.clear()
        return

    data = await state.get_data()
    pid = data.get("edit_post_id")
    edit_message_id = data.get("edit_message_id")

    if pid not in pending_posts:
        await message.answer("⚠️ Пост не знайдено. Редагування скасовано.")
        await state.clear()
        return

    item = pending_posts[pid]
    old_media = item.get("media")

    if message.text and message.text.lower() == "видалити":
        if old_media and os.path.exists(old_media):
            os.remove(old_media)

        item["media"] = None
        item["media_type"] = None

        preview_type = "⚡ Відключення світла / графіки" if item.get("is_power") else "📍 Новина з Самбірщини"
        if item.get("source") in SOURCE_NAMES:
            preview_type += f" | {SOURCE_NAMES[item.get('source')]}"

        full_text = item["text"]
        lines = full_text.split('\n')
        main_text_lines = []
        for line in lines:
            if not (line.startswith('📰 <b>Джерело:') or line.startswith(f'<b>{TARGET_CHANNEL_TITLE}</b>')):
                main_text_lines.append(line)
        cleaned_text = '\n'.join(main_text_lines).strip()

        preview = f"{preview_type}\n\n{cleaned_text}" if cleaned_text else preview_type

        try:
            await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)
            sent_message = await bot.send_message(
                ADMIN_ID,
                preview,
                reply_markup=moderation_keyboard(pid)
            )

            if sent_message:
                pending_posts[pid]["admin_message_id"] = sent_message.message_id

            await message.answer("✅ Медіа успішно видалено!")

        except Exception as e:
            await message.answer(f"❌ Помилка при видаленні медіа: {str(e)}")

        await state.clear()
        return

    media_file = None
    media_type = None

    if message.photo:
        media_type = "photo"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.photo[-1],
            destination=media_file
        )

    elif message.video:
        if message.video.file_size and message.video.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.video.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp4')
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.video,
            destination=media_file
        )

    elif message.document and message.document.mime_type and 'video' in message.document.mime_type:
        if message.document.file_size and message.document.file_size > MAX_VIDEO_SIZE:
            await message.answer(
                f"❌ Відео занадто велике ({message.document.file_size // (1024 * 1024)} МБ). "
                f"Максимальний розмір: {MAX_VIDEO_SIZE // (1024 * 1024)} МБ.\n"
                "Спробуйте стиснути відео або надіслати посилання на нього."
            )
            return

        media_type = "video"
        file_name = message.document.file_name or "video.mp4"
        if '.' in file_name:
            ext = '.' + file_name.split('.')[-1]
        else:
            ext = '.mp4'

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        temp_file.close()
        media_file = temp_file.name

        await message.bot.download(
            message.document,
            destination=media_file
        )

    else:
        await message.answer("❌ Будь ласка, надішліть фото або відео. Для видалення медіа напишіть 'видалити'.")
        return

    if old_media and os.path.exists(old_media):
        os.remove(old_media)

    item["media"] = media_file
    item["media_type"] = media_type

    preview_type = "⚡ Відключення світла / графіки" if item.get("is_power") else "📍 Новина з Самбірщини"
    if item.get("source") in SOURCE_NAMES:
        preview_type += f" | {SOURCE_NAMES[item.get('source')]}"

    full_text = item["text"]
    lines = full_text.split('\n')
    main_text_lines = []
    for line in lines:
        if not (line.startswith('📰 <b>Джерело:') or line.startswith(f'<b>{TARGET_CHANNEL_TITLE}</b>')):
            main_text_lines.append(line)
    cleaned_text = '\n'.join(main_text_lines).strip()

    preview = f"{preview_type}\n\n{cleaned_text}" if cleaned_text else preview_type

    try:
        await bot.delete_message(chat_id=ADMIN_ID, message_id=edit_message_id)

        if media_file and os.path.exists(media_file) and os.path.getsize(media_file) > 0:
            if media_type == "photo":
                sent_message = await bot.send_photo(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )
            elif media_type == "video":
                sent_message = await bot.send_video(
                    ADMIN_ID,
                    FSInputFile(media_file),
                    caption=preview,
                    reply_markup=moderation_keyboard(pid)
                )
        else:
            sent_message = await bot.send_message(
                ADMIN_ID,
                f"{preview}\n\n⚠️ Медіа не вдалося завантажити",
                reply_markup=moderation_keyboard(pid)
            )

        if sent_message:
            pending_posts[pid]["admin_message_id"] = sent_message.message_id

        await message.answer("✅ Медіа успішно оновлено!")

    except Exception as e:
        await message.answer(f"❌ Помилка при оновленні медіа: {str(e)}")
        if media_file and os.path.exists(media_file):
            os.remove(media_file)

    await state.clear()


# ================== КОМАНДИ ==================
@dp.message(CommandStart())
async def start_handler(message: Message):
    await show_main_menu(message)


@dp.message(Command("menu"))
async def menu_handler(message: Message):
    await show_main_menu(message)


@dp.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("ℹ️ Немає активної операції для скасування.")
        return

    if current_state.startswith("EditStates"):
        await message.answer("❌ Редагування скасовано.")
    elif current_state.startswith("ShareStates"):
        await message.answer("❌ Операція скасована.")
    elif current_state.startswith("ScheduledPostStates"):
        await message.answer("❌ Запланування скасовано.")
    elif current_state.startswith("NewScheduledPostStates"):
        await message.answer("❌ Створення поста скасовано.")
    elif current_state.startswith("TelegramLoginStates"):
        await message.answer("❌ Авторизацію скасовано.")

    await state.clear()
    await show_main_menu(message)


@dp.message(Command("status"))
async def status_handler(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас немає доступу до цієї команди.")
        return
    
    # Статус Telethon
    telethon_status = await check_telethon_status()
    
    # Статус бота
    bot_status = "✅ Aiogram бот активний"
    try:
        me = await bot.get_me()
        bot_status = f"✅ Aiogram бот активний (@{me.username})"
    except Exception as e:
        bot_status = f"❌ Помилка бота: {str(e)}"
    
    # Статистика
    alert_state = load_alert_state()
    scheduled_posts = load_scheduled_posts()
    
    status_text = f"📊 <b>Статус системи:</b>\n\n"
    status_text += f"🤖 <b>Бот:</b> {bot_status}\n"
    status_text += f"📡 <b>Telethon:</b> {telethon_status}\n"
    status_text += f"📝 <b>Постів в очікуванні:</b> {len(pending_posts)}\n"
    status_text += f"⏰ <b>Запланованих постів:</b> {len(scheduled_posts)}\n"
    status_text += f"🚨 <b>Тривога активна:</b> {'Так' if alert_state['active'] else 'Ні'}\n"
    
    await message.answer(status_text, parse_mode=ParseMode.HTML)


# ================== ОБРОБКА ІНШИХ ПОВІДОМЛЕНЬ ==================
@dp.message()
async def handle_other_messages(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if not current_state:
        if message.text and message.text.startswith("/"):
            await message.answer("ℹ️ Невідома команда. Використовуйте /menu для відкриття меню.")
        else:
            await show_main_menu(message)


# ================== ЗАПУСК ==================
async def main():
    logger.info("=" * 50)
    logger.info("🚀 Запуск бота...")
    logger.info(f"🤖 Aiogram бот: {BOT_TOKEN[:10]}...")
    logger.info(f"📡 Telethon API ID: {API_ID}")
    logger.info(f"🎯 Цільовий канал: {TARGET_CHANNEL}")
    logger.info(f"📱 Джерела новин: {len(SOURCE_CHANNELS)} каналів")
    logger.info("=" * 50)

    try:
        # Перевірка підключення бота
        me = await bot.get_me()
        logger.info(f"✅ Aiogram бот підключений: @{me.username}")

        # Ініціалізація Telethon
        logger.info("🔄 Ініціалізація Telethon...")
        await setup_telegram_client()
        
        # Запуск фонових задач
        logger.info("🔄 Запуск фонових задач...")
        asyncio.create_task(alerts_monitoring_task())
        asyncio.create_task(scheduled_posts_monitoring_task())
        
        # Запуск моніторингу Telethon (якщо авторизовано)
        if telegram_client and client_authorized:
            await start_telethon_monitoring()
        
        logger.info("✅ Всі системи запущено")
        logger.info("🔄 Очікування повідомлень...")
        
        # Запуск polling
        await dp.start_polling(bot, skip_updates=True)
        
    except Exception as e:
        logger.error(f"❌ Критична помилка при запуску: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if telegram_client:
            await telegram_client.disconnect()
            logger.info("✅ Telethon клієнт відключено")
        logger.info("✅ Бот зупинено")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("✅ Бот зупинено користувачем")
    except Exception as e:
        logger.error(f"❌ Несподівана помилка: {e}")
        import traceback
        traceback.print_exc()
