import telebot

TOKEN = "8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g"

bot = telebot.TeleBot(TOKEN)

bot.remove_webhook()  # ← ОСЬ ЦЕ ГОЛОВНЕ ВИПРАВЛЕННЯ

@bot.message_handler(commands=['start'])
def start(message):
    print("START отримано")
    bot.send_message(
        message.chat.id,
        "👋 Привіт! Бот працює ✅"
    )

@bot.message_handler(func=lambda message: True)
def echo(message):
    print("Повідомлення:", message.text)
    bot.send_message(
        message.chat.id,
        f"Ти написав: {message.text}"
    )

print("🤖 Бот запущений...")
bot.polling(none_stop=True)
