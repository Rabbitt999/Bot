import telebot

# Замените 'ВАШ_ТОКЕН' на токен, полученный от BotFather
TOKEN = '8067473611:AAHaIRuXuCF_SCkiGkg-gfHf2zKPOkT_V9g'
bot = telebot.TeleBot(TOKEN)

# Обработчик команды /start
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Привет! Я простой телеграм-бот. Что я могу для тебя сделать?")

# Обработчик текстовых сообщений
@bot.message_handler(func=lambda message: True)
def echo_all(message):
    bot.reply_to(message, f"Ты написал: {message.text}")

# Запуск бота
if __name__ == '__main__':
    print("Бот запущен...")
    bot.polling(none_stop=True) # Запускает бота в режиме "Long Poll"
