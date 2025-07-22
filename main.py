import os
import asyncio
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import BadRequest, TelegramAPIError, MessageNotModified, MessageToDeleteNotFound

import motor.motor_asyncio
from motor.core import AgnosticClient, AgnosticDatabase
from pymongo import DESCENDING, ASCENDING, ReturnDocument

# Імпорт модулів бота
from config import API_TOKEN, MONGO_DB_URL, WEBHOOK_HOST, WEBHOOK_PATH, WEBAPP_HOST, WEBAPP_PORT, POST_LIFETIME_DAYS, MY_POSTS_PER_PAGE, VIEW_POSTS_PER_PAGE, CATEGORIES, TYPE_EMOJIS
from states import AppStates
from keyboards import main_kb, categories_kb, confirm_add_post_kb, post_actions_kb, edit_post_kb, pagination_kb, confirm_delete_kb, back_kb, type_kb, contact_kb

# Імпортуємо update_or_send_interface_message, can_edit, get_next_sequence_value з utils
from utils import escape_markdown_v2, update_or_send_interface_message, can_edit, get_next_sequence_value

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger().addHandler(logging.StreamHandler())

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# Глобальні змінні для бази даних
db_client: AgnosticClient = None
db: AgnosticDatabase = None

# ======== Функції бази даних (перенесені з main.py для чистоти) ========
async def init_db_connection():
    """Ініціалізує підключення до MongoDB та створює необхідні індекси."""
    global db_client, db
    try:
        logging.info("Підключення до MongoDB...")
        db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DB_URL)
        db = db_client.cropservice_db # Назва вашої бази даних
        logging.info("Підключення до MongoDB успішно встановлено.")

        # Створення індексів
        # TTL індекс для автоматичного видалення старих оголошень
        await db.posts.create_index("created_at", expireAfterSeconds=int(POST_LIFETIME_DAYS * 24 * 60 * 60))
        logging.info(f"Створено TTL індекс на 'created_at' для колекції 'posts' з терміном дії {POST_LIFETIME_DAYS} днів.")

        # Складений індекс для перегляду публічних оголошень
        await db.posts.create_index([("category", 1), ("created_at", DESCENDING)])
        logging.info("Створено складений індекс на '(category, created_at)' для колекції 'posts'.")

        # Складений індекс для перегляду 'Моїх оголошень'
        await db.posts.create_index([("user_id", 1), ("created_at", DESCENDING)])
        logging.info("Створено складений індекс на '(user_id, created_at)' для колекції 'posts'.")

        # Унікальний індекс для користувацького ID оголошення
        await db.posts.create_index("id", unique=True)
        logging.info("Створено унікальний індекс на 'id' для колекції 'posts'.")

        # Індекс для колекції лічильників (автоматично _id)
        await db.counters.create_index("_id")
        logging.info("Створено унікальний індекс на '_id' для колекції 'counters'.")

    except Exception as e:
        logging.critical(f"Помилка підключення до MongoDB або створення індексів: {e}", exc_info=True)
        exit(1)

# ======== Допоміжні функції для переходу між станами ========
WELCOME_MESSAGE = (
    "👋 Привіт\\! Я CropServiceBot — допомагаю знаходити підробітки або виконавців у твоєму місті\\.\n\n"
    "➕ \\— Додати оголошення\n"
    "🔍 \\— Пошук оголошень\n"
    "🗂️ \\— Мої оголошення\n"
    "❓ \\— Допомога"
)

async def go_to_main_menu(bot_obj: Bot, chat_id: int, state: FSMContext):
    """Повертає до головного меню, оновлюючи існуюче повідомлення."""
    logging.info(f"User {chat_id} going to main menu.")
    await update_or_send_interface_message(bot_obj, chat_id, state, WELCOME_MESSAGE, main_kb(), parse_mode='MarkdownV2')
    await state.set_state(AppStates.MAIN_MENU)

async def show_view_posts_page(bot_obj: Bot, chat_id: int, state: FSMContext, offset: int = 0):
    logging.info(f"Showing view posts page for user {chat_id}, offset {offset}")
    try:
        data = await state.get_data()
        cat = data.get('current_view_category')

        if not cat:
            logging.error(f"Category not found in state for user {chat_id}")
            return await go_to_main_menu(bot_obj, chat_id, state)

        # Отримуємо загальну кількість оголошень для пагінації
        total_posts = await db.posts.count_documents({'category': cat})
        
        # Отримуємо оголошення з MongoDB з сортуванням та пагінацією
        posts_cursor = db.posts.find(
            {'category': cat}
        ).sort([('created_at', DESCENDING)]).skip(offset).limit(VIEW_POSTS_PER_PAGE)
        
        page_posts = await posts_cursor.to_list(length=VIEW_POSTS_PER_PAGE)

        if not page_posts: 
            logging.info(f"No posts found for category '{cat}' for user {chat_id}")
            kb = InlineKeyboardMarkup(row_width=1).add(
                InlineKeyboardButton("⬅️ Назад до категорій", callback_data="go_back_to_prev_step"),
                InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu")
            )
            text_to_send = f"У категорії «{escape_markdown_v2(cat)}» поки що немає оголошень\\."
            return await update_or_send_interface_message(
                bot_obj, chat_id, state,
                text_to_send,
                kb, parse_mode='MarkdownV2'
            )

        await state.update_data(offset=offset)
        
        total_pages = (total_posts + VIEW_POSTS_PER_PAGE - 1) // VIEW_POSTS_PER_PAGE
        current_page = offset // VIEW_POSTS_PER_PAGE + 1
        
        full_text = (f"📋 **{escape_markdown_v2(cat)}** \\(Сторінка {escape_markdown_v2(current_page)}/{escape_markdown_v2(total_pages)}\\)\n\n")
        
        # Використовуємо pagination_kb для створення кнопок пагінації
        combined_keyboard = pagination_kb(total_posts, offset, VIEW_POSTS_PER_PAGE, 'viewpage', cat)

        for i, p in enumerate(page_posts):
            type_emoji = TYPE_EMOJIS.get(p['type'], '') 
            
            post_block = (f"ID: {escape_markdown_v2(p['id'])}\n"
                         f"{escape_markdown_v2(type_emoji)} **{escape_markdown_v2(p['type'].capitalize())}**\n"
                         f"🔹 {escape_markdown_v2(p['description'])}\n") 
            
            if p['username']:
                if p['username'].isdigit():
                    post_block += f"👤 Автор: \\_Приватний користувач\\_\n"
                else:
                    post_block += f"👤 Автор: \\@{escape_markdown_v2(p['username'])}\n"
            
            contact_info = p.get('contacts', '')
            if contact_info:
                post_block += f"📞 Контакт: {escape_markdown_v2(contact_info)}\n"
            
            full_text += post_block
            
            if i < len(page_posts) - 1:
                full_text += "\n—\n\n" 
        
        await update_or_send_interface_message(bot_obj, chat_id, state, full_text, combined_keyboard, parse_mode='MarkdownV2', disable_web_page_preview=True)

    except Exception as e:
        logging.error(f"Error in show_view_posts_page for user {chat_id}: {e}", exc_info=True)
        await update_or_send_interface_message(bot_obj, chat_id, state, "Вибачте, сталася неочікувана помилка при перегляді оголошень\\. Спробуйте ще раз\\.", main_kb(), parse_mode='MarkdownV2')
        await state.set_state(AppStates.MAIN_MENU)

async def show_my_posts_page(bot_obj: Bot, chat_id: int, state: FSMContext, offset: int = 0):
    logging.info(f"Showing my posts page for user {chat_id}, offset {offset}")
    try:
        # Отримуємо загальну кількість оголошень користувача
        total_posts = await db.posts.count_documents({'user_id': chat_id})

        if total_posts == 0:
            logging.info(f"No posts found for user {chat_id}")
            kb_no_posts = InlineKeyboardMarkup(row_width=1).add(
                InlineKeyboardButton("➕ Додати оголошення", callback_data="add_post"), 
                InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu")
            )
            return await update_or_send_interface_message(bot_obj, chat_id, state, "🧐 У вас немає оголошень\\.", kb_no_posts, parse_mode='MarkdownV2')

        # Отримуємо оголошення користувача з MongoDB, сортуємо за датою та пагінуємо
        user_posts_cursor = db.posts.find(
            {'user_id': chat_id}
        ).sort([('created_at', DESCENDING)]).skip(offset).limit(MY_POSTS_PER_PAGE)
        
        page_posts = await user_posts_cursor.to_list(length=MY_POSTS_PER_PAGE)
        
        await state.update_data(offset=offset)

        total_pages = (total_posts + MY_POSTS_PER_PAGE - 1) // MY_POSTS_PER_PAGE
        current_page = offset // MY_POSTS_PER_PAGE + 1
        
        full_text = f"🗂️ **Мої оголошення** \\(Сторінка {escape_markdown_v2(current_page)}/{escape_markdown_v2(total_pages)}\\)\n\n"
        
        combined_keyboard = InlineKeyboardMarkup(row_width=2) 

        for i, p in enumerate(page_posts):
            type_emoji = TYPE_EMOJIS.get(p['type'], '') 
            
            local_post_num = offset + i + 1
            
            post_block = (f"№ {escape_markdown_v2(local_post_num)}\n" 
                         f"ID: {escape_markdown_v2(p['id'])}\n"
                         f"{escape_markdown_v2(type_emoji)} **{escape_markdown_v2(p['type'].capitalize())}**\n"
                         f"🔹 {escape_markdown_v2(p['description'])}\n")
            
            if p['username']:
                if p['username'].isdigit():
                    post_block += f"👤 Автор: \\_Приватний користувач\\_\n"
                else:
                    post_block += f"👤 Автор: \\@{escape_markdown_v2(p['username'])}\n"
            
            if p.get('contacts'):
                 post_block += f"📞 Контакт: {escape_markdown_v2(p['contacts'])}\n"
            
            full_text += post_block
            
            post_kb_row = []
            if can_edit(p):
                post_kb_row.append(InlineKeyboardButton(f"✏️ Редагувати № {local_post_num}", callback_data=f"edit_{p['id']}")) 
            post_kb_row.append(InlineKeyboardButton(f"🗑️ Видалити № {local_post_num}", callback_data=f"delete_{p['id']}")) 
            
            combined_keyboard.row(*post_kb_row)

            if i < len(page_posts) - 1:
                full_text += "\n—\n\n"

        # Використовуємо pagination_kb для створення кнопок пагінації
        nav_keyboard = pagination_kb(total_posts, offset, MY_POSTS_PER_PAGE, 'mypage', str(chat_id))
        
        # Додаємо кнопки навігації до основної клавіатури
        for row in nav_keyboard.inline_keyboard:
            combined_keyboard.add(*row)
            
        await update_or_send_interface_message(bot_obj, chat_id, state, full_text, combined_keyboard, parse_mode='MarkdownV2', disable_web_page_preview=True)


    except Exception as e:
        logging.error(f"Error in show_my_posts_page for user {chat_id}: {e}", exc_info=True)
        await update_or_send_interface_message(bot_obj, chat_id, state, "Вибачте, сталася неочікувана помилка при завантаженні ваших оголошень\\. Спробуйте ще раз\\.", main_kb(), parse_mode='MarkdownV2')
        await state.set_state(AppStates.MAIN_MENU)

# ======== Обробники команд ========
@dp.message_handler(commands=['start'], state="*")
async def on_start(msg: types.Message, state: FSMContext):
    logging.info(f"User {msg.from_user.id} started bot.")
    logging.info(f"DEBUG: on_start handler triggered for user {msg.from_user.id}")
    
    try:
        await msg.delete() 
    except MessageToDeleteNotFound:
        pass
    except Exception as e:
        logging.warning(f"Failed to delete /start command: {e}")
    
    await state.update_data(last_bot_message_id=None)
    await go_to_main_menu(msg.bot, msg.chat.id, state)


@dp.callback_query_handler(lambda c: c.data == 'go_back_to_main_menu', state='*')
async def on_back_to_main(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} pressed 'Go Back to Main Menu'.")
    await call.answer()
    await go_to_main_menu(call.message.bot, call.message.chat.id, state)


@dp.callback_query_handler(lambda c: c.data == 'go_back_to_prev_step', state='*')
async def on_back_to_prev_step(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} pressed 'Go Back to Previous Step'.")
    await call.answer()
    current_state = await state.get_state()
    chat_id = call.message.chat.id
    bot_obj = call.message.bot
    
    if current_state == AppStates.ADD_TYPE.state:
        await go_to_main_menu(bot_obj, chat_id, state)
    elif current_state == AppStates.ADD_CAT.state:
        await update_or_send_interface_message(bot_obj, chat_id, state, "🔹 Виберіть тип оголошення:", type_kb())
        await state.set_state(AppStates.ADD_TYPE)
    elif current_state == AppStates.ADD_DESC.state:
        await update_or_send_interface_message(bot_obj, chat_id, state, "🗂️ Виберіть категорію:", categories_kb(is_post_creation=True))
        await state.set_state(AppStates.ADD_CAT)
    elif current_state == AppStates.ADD_CONT.state:
        await update_or_send_interface_message(bot_obj, chat_id, state, "✏️ Введіть опис (до 500 символів):", back_kb())
        await state.set_state(AppStates.ADD_DESC)
    elif current_state == AppStates.ADD_CONFIRM.state:
        await update_or_send_interface_message(bot_obj, chat_id, state, "📞 Введіть контакт (необов’язково):", contact_kb())
        await state.set_state(AppStates.ADD_CONT)
    elif current_state == AppStates.VIEW_CAT.state:
        await go_to_main_menu(bot_obj, chat_id, state)
    elif current_state == AppStates.VIEW_LISTING.state:
        await update_or_send_interface_message(bot_obj, chat_id, state, "🔎 Оберіть категорію:", categories_kb(is_post_creation=False))
        await state.set_state(AppStates.VIEW_CAT)
    elif current_state == AppStates.MY_POSTS_VIEW.state:
        await go_to_main_menu(bot_obj, chat_id, state) 
    elif current_state == AppStates.EDIT_DESC.state:
        data = await state.get_data()
        await show_my_posts_page(bot_obj, chat_id, state, data.get('offset', 0))
        await state.set_state(AppStates.MY_POSTS_VIEW)
    else:
        await go_to_main_menu(bot_obj, chat_id, state)

# ======== Додавання оголошень ========
@dp.callback_query_handler(lambda c: c.data == 'add_post', state="*")
async def add_start(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} initiated 'Add Post'.")
    await call.answer()
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "🔹 Виберіть тип оголошення:", type_kb())
    await state.set_state(AppStates.ADD_TYPE)

@dp.callback_query_handler(lambda c: c.data.startswith('type_'), state=AppStates.ADD_TYPE)
async def add_type(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} selected post type: {call.data}.")
    await call.answer()
    typ = 'робота' if call.data == 'type_work' else 'послуга'
    await state.update_data(type=typ)
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "🗂️ Виберіть категорію:", categories_kb(is_post_creation=True))
    await state.set_state(AppStates.ADD_CAT)

@dp.callback_query_handler(lambda c: c.data.startswith('post_cat_'), state=AppStates.ADD_CAT)
async def add_cat(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split('_')[2])
    _, cat = CATEGORIES[idx]
    logging.info(f"User {call.from_user.id} selected category: {cat}.")
    await call.answer()
    await state.update_data(category=cat)
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "✏️ Введіть опис (до 500 символів):", back_kb())
    await state.set_state(AppStates.ADD_DESC)

@dp.message_handler(state=AppStates.ADD_DESC)
async def add_desc(msg: types.Message, state: FSMContext):
    logging.info(f"User {msg.from_user.id} entered description.")
    text = msg.text.strip()
    
    try:
        await msg.delete()
    except MessageToDeleteNotFound:
        pass

    if not text:
        return await update_or_send_interface_message(msg.bot, msg.chat.id, state, "❌ Опис не може бути порожнім\\. Введіть опис (до 500 символів):", back_kb(), parse_mode='MarkdownV2')
    if len(text) > 500:
        return await update_or_send_interface_message(msg.bot, msg.chat.id, state, f"❌ Занадто довгий \\({len(text)}/500\\)\\.", back_kb(), parse_mode='MarkdownV2')
    
    await state.update_data(desc=text)
    await update_or_send_interface_message(msg.bot, msg.chat.id, state, "📞 Введіть контакт (необов’язково):", contact_kb())
    await state.set_state(AppStates.ADD_CONT)

@dp.callback_query_handler(lambda c: c.data == 'skip_cont', state=AppStates.ADD_CONT)
async def skip_cont(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} skipped contact info.")
    await call.answer()
    await state.update_data(cont="")
    data = await state.get_data()
    
    type_emoji = TYPE_EMOJIS.get(data['type'], '')
    
    summary = (
        f"🔎 \\*Перевірте:\\*\n"
        f"{escape_markdown_v2(type_emoji)} **{escape_markdown_v2(data['type'].capitalize())}** \\| **{escape_markdown_v2(data['category'])}**\n"
        f"🔹 {escape_markdown_v2(data['desc'])}\n"
        f"📞 \\_немає\\_"
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_add_post"),
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, summary, kb, parse_mode='MarkdownV2')
    await state.set_state(AppStates.ADD_CONFIRM)

@dp.message_handler(state=AppStates.ADD_CONT)
async def add_cont(msg: types.Message, state: FSMContext):
    logging.info(f"User {msg.from_user.id} entered contact info.")
    text = msg.text.strip()
    
    try:
        await msg.delete()
    except MessageToDeleteNotFound:
        pass

    if not text:
        return await update_or_send_interface_message(msg.bot, msg.chat.id, state, "❌ Контакт не може бути порожнім\\. Введіть номер телефону або пропустіть\\.", contact_kb(), parse_mode='MarkdownV2')
    
    phone_pattern_regex = r'^(?:0\d{9}|\+380\d{9}|@[a-zA-Z0-9_]{5,32})$'

    if not re.fullmatch(phone_pattern_regex, text):
        logging.warning(f"User {msg.from_user.id} entered invalid contact format: '{text}'")
        return await update_or_send_interface_message(
            msg.bot, msg.chat.id, state,
            "❌ Невірний формат\\. Будь ласка, введіть номер телефону у форматі \\+380XXXXXXXXX або 0XXXXXXXXX, або username Telegram \\(@username\\)\\.",
            contact_kb(), parse_mode='MarkdownV2'
        )
    
    await state.update_data(cont=text)
    data = await state.get_data()
    
    type_emoji = TYPE_EMOJIS.get(data['type'], '')

    summary = (
        f"🔎 \\*Перевірте:\\*\n"
        f"{escape_markdown_v2(type_emoji)} **{escape_markdown_v2(data['type'].capitalize())}** \\| **{escape_markdown_v2(data['category'])}**\n"
        f"🔹 {escape_markdown_v2(data['desc'])}\n"
        f"📞 {escape_markdown_v2(data['cont'])}"
    )
    kb = InlineKeyboardMarkup(row_width=2).add(
        InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_add_post"),
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    await update_or_send_interface_message(msg.bot, msg.chat.id, state, summary, kb, parse_mode='MarkdownV2')
    await state.set_state(AppStates.ADD_CONFIRM)

@dp.callback_query_handler(lambda c: c.data == 'confirm_add_post', state=AppStates.ADD_CONFIRM)
async def add_confirm(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} confirmed post creation.")
    await call.answer()
    d = await state.get_data()
    
    contact_info = d.get('cont', "")
    if contact_info:
        phone_pattern_regex = r'^(?:0\d{9}|\+380\d{9}|@[a-zA-Z0-9_]{5,32})$'
        if not re.fullmatch(phone_pattern_regex, contact_info):
            logging.error(f"Invalid contact format somehow slipped through for user {call.from_user.id}: {contact_info}")
            await update_or_send_interface_message(
                call.message.bot, call.message.chat.id, state,
                "❌ Помилка: Невірний формат контакту\\. Будь ласка, спробуйте ще раз\\.",
                main_kb(), parse_mode='MarkdownV2'
            )
            await state.set_state(AppStates.MAIN_MENU)
            return

    post_id = await get_next_sequence_value(db, 'postid')

    post_data = {
        'id': post_id,
        'user_id': call.from_user.id,
        'username': call.from_user.username or str(call.from_user.id),
        'type': d['type'],
        'category': d['category'],
        'description': d['desc'],
        'contacts': contact_info,
        'created_at': datetime.utcnow()
    }
    
    try:
        await db.posts.insert_one(post_data)
        logging.info(f"Added post {post_id} to MongoDB for user {call.from_user.id}")
    except Exception as e:
        logging.error(f"Failed to save post to MongoDB: {e}", exc_info=True)
        await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "❌ Вибачте, сталася помилка при збереженні оголошення\\. Спробуйте ще раз\\.", main_kb(), parse_mode='MarkdownV2')
        await state.set_state(AppStates.MAIN_MENU)
        return

    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "✅ Оголошення успішно додано\\!", parse_mode='MarkdownV2') 
    await show_my_posts_page(call.message.bot, call.message.chat.id, state, 0)
    await state.set_state(AppStates.MY_POSTS_VIEW)


# ======== Перегляд оголошень (Повернення до пагінації) ========
@dp.callback_query_handler(lambda c: c.data == 'view_posts', state="*")
async def view_start(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} initiated 'View Posts'.")
    await call.answer()
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "🔎 Оберіть категорію:", categories_kb(is_post_creation=False))
    await state.set_state(AppStates.VIEW_CAT)

@dp.callback_query_handler(lambda c: c.data.startswith('view_cat_'), state=AppStates.VIEW_CAT)
async def view_cat(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split('_')[2])
    cat_name = CATEGORIES[idx][1]
    logging.info(f"User {call.from_user.id} selected view category: {cat_name}.")
    await call.answer()
    
    await state.update_data(current_view_category=cat_name, current_category_idx=idx)
    await show_view_posts_page(call.message.bot, call.message.chat.id, state, 0)
    await state.set_state(AppStates.VIEW_LISTING)
    
@dp.callback_query_handler(lambda c: c.data.startswith('viewpage_'), state=AppStates.VIEW_LISTING)
async def view_paginate(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} paginating view posts to offset {call.data.split('_')[1]}.")
    await call.answer()
    offset = int(call.data.split('_')[1])
    await show_view_posts_page(call.message.bot, call.message.chat.id, state, offset)


# ======== Мої оголошення ========
@dp.callback_query_handler(lambda c: c.data=='my_posts', state="*")
async def my_posts_start(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} pressed 'My Posts'.")
    await call.answer()
    await show_my_posts_page(call.message.bot, call.message.chat.id, state, 0)
    await state.set_state(AppStates.MY_POSTS_VIEW)

@dp.callback_query_handler(lambda c: c.data.startswith('mypage_'), state=AppStates.MY_POSTS_VIEW)
async def my_posts_paginate(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} paginating my posts to offset {call.data.split('_')[1]}.")
    await call.answer()
    offset = int(call.data.split('_')[1])
    await show_my_posts_page(call.message.bot, call.message.chat.id, state, offset)


# ======== Редагування ========
@dp.callback_query_handler(lambda c: c.data.startswith('edit_'), state=AppStates.MY_POSTS_VIEW)
async def edit_start(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} initiated edit for post {call.data.split('_')[1]}.")
    await call.answer()
    pid = int(call.data.split('_')[1])
    
    post = await db.posts.find_one({'id': pid, 'user_id': call.from_user.id})
    
    if not post or not can_edit(post):
        logging.warning(f"User {call.from_user.id} tried to edit expired or non-existent/unauthorized post {pid}.")
        await call.answer("⏰ Час редагування (15 хв) вичерпано, або оголошення не знайдено/належить іншому користувачу.\\.", show_alert=True) 
        return
        
    await state.update_data(edit_pid=pid)
    
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "✏️ Введіть новий опис (до 500 символів):", back_kb())
    await state.set_state(AppStates.EDIT_DESC)

@dp.message_handler(state=AppStates.EDIT_DESC)
async def process_edit(msg: types.Message, state: FSMContext):
    logging.info(f"User {msg.from_user.id} submitting new description for edit.")
    text = msg.text.strip()
    
    try:
        await msg.delete()
    except MessageToDeleteNotFound:
        pass

    if not text or len(text) > 500:
        return await update_or_send_interface_message(msg.bot, msg.chat.id, state, f"❌ Неприпустимий опис \\(1\\-500 символів\\)\\.", back_kb(), parse_mode='MarkdownV2') 
        
    data = await state.get_data()
    pid = data['edit_pid']
    
    try:
        result = await db.posts.update_one(
            {'id': pid, 'user_id': msg.from_user.id}, 
            {'$set': {'description': text}}
        )
        if result.matched_count == 0:
            logging.warning(f"No post found to update for user {msg.from_user.id}, post {pid}")
            await update_or_send_interface_message(msg.bot, msg.chat.id, state, "❌ Оголошення не знайдено або ви не маєте прав на його редагування\\.", main_kb(), parse_mode='MarkdownV2')
            await state.set_state(AppStates.MAIN_MENU)
            return
        logging.info(f"Edited post {pid} in MongoDB for user {msg.from_user.id}")
    except Exception as e:
        logging.error(f"Failed to update post in MongoDB: {e}", exc_info=True)
        await update_or_send_interface_message(msg.bot, msg.chat.id, state, "❌ Вибачте, сталася помилка при оновленні опису оголошення\\. Спробуйте ще раз\\.", main_kb(), parse_mode='MarkdownV2')
        await state.set_state(AppStates.MAIN_MENU)
        return

    await update_or_send_interface_message(msg.bot, msg.chat.id, state, "✅ Опис оголошення оновлено\\!", parse_mode='MarkdownV2')
    await show_my_posts_page(msg.bot, msg.chat.id, state, data.get('offset', 0))
    await state.set_state(AppStates.MY_POSTS_VIEW)


# ======== Видалення ========
@dp.callback_query_handler(lambda c: c.data.startswith('delete_'), state=AppStates.MY_POSTS_VIEW)
async def delete_post(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} initiating delete for post {call.data.split('_')[1]}.")
    
    pid = int(call.data.split('_')[1])
    
    try:
        result = await db.posts.delete_one({'id': pid, 'user_id': call.from_user.id})
        
        if result.deleted_count == 0:
            logging.warning(f"User {call.from_user.id} tried to delete non-existent or unauthorized post {pid}.")
            await call.answer("❌ Оголошення не знайдено або ви не маєте прав на його видалення.", show_alert=True)
            await show_my_posts_page(call.message.bot, call.message.chat.id, state, (await state.get_data()).get('offset', 0))
            return

        logging.info(f"Deleted post {pid} from MongoDB for user {call.from_user.id}")
        await call.answer("✅ Оголошення успішно видалено.", show_alert=True)
    except Exception as e:
        logging.error(f"Failed to delete post from MongoDB: {e}", exc_info=True)
        await call.answer("❌ Вибачте, сталася помилка при видаленні оголошення.", show_alert=True)
        await show_my_posts_page(call.message.bot, call.message.chat.id, state, (await state.get_data()).get('offset', 0))
        return
    
    data = await state.get_data()
    current_offset = data.get('offset', 0)
    
    total_user_posts_after_delete = await db.posts.count_documents({'user_id': call.from_user.id})
    
    new_offset = current_offset
    
    if new_offset >= total_user_posts_after_delete and new_offset > 0:
        new_offset = max(0, new_offset - MY_POSTS_PER_PAGE)
    
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "🗑️ Оголошення успішно видалено\\!", parse_mode='MarkdownV2')
    await show_my_posts_page(call.message.bot, call.message.chat.id, state, new_offset)
    await state.set_state(AppStates.MY_POSTS_VIEW)


# ======== Допомога ========
@dp.callback_query_handler(lambda c: c.data=='help', state="*")
async def help_handler(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} requested help.")
    await call.answer()
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Написати @VILARSO18", url="https://t.me/VILARSO18"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_main_menu"))
    await update_or_send_interface_message(call.message.bot, call.message.chat.id, state, "💬 Для співпраці або допомоги пишіть \\@VILARSO18", kb, parse_mode='MarkdownV2') 
    await state.set_state(AppStates.MAIN_MENU) 

# Глобальний обробник для логування всіх callback_data та обробки скинутого стану
# Цей обробник має бути ПІСЛЯ всіх інших специфічних callback_query_handler-ів
@dp.callback_query_handler(state="*")
async def debug_all_callbacks(call: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    logging.info(f"DEBUG: Unhandled callback_data received: {call.data} from user {call.from_user.id} in state {current_state}")

    # Перевіряємо, чи стан користувача None (сесія скинута)
    if current_state is None:
        # Видаляємо повідомлення, на яке натиснув користувач, щоб прибрати старий інтерфейс
        try:
            await call.message.delete()
            logging.info(f"Deleted old message {call.message.message_id} for user {call.from_user.id} due to session reset.")
        except MessageToDeleteNotFound:
            logging.warning(f"Message {call.message.message_id} not found to delete for user {call.from_user.id}.")
        except Exception as e:
            logging.error(f"Error deleting message {call.message.message_id} for user {call.from_user.id}: {e}", exc_info=True)

        await call.answer("Ваша сесія була скинута. Будь ласка, почніть з головного меню.", show_alert=True)
        await go_to_main_menu(call.message.bot, call.message.chat.id, state)
        return # Важливо повернутися після обробки

    await call.answer() # Завжди відповідаємо на callback_query, щоб уникнути "крутячогося годинника"

# ======== Глобальний хендлер помилок ========
@dp.errors_handler()
async def err_handler(update: types.Update, exception):
    logging.error(f"Update: {update} caused error: {exception}", exc_info=True)
    
    chat_id = None
    bot_obj = None
    if update.callback_query and update.callback_query.message:
        chat_id = update.callback_query.message.chat.id
        bot_obj = update.callback_query.message.bot
    elif update.message:
        chat_id = update.message.chat.id
        bot_obj = update.message.bot

    if chat_id and bot_obj:
        if isinstance(exception, (BadRequest, TelegramAPIError)):
            if "Can't parse entities" in str(exception):
                logging.error("Markdown parse error detected. Ensure all user-supplied text is escaped.")
                await update_or_send_interface_message(bot_obj, chat_id, dp.current_state(), "Вибачте, сталася помилка з відображенням тексту\\. Можливо, в описі є некоректні символи\\.", main_kb(), parse_mode='MarkdownV2')
                await dp.current_state().set_state(AppStates.MAIN_MENU)
                return True
            elif "Text must be non-empty" in str(exception):
                logging.error("Message text is empty error detected.")
                await update_or_send_interface_message(bot_obj, chat_id, dp.current_state(), "Вибачте, сталася внутрішня помилка\\. Спробуйте ще раз\\.", main_kb())
                await dp.current_state().set_state(AppStates.MAIN_MENU)
                return True
            elif "message is not modified" in str(exception): 
                logging.info("Message was not modified, skipping update.")
                return True 
            elif "Too Many Requests: retry after" in str(exception):
                retry_after = int(re.search(r'retry after (\d+)', str(exception)).group(1))
                logging.warning(f"FloodWait for {retry_after} seconds for chat {chat_id}")
                await update_or_send_interface_message(bot_obj, chat_id, dp.current_state(), f"Забагато запитів\\. Будь ласка, зачекайте {retry_after} секунд перед наступною дією\\.", main_kb(), parse_mode='MarkdownV2')
                await dp.current_state().set_state(AppStates.MAIN_MENU)
                return True
        elif isinstance(exception, MessageNotModified):
            logging.info("Message was not modified, skipping update.")
            return True
        elif isinstance(exception, MessageToDeleteNotFound):
            logging.info("Message to delete not found, skipping.")
            return True

    logging.critical(f"Unhandled error: {exception}", exc_info=True)
    if chat_id and bot_obj:
        await update_or_send_interface_message(bot_obj, chat_id, dp.current_state(), "Вибачте, сталася неочікувана помилка\\. Спробуйте ще раз або зверніться до адміністратора\\.", main_kb())
        await dp.current_state().set_state(AppStates.MAIN_MENU)
    return True

async def on_startup(dp_obj):
    logging.info("Запуск бота...")
    await init_db_connection()

    WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"
    
    # Явно видаляємо вебхук перед встановленням нового
    try:
        await bot.delete_webhook()
        logging.info("Попередній вебхук успішно видалено.")
    except TelegramAPIError as e:
        logging.warning(f"Не вдалося видалити попередній вебхук (можливо, його не було): {e}")
    
    # Додаємо невелику паузу
    await asyncio.sleep(1)

    # Встановлюємо новий вебхук, скидаючи всі очікуючі оновлення
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    logging.info(f"Webhook встановлено: {WEBHOOK_URL}")

    # Перевірка статусу вебхука після встановлення
    try:
        webhook_info = await bot.get_webhook_info()
        logging.info(f"DEBUG: Webhook info after setup: {webhook_info}")
    except Exception as e:
        logging.error(f"DEBUG: Failed to get webhook info after setup: {e}", exc_info=True)


async def on_shutdown(dp_obj):
    logging.info("Вимкнення бота...")
    await bot.delete_webhook()
    logging.info("Вебхук видалено.")
    global db_client
    if db_client:
        db_client.close()
        logging.info("Підключення до MongoDB закрито.")

if __name__ == '__main__':
    logging.info("Starting webhook...")
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
