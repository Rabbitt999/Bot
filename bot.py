import telebot

TOKEN = "8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g"

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "👋 Привіт! Я простий Telegram-бот без aiogram."
    )

@bot.message_handler(func=lambda message: True)
def echo(message):
    bot.send_message(
        message.chat.id,
        f"Ти написав: {message.text}"
    )

print("🤖 Бот запущений...")
bot.polling(none_stop=True)
