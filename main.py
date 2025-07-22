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
from config import (
    API_TOKEN, MONGO_DB_URL, WEBHOOK_HOST, WEBHOOK_PATH,
    WEBAPP_HOST, WEBAPP_PORT, POST_LIFETIME_DAYS,
    MY_POSTS_PER_PAGE, VIEW_POSTS_PER_PAGE,
    CATEGORIES, TYPE_EMOJIS
)
from states import AppStates
from keyboards import (
    main_kb, categories_kb, search_type_kb,
    confirm_add_post_kb, post_actions_kb,
    edit_post_kb, pagination_kb,
    confirm_delete_kb, back_kb,
    type_kb, contact_kb
)

from utils import (
    escape_markdown_v2,
    update_or_send_interface_message,
    can_edit,
    get_next_sequence_value
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logging.getLogger().addHandler(logging.StreamHandler())

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

db_client: AgnosticClient = None
db: AgnosticDatabase = None

async def init_db_connection():
    global db_client, db
    try:
        logging.info("Підключення до MongoDB...")
        db_client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_DB_URL)
        db = db_client.cropservice_db  # назва вашої бази
        logging.info("Підключення до MongoDB успішно встановлено.")

        await db.posts.create_index("created_at", expireAfterSeconds=int(POST_LIFETIME_DAYS * 24 * 60 * 60))
        await db.posts.create_index([("category", 1), ("created_at", DESCENDING)])
        await db.posts.create_index([("user_id", 1), ("created_at", DESCENDING)])
        await db.posts.create_index("id", unique=True)
        await db.counters.create_index("_id")

    except Exception as e:
        logging.critical(f"Помилка підключення до MongoDB або створення індексів: {e}", exc_info=True)
        exit(1)


WELCOME_MESSAGE = (
    "👋 Привіт\\! Я CropServiceBot — допомагаю знаходити підробітки або виконавців у твоєму місті\\.\n\n"
    "➕ \\— Додати оголошення\n"
    "🔍 \\— Пошук оголошень\n"
    "🗂️ \\— Мої оголошення\n"
    "❓ \\— Допомога"
)

async def go_to_main_menu(bot_obj: Bot, chat_id: int, state: FSMContext):
    await update_or_send_interface_message(
        bot_obj, chat_id, state,
        WELCOME_MESSAGE,
        main_kb(),
        parse_mode='MarkdownV2'
    )
    await state.set_state(AppStates.MAIN_MENU)

async def show_view_posts_page(bot_obj: Bot, chat_id: int, state: FSMContext, offset: int = 0):
    logging.info(f"Showing view posts page for user {chat_id}, offset {offset}")
    try:
        data = await state.get_data()
        cat = data.get('current_view_category')
        if not cat:
            return await go_to_main_menu(bot_obj, chat_id, state)

        # Підготовка запиту з урахуванням типу
        count_query = {'category': cat}
        if data.get('search_type'):
            count_query['type'] = data['search_type']

        total_posts = await db.posts.count_documents(count_query)
        posts_cursor = db.posts.find(count_query) \
                                .sort([('created_at', DESCENDING)]) \
                                .skip(offset) \
                                .limit(VIEW_POSTS_PER_PAGE)
        page_posts = await posts_cursor.to_list(length=VIEW_POSTS_PER_PAGE)

        if not page_posts:
            kb = InlineKeyboardMarkup(row_width=1).add(
                InlineKeyboardButton("⬅️ Назад до категорій", callback_data="go_back_to_prev_step"),
                InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu")
            )
            text_to_send = f"У категорії «{escape_markdown_v2(cat)}» поки що немає оголошень\\."
            return await update_or_send_interface_message(
                bot_obj, chat_id, state,
                text_to_send, kb,
                parse_mode='MarkdownV2'
            )

        await state.update_data(offset=offset)
        total_pages = (total_posts + VIEW_POSTS_PER_PAGE - 1) // VIEW_POSTS_PER_PAGE
        current_page = offset // VIEW_POSTS_PER_PAGE + 1

        full_text = (
            f"📋 **{escape_markdown_v2(cat)}** "
            f"\\(Сторінка {escape_markdown_v2(current_page)}/{escape_markdown_v2(total_pages)}\\)\n\n"
        )
        combined_keyboard = pagination_kb(
            total_posts, offset, VIEW_POSTS_PER_PAGE,
            'viewpage', cat
        )

        for i, p in enumerate(page_posts):
            type_emoji = TYPE_EMOJIS.get(p['type'], '')
            post_block = (
                f"ID: {escape_markdown_v2(p['id'])}\n"
                f"{type_emoji} **{escape_markdown_v2(p['type'].capitalize())}**\n"
                f"🔹 {escape_markdown_v2(p['description'])}\n"
            )
            if p['username']:
                if p['username'].isdigit():
                    post_block += "👤 Автор: \\_Приватний користувач\\_\n"
                else:
                    post_block += f"👤 Автор: \\@{escape_markdown_v2(p['username'])}\n"
            if p.get('contacts'):
                post_block += f"📞 Контакт: {escape_markdown_v2(p['contacts'])}\n"

            full_text += post_block
            if i < len(page_posts) - 1:
                full_text += "\n—\n\n"

        await update_or_send_interface_message(
            bot_obj, chat_id, state,
            full_text, combined_keyboard,
            parse_mode='MarkdownV2',
            disable_web_page_preview=True
        )

    except Exception as e:
        logging.error(f"Error in show_view_posts_page for user {chat_id}: {e}", exc_info=True)
        await update_or_send_interface_message(
            bot_obj, chat_id, state,
            "Вибачте, сталася неочікувана помилка при перегляді оголошень\\. Спробуйте ще раз\\.",
            main_kb(),
            parse_mode='MarkdownV2'
        )
        await state.set_state(AppStates.MAIN_MENU)


async def show_my_posts_page(bot_obj: Bot, chat_id: int, state: FSMContext, offset: int = 0):
    # (залишаємо без змін)
    ...


# ======== Обробники команд ========
@dp.message_handler(commands=['start'], state="*")
async def on_start(msg: types.Message, state: FSMContext):
    # (залишаємо без змін)
    ...


@dp.callback_query_handler(lambda c: c.data == 'go_back_to_main_menu', state='*')
async def on_back_to_main(call: CallbackQuery, state: FSMContext):
    # (залишаємо без змін)
    ...


@dp.callback_query_handler(lambda c: c.data == 'go_back_to_prev_step', state='*')
async def on_back_to_prev_step(call: CallbackQuery, state: FSMContext):
    # (залишаємо без змін)
    ...


@dp.callback_query_handler(lambda c: c.data == 'add_post', state="*")
async def add_start(call: CallbackQuery, state: FSMContext):
    # (залишаємо без змін)
    ...


# … всі існуючі обробники додавання …

# ======== Перегляд оголошень ========
@dp.callback_query_handler(lambda c: c.data == 'view_posts', state="*")
async def view_start(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} initiated 'View Posts'.")
    await call.answer()
    # крок 1: обираємо тип
    await update_or_send_interface_message(
        call.message.bot, call.message.chat.id, state,
        "🔎 Оберіть тип оголошень для пошуку:",
        search_type_kb()
    )
    await state.set_state(AppStates.SEARCH_TYPE)

@dp.callback_query_handler(lambda c: c.data.startswith('search_type:'), state=AppStates.SEARCH_TYPE)
async def process_search_type(call: CallbackQuery, state: FSMContext):
    logging.info(f"User {call.from_user.id} selected search type: {call.data}.")
    await call.answer()
    type_value = call.data.split(':')[1]  # 'job' або 'service'
    await state.update_data(search_type=type_value)
    # крок 2: обираємо категорію
    await update_or_send_interface_message(
        call.message.bot, call.message.chat.id, state,
        f"Тип «{'Робота' if type_value=='job' else 'Послуга'}» обрано.\n🔎 Оберіть категорію:",
        categories_kb(is_post_creation=False)
    )
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
        # Перевіряємо, чи callback_data схожа на ту, що очікується в певних станах
        sub_menu_callbacks = [
            'type_', 'post_cat_', 'view_cat_', 'viewpage_', 'mypage_',
            'edit_', 'delete_', 'skip_cont', 'confirm_add_post', 'cancel_add_post', 'confirm_delete_', 'cancel_delete_'
        ]
        
        is_sub_menu_callback = any(call.data.startswith(prefix) for prefix in sub_menu_callbacks)

        if is_sub_menu_callback:
            # Видаляємо попереднє повідомлення перед тим, як надіслати нове головне меню
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
