import asyncio
import logging
import os
import json
from urllib.parse import urljoin

import aiohttp
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler
from playwright.async_api import async_playwright

BOT_TOKEN = "8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g"  # встав свій токен
CHAT_ID = 6974875043
CHECK_INTERVAL = 60  # оновлення кожні 60 секунд
URL = "https://poweron.loe.lviv.ua/"
UPDATE_FILE = "sent_graphs.json"
LAST_IMAGE_FILE = "last_graph.png"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


async def get_all_graphs(page):
    """Повертає список всіх графіків (підпис + URL) на сторінці"""
    await page.wait_for_selector("text=Інформація станом", timeout=30000)

    texts = await page.locator("text=Інформація станом").all_text_contents()
    images = await page.locator("img").all()

    graphs = []

    img_index = 0
    for text in texts:
        # шукаємо наступне зображення, яке ймовірно графік
        while img_index < len(images):
            src = await images[img_index].get_attribute("src")
            img_index += 1
            if src and ("grafik" in src.lower() or src.lower().endswith(".png")):
                url = urljoin(URL, src)
                graphs.append({"text": text.strip(), "url": url})
                break
    return graphs


def load_sent_graphs():
    if os.path.exists(UPDATE_FILE):
        with open(UPDATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_sent_graphs(sent_list):
    with open(UPDATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_list, f, ensure_ascii=False, indent=2)


async def download_image(url, path):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                with open(path, "wb") as f:
                    f.write(await resp.read())
                return True
            else:
                logging.error(f"❌ Не вдалося завантажити зображення. Status: {resp.status}")
    return False


async def check_loop(bot: Bot):
    logging.info("▶️ Моніторинг графіків запущено")
    while True:
        try:
            sent_graphs = load_sent_graphs()

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)

                iphone_ua = (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
                )
                page = await browser.new_page(user_agent=iphone_ua, viewport={"width": 375, "height": 812})
                await page.goto(URL, wait_until="load", timeout=60000)

                graphs = await get_all_graphs(page)
                await browser.close()

            for graph in graphs:
                identifier = graph["url"]  # унікальний ключ по URL
                if identifier not in sent_graphs:
                    logging.info(f"🆕 Надсилаємо новий графік: {graph['text']}")
                    success = await download_image(graph["url"], LAST_IMAGE_FILE)
                    if success:
                        caption = f"⚡ ОНОВЛЕННЯ ГРАФІКА\n{graph['text']}"
                        with open(LAST_IMAGE_FILE, "rb") as photo:
                            await bot.send_photo(chat_id=CHAT_ID, photo=photo, caption=caption)
                        sent_graphs.append(identifier)

            save_sent_graphs(sent_graphs)

        except Exception as e:
            logging.error(f"❌ Помилка: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


# ================== КОМАНДИ ==================

async def start(update: Update, context):
    keyboard = [[InlineKeyboardButton("📊 Отримати останній графік", callback_data="send_last_graph")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Привіт! Я моніторю графіки відключень.\nНатисни кнопку, щоб отримати останній:",
        reply_markup=reply_markup
    )


async def button_handler(update: Update, context):
    query = update.callback_query
    await query.answer()
    if query.data == "send_last_graph":
        if os.path.exists(LAST_IMAGE_FILE):
            with open(LAST_IMAGE_FILE, "rb") as photo:
                await query.message.reply_photo(photo=photo, caption="📊 Останній графік відключень")
        else:
            await query.message.reply_text("❌ Графік ще не завантажено. Спробуй пізніше.")


# ================== СТАРТ ==================

async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    bot = app.bot
    asyncio.create_task(check_loop(bot))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CallbackQueryHandler(button_handler))
    logging.info("🤖 Бот запущений")
    await app.initialize()
    await app.start()
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
