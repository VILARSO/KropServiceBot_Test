import os
from dotenv import load_dotenv

# Завантажуємо змінні середовища з файлу .env
load_dotenv()

API_TOKEN = os.getenv('API_TOKEN')
if not API_TOKEN:
    print("❌ API_TOKEN не заданий. Будь ласка, встановіть змінну середовища API_TOKEN.")
    exit(1)

MONGO_DB_URL = os.getenv('MONGO_DB_URL')
if not MONGO_DB_URL:
    print("❌ MONGO_DB_URL не заданий. Будь ласка, встановіть змінну середовища MONGO_DB_URL для підключення до MongoDB.")
    exit(1)

# Налаштування вебхука (для розгортання на серверах)
WEBHOOK_HOST = os.getenv('WEBHOOK_HOST', '[https://your-domain.com](https://your-domain.com)') # Замініть на ваш домен
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook') # Шлях вебхука, не включає API_TOKEN
WEBAPP_HOST = os.getenv('WEBAPP_HOST', '0.0.0.0') # Для прослуховування всіх інтерфейсів
WEBAPP_PORT = int(os.getenv('WEBAPP_PORT', 8080))

# Налаштування пагінації
MY_POSTS_PER_PAGE = 5
VIEW_POSTS_PER_PAGE = 5

# Термін дії оголошень у днях (для TTL індексу MongoDB)
POST_LIFETIME_DAYS = 30

# Категорії оголошень
CATEGORIES = [
    ("👷 Робота / Підробітки", "👷 Робота / Підробітки"),
    ("🛠️ Побутові послуги", "🛠️ Побутові послуги"),
    ("🚗 Доставка / Перевезення", "🚗 Доставка / Перевезення"),
    ("💻 Онлайн-послуги", "💻 Онлайн-послуги"),
    ("💅 Краса / Здоров’я", "💅 Краса / Здоров’я"),
    ("📚 Репетитори / Освіта", "📚 Репетитори / Освіта"),
    ("🧩 Інше", "🧩 Інше"),
]

# Тематичні емоджі для типу "Робота" та "Послуга"
TYPE_EMOJIS = {
    "робота": "💼",
    "послуга": "🤝"
}
