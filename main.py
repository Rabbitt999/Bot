import telebot
import json
import random
import os
import re
import time
import requests
from telebot import types
from datetime import datetime, timedelta, timezone

# Конфігурація бота
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '7991439480:AAGR8KyC3RnBEVlYpP8-39ExcI-SSAhmPC0')
bot = telebot.TeleBot(TOKEN)

ADMIN_ID = 6974875043
CHANNEL_USERNAME = 'CodeMovie1'
MOVIES_FILE = 'movies.json'
USERS_FILE = 'users.json'
ADMINS_FILE = 'admins.json'

# TMDB API конфігурація
TMDB_API_KEY = os.getenv('TMDB_API_KEY',
                         '4819d57a475cf1ba39646b846f3d9d17')
TMDB_BASE_URL = 'https://api.themoviedb.org/3'
TMDB_IMAGE_BASE_URL = 'https://image.tmdb.org/t/p/w500'

# Глобальні змінні для зберігання стану
user_states = {}
temp_data = {}
genre_search_data = {}
user_movie_history = {}
genre_movie_history = {}


def ensure_file_exists(filename, default):
    """Перевіряє існування файлу, створює якщо не існує"""
    if not os.path.exists(filename):
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(default, f, ensure_ascii=False, indent=2)


def load_movies():
    """Завантажує список фільмів з файлу"""
    ensure_file_exists(MOVIES_FILE, [])
    try:
        with open(MOVIES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_movies(movies):
    """Зберігає список фільмів у файл"""
    with open(MOVIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(movies, f, ensure_ascii=False, indent=2)


def load_users():
    """Завантажує список користувачів у правильному форматі"""
    ensure_file_exists(USERS_FILE, {})
    try:
        with open(USERS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                new_data = {str(user_id): datetime.now(timezone.utc).isoformat() for user_id in data}
                save_users(new_data)
                return new_data
            return data
    except (json.JSONDecodeError, FileNotFoundError):
        return {}


def save_users(users):
    """Зберігає список користувачів"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def log_user(user_id):
    """Логує активність користувача"""
    users = load_users()
    users[str(user_id)] = datetime.now(timezone.utc).isoformat()
    save_users(users)


def get_weekly_user_count():
    """Повертає кількість унікальних користувачів за останні 7 днів"""
    users = load_users()
    count = 0
    for timestamp in users.values():
        try:
            if datetime.fromisoformat(timestamp) >= datetime.now(timezone.utc) - timedelta(days=7):
                count += 1
        except Exception:
            continue
    return count


def check_subscription(user_id):
    """Перевіряє чи підписаний користувач на канал"""
    try:
        member = bot.get_chat_member(f"@{CHANNEL_USERNAME}", user_id)
        return member.status in ["member", "creator", "administrator"]
    except Exception as e:
        print(f"Помилка перевірки підписки: {e}")
        return False


def normalize_genre(text):
    """Нормалізує назву жанру для порівняння"""
    return re.sub(r'[^a-zA-Zа-яА-ЯіїІЇєЄґҐ0-9\s]', '', text.lower().strip())


def split_genres(genre_text):
    """Розділяє рядок з жанрами на список"""
    parts = re.split(r'[/,;]+', genre_text)
    return [normalize_genre(p) for p in parts if p.strip() != '']


def send_main_menu(chat_id):
    """Надсилає головне меню"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🔍 Пошук фільму за кодом')
    markup.row('🎲 Випадковий фільм', '🎬 Пошук за жанром')
    if str(chat_id) == str(ADMIN_ID):
        markup.row('Адмін панель')
    markup.row('ℹ️ Інформація про бота')
    bot.send_message(chat_id, 'Оберіть опцію з меню:', reply_markup=markup)


def send_admin_panel(user_id):
    """Надсилає адмін панель"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('➕ Додати фільм 🎬', '➖ Видалити фільм 🎬')
    markup.row('🔍 Завантажити фільм за назвою')
    markup.row('📋 Список фільмів')
    markup.row('🗑️ Видалити всі фільми', '📊 Статистика')
    markup.row('➕ Додати адміна 👤', '➖ Видалити адміна 👤')
    markup.row('👑 Список адміністраторів')
    markup.row('◀️ Назад')
    bot.send_message(user_id, 'Адмін панель:', reply_markup=markup)


def format_movie(movie):
    """Форматує інформацію про фільм для відправки"""
    if not isinstance(movie, dict):
        return "Невірний формат фільму"

    caption = (f"🎬 {movie.get('title', 'Невідомо')}\n"
               f"⭐ IMDb: {movie.get('rating', 'Невідомо')}\n"
               f"⏱ Тривалість: {movie.get('duration', 'Невідомо')}\n"
               f"📅 Рік: {movie.get('year', 'Невідомо')}\n"
               f"🚫 Вік: {movie.get('age_category', 'Не вказано')}\n"
               f"🌍 Країна: {movie.get('country', 'Невідомо')}\n"
               f"🎭 Жанр: {movie.get('genre', 'Невідомо')}\n"
               f"#Код: {movie.get('code', 'Невідомо')}")

    if 'megogo_link' in movie:
        caption += f"\n\n🔗 Дивитися на Megogo: {movie['megogo_link']}"

    return caption


def load_admins():
    """Завантажує список адміністраторів"""
    ensure_file_exists(ADMINS_FILE, [ADMIN_ID])
    try:
        with open(ADMINS_FILE, 'r', encoding='utf-8') as f:
            admins = json.load(f)
            return [int(admin) for admin in admins]
    except (json.JSONDecodeError, FileNotFoundError):
        return [ADMIN_ID]


def save_admins(admins):
    """Зберігає список адміністраторів"""
    with open(ADMINS_FILE, 'w', encoding='utf-8') as f:
        json.dump(admins, f, ensure_ascii=False, indent=2)


def show_more_genre_movies(user_id, genre_input):
    """Показує фільми за жанром"""
    if genre_input not in genre_movie_history:
        genre_movie_history[genre_input] = []

    movies = load_movies()
    found_movies = []

    for m in movies:
        if isinstance(m, dict):
            movie_genres = m.get('genre', '')
            genres_list = split_genres(movie_genres)
            if genre_input in genres_list:
                found_movies.append(m)

    if not found_movies:
        bot.send_message(user_id, 'Фільми цього жанру не знайдені.')
        send_main_menu(user_id)
        return

    random.shuffle(found_movies)
    available_movies = [m for m in found_movies if m['code'] not in genre_movie_history[genre_input]]

    if len(available_movies) < 3:
        shown_in_history = [m for m in found_movies if m['code'] in genre_movie_history[genre_input]]
        if shown_in_history:
            num_needed = min(3 - len(available_movies), len(shown_in_history))
            additional_movies = random.sample(shown_in_history, num_needed)
            available_movies.extend(additional_movies)

    movies_to_show = available_movies[:3]

    for movie in movies_to_show:
        try:
            if 'poster' in movie and movie['poster']:
                bot.send_photo(user_id, movie['poster'], caption=format_movie(movie), parse_mode='Markdown')
            else:
                bot.send_message(user_id, format_movie(movie), parse_mode='Markdown')
            time.sleep(1)

            if movie['code'] not in genre_movie_history[genre_input]:
                genre_movie_history[genre_input].append(movie['code'])
        except Exception as e:
            print(f"Помилка при відправці фільму: {e}")
            continue

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🎬 Показати ще фільми цього жанру')
    markup.row('🎭 Обрати інший жанр')
    markup.row('◀️ Назад до головного меню')
    bot.send_message(user_id, 'Оберіть інший жанр або цей самий:', reply_markup=markup)


def get_existing_codes():
    """Отримує всі існуючі коди фільмів"""
    movies = load_movies()
    return {movie['code'] for movie in movies if isinstance(movie, dict) and 'code' in movie}


def get_existing_titles():
    """Отримує всі існуючі назви фільмів (нормалізовані)"""
    movies = load_movies()
    titles = set()
    for movie in movies:
        if isinstance(movie, dict) and 'title' in movie:
            normalized_title = re.sub(r'[^a-zA-Zа-яА-ЯіїІЇєЄґҐ0-9]', '', movie['title'].lower().strip())
            titles.add(normalized_title)
    return titles


def generate_unique_code():
    """Генерує унікальний 4-значний код"""
    existing_codes = get_existing_codes()

    while True:
        code = str(random.randint(1000, 9999))
        if code not in existing_codes:
            return code


def is_movie_exists(movie_title):
    """Перевіряє чи існує фільм з такою назвою"""
    existing_titles = get_existing_titles()
    normalized_title = re.sub(r'[^a-zA-Zа-яА-ЯіїІЇєЄґҐ0-9]', '', movie_title.lower().strip())
    return normalized_title in existing_titles


def delete_all_movies():
    """Видаляє всі фільми з бази"""
    save_movies([])
    global user_movie_history, genre_movie_history
    user_movie_history = {}
    genre_movie_history = {}


def search_tmdb_movies(query, year=None):
    """Пошук фільмів на TMDB"""
    try:
        url = f"{TMDB_BASE_URL}/search/movie"
        params = {
            'api_key': TMDB_API_KEY,
            'query': query,
            'language': 'uk-UA',
            'page': 1
        }
        if year:
            params['year'] = year

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json().get('results', [])
        else:
            print(f"TMDB API помилка: {response.status_code}")
            return []
    except Exception as e:
        print(f"Помилка пошуку на TMDB: {e}")
        return []


def get_tmdb_movie_details(movie_id):
    """Отримання детальної інформації про фільм з TMDB"""
    try:
        url = f"{TMDB_BASE_URL}/movie/{movie_id}"
        params = {
            'api_key': TMDB_API_KEY,
            'language': 'uk-UA',
            'append_to_response': 'credits'
        }

        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"TMDB API помилка деталей: {response.status_code}")
            return None
    except Exception as e:
        print(f"Помилка отримання деталей фільму: {e}")
        return None


def convert_runtime(minutes):
    """Конвертує хвилини у формат години:хвилини"""
    if not minutes:
        return "Невідомо"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours} год {mins} хв" if hours > 0 else f"{mins} хв"


def get_age_rating(movie_details):
    """Отримує віковий рейтинг фільму"""
    try:
        release_dates_url = f"{TMDB_BASE_URL}/movie/{movie_details['id']}/release_dates"
        params = {'api_key': TMDB_API_KEY}

        response = requests.get(release_dates_url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for country in data.get('results', []):
                if country['iso_3166_1'] in ['UA', 'US']:
                    for release in country.get('release_dates', []):
                        if release.get('certification'):
                            return f"{release['certification']}+"
        return "16+"
    except Exception as e:
        print(f"Помилка отримання вікового рейтингу: {e}")
        return "16+"


def auto_add_movie_from_tmdb(movie_title, user_id, year=None):
    """Автоматично додає фільм з TMDB"""
    try:
        if is_movie_exists(movie_title):
            return False, f"Фільм '{movie_title}' вже існує в базі"

        search_results = search_tmdb_movies(movie_title, year)
        if not search_results:
            return False, "Фільм не знайдено на TMDB"

        movie_data = search_results[0]
        movie_details = get_tmdb_movie_details(movie_data['id'])

        if not movie_details:
            return False, "Не вдалося отримати деталі фільму"

        final_title = movie_details['title']
        if is_movie_exists(final_title):
            return False, f"Фільм '{final_title}' вже існує в базі"

        code = generate_unique_code()

        genres = [genre['name'] for genre in movie_details.get('genres', [])]
        genre_str = '/'.join(genres[:3])

        countries = [country['name'] for country in movie_details.get('production_countries', [])]
        country_str = ', '.join(countries[:2])

        rating = round(movie_details.get('vote_average', 0), 1)

        release_year = movie_details['release_date'][:4] if movie_details.get('release_date') else 'Невідомо'

        movie = {
            'code': code,
            'title': final_title,
            'rating': str(rating),
            'duration': convert_runtime(movie_details.get('runtime')),
            'year': release_year,
            'age_category': get_age_rating(movie_details),
            'country': country_str,
            'genre': genre_str,
            'poster': f"{TMDB_IMAGE_BASE_URL}{movie_details['poster_path']}" if movie_details.get(
                'poster_path') else '',
            'description': movie_details.get('overview', ''),
            'source': 'tmdb_auto'
        }

        existing_movies = load_movies()
        existing_movies.append(movie)
        save_movies(existing_movies)

        return True, movie

    except Exception as e:
        print(f"Помилка автоматичного додавання фільму: {e}")
        return False, f"Помилка: {str(e)}"


def send_movies_list(user_id):
    """Надсилає список всіх фільмів з кодами"""
    movies = load_movies()

    if not movies:
        bot.send_message(user_id, "📭 База фільмів порожня.")
        return

    movies.sort(key=lambda x: x.get('title', '').lower())

    chunk_size = 50
    chunks = [movies[i:i + chunk_size] for i in range(0, len(movies), chunk_size)]

    for chunk_index, chunk in enumerate(chunks, 1):
        movie_list = "📋 **СПИСОК ФІЛЬМІВ**\n\n"

        for i, movie in enumerate(chunk, 1):
            title = movie.get('title', 'Невідома назва')
            code = movie.get('code', 'Невідомий код')
            year = movie.get('year', 'Невідомо')

            movie_list += f"{i + (chunk_index - 1) * chunk_size}. **{title}** ({year}) - `{code}`\n"

        if len(chunks) > 1:
            movie_list += f"\n*Частина {chunk_index} з {len(chunks)}*"

        try:
            bot.send_message(user_id, movie_list, parse_mode='Markdown')
            time.sleep(0.5)
        except Exception as e:
            print(f"Помилка при відправці списку фільмів: {e}")
            if "Message is too long" in str(e):
                smaller_chunks = [chunk[i:i + 20] for i in range(0, len(chunk), 20)]
                for small_chunk in smaller_chunks:
                    small_list = "📋 **СПИСОК ФІЛЬМІВ**\n\n"
                    for j, m in enumerate(small_chunk, 1):
                        title = m.get('title', 'Невідома назва')
                        code = m.get('code', 'Невідомий код')
                        year = m.get('year', 'Невідомо')
                        small_list += f"{j}. **{title}** ({year}) - `{code}`\n"
                    bot.send_message(user_id, small_list, parse_mode='Markdown')
                    time.sleep(0.3)

    total_movies = len(movies)
    unique_titles = len(get_existing_titles())
    bot.send_message(user_id, f"📊 **Всього фільмів у базі:** {total_movies}\n**Унікальних назв:** {unique_titles}")


def send_delete_confirmation(user_id):
    """Надсилає підтвердження видалення всіх фільмів"""
    movies_count = len(load_movies())

    if movies_count == 0:
        bot.send_message(user_id, "📭 База фільмів вже порожня.")
        return

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('✅ ТАК, видалити всі фільми')
    markup.row('❌ НІ, скасувати')

    message = (
        f"⚠️ **УВАГА! ВИДАЛЕННЯ ВСІХ ФІЛЬМІВ**\n\n"
        f"Ви збираєтесь видалити **всі {movies_count} фільмів** з бази даних!\n\n"
        f"🔴 **Ця дія незворотна!**\n"
        f"🔴 **Всі дані будуть втрачені!**\n\n"
        f"Підтвердіть видалення:"
    )

    bot.send_message(user_id, message, reply_markup=markup, parse_mode='Markdown')


@bot.message_handler(commands=['start'])
def start(message):
    """Обробник команди /start"""
    try:
        user_id = message.from_user.id
        if not check_subscription(user_id):
            markup = types.InlineKeyboardMarkup()
            btn = types.InlineKeyboardButton('Підписатися', url=f'https://t.me/{CHANNEL_USERNAME}')
            markup.add(btn)
            bot.send_message(message.chat.id, 'Щоб користуватися ботом, підпишіться на канал:', reply_markup=markup)
            return

        log_user(user_id)
        send_main_menu(message.chat.id)
    except Exception as e:
        print(f"Помилка в команді /start: {e}")
        bot.send_message(message.chat.id, "Сталася помилка. Спробуйте ще раз.")


def handle_state(message):
    """Обробляє повідомлення в залежності від стану користувача"""
    user_id = message.from_user.id
    text = message.text.strip() if message.text else ""
    state = user_states.get(user_id)

    if state == 'awaiting_code':
        movies = load_movies()
        found = next((m for m in movies if isinstance(m, dict) and m['code'] == text), None)
        if found:
            try:
                if 'poster' in found and found['poster']:
                    bot.send_photo(user_id, found['poster'], caption=format_movie(found), parse_mode='Markdown')
                else:
                    bot.send_message(user_id, format_movie(found), parse_mode='Markdown')
            except Exception as e:
                print(f"Помилка при відправці фільму: {e}")
                bot.send_message(user_id, 'Сталася помилка при відправці фільму.')
        else:
            bot.send_message(user_id, 'Фільм не знайдено.')
        user_states.pop(user_id, None)
        send_main_menu(user_id)

    elif state == 'awaiting_genre':
        genre_input = normalize_genre(text)
        genre_search_data[user_id] = genre_input
        show_more_genre_movies(user_id, genre_input)
        user_states.pop(user_id, None)

    elif state == 'add_code':
        if not text.isdigit() or len(text) != 4:
            bot.send_message(user_id, 'Код має бути 4-значним числом (наприклад: 1234). Спробуйте ще раз:')
            return

        existing_codes = get_existing_codes()
        if text in existing_codes:
            bot.send_message(user_id, 'Цей код вже використовується. Введіть інший 4-значний код:')
            return

        temp_data[user_id]['code'] = text
        user_states[user_id] = 'add_title'
        bot.send_message(user_id, 'Введіть назву фільму:')

    elif state == 'add_title':
        if is_movie_exists(text):
            bot.send_message(user_id, f'Фільм з назвою "{text}" вже існує. Введіть іншу назву:')
            return

        temp_data[user_id]['title'] = text
        user_states[user_id] = 'add_rating'
        bot.send_message(user_id, 'Введіть рейтинг IMDb:')

    elif state == 'add_rating':
        temp_data[user_id]['rating'] = text
        user_states[user_id] = 'add_duration'
        bot.send_message(user_id, 'Введіть тривалість:')

    elif state == 'add_duration':
        temp_data[user_id]['duration'] = text
        user_states[user_id] = 'add_year'
        bot.send_message(user_id, 'Введіть рік:')

    elif state == 'add_year':
        temp_data[user_id]['year'] = text
        user_states[user_id] = 'add_age_category'
        bot.send_message(user_id, 'Введіть вікову категорію (наприклад, 16+):')

    elif state == 'add_age_category':
        temp_data[user_id]['age_category'] = text
        user_states[user_id] = 'add_country'
        bot.send_message(user_id, 'Введіть країну:')

    elif state == 'add_country':
        temp_data[user_id]['country'] = text
        user_states[user_id] = 'add_genre'
        bot.send_message(user_id, 'Введіть жанр (
