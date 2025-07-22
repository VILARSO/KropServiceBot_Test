import os
import asyncio
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.types import (
    CallbackQuery, Message,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils.executor import start_webhook
from aiogram.utils.exceptions import (
    BadRequest, TelegramAPIError,
    MessageNotModified, MessageToDeleteNotFound
)

import motor.motor_asyncio
from motor.core import AgnosticClient, AgnosticDatabase
from pymongo import DESCENDING, ReturnDocument

from config import (
    API_TOKEN, MONGO_DB_URL, WEBHOOK_HOST, WEBHOOK_PATH,
    WEBAPP_HOST, WEBAPP_PORT, POST_LIFETIME_DAYS,
    MY_POSTS_PER_PAGE, VIEW_POSTS_PER_PAGE,
    CATEGORIES, TYPE_EMOJIS
)
from states import AppStates
from keyboards import (
    main_kb, categories_kb, search_type_kb,  # <-- ОНОВЛЕНО
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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
        db = db_client.cropservice_db  # назва вашої БД
        logging.info("MongoDB: OK")

        # Індекси
        await db.posts.create_index(
            "created_at",
            expireAfterSeconds=int(POST_LIFETIME_DAYS * 24 * 60 * 60)
        )
        await db.posts.create_index([("category", 1), ("created_at", DESCENDING)])
        await db.posts.create_index([("user_id", 1), ("created_at", DESCENDING)])
        await db.posts.create_index("id", unique=True)
        await db.counters.create_index("_id")
    except Exception as e:
        logging.critical(f"Mongo init error: {e}", exc_info=True)
        exit(1)

WELCOME_MESSAGE = (
    "👋 Привіт\\! Я CropServiceBot …\n\n"
    "➕ — Додати оголошення\n"
    "🔍 — Пошук оголошень\n"
    "🗂️ — Мої оголошення\n"
    "❓ — Допомога"
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
    logging.info(f"ViewPosts page for {chat_id}, offset={offset}")
    try:
        data = await state.get_data()
        cat = data.get('current_view_category')
        if not cat:
            return await go_to_main_menu(bot_obj, chat_id, state)

        # Формуємо запит з урахуванням type
        query = {'category': cat}
        if data.get('search_type'):
            query['type'] = data['search_type']

        total_posts = await db.posts.count_documents(query)
        cursor = db.posts.find(query) \
                         .sort([('created_at', DESCENDING)]) \
                         .skip(offset) \
                         .limit(VIEW_POSTS_PER_PAGE)
        page_posts = await cursor.to_list(length=VIEW_POSTS_PER_PAGE)

        if not page_posts:
            kb = InlineKeyboardMarkup(row_width=1).add(
                InlineKeyboardButton("⬅️ Назад до категорій", callback_data="go_back_to_prev_step"),
                InlineKeyboardButton("🏠 Головне меню",    callback_data="go_back_to_main_menu")
            )
            text = f"У категорії «{escape_markdown_v2(cat)}» поки що немає оголошень\\."
            return await update_or_send_interface_message(
                bot_obj, chat_id, state, text, kb,
                parse_mode='MarkdownV2'
            )

        await state.update_data(offset=offset)
        total_pages = (total_posts + VIEW_POSTS_PER_PAGE - 1) // VIEW_POSTS_PER_PAGE
        current_page = offset // VIEW_POSTS_PER_PAGE + 1

        full_text = (
            f"📋 **{escape_markdown_v2(cat)}** "
            f"\\(Стор {escape_markdown_v2(current_page)}/{escape_markdown_v2(total_pages)}\\)\n\n"
        )
        kb = pagination_kb(total_posts, offset, VIEW_POSTS_PER_PAGE, 'viewpage', cat)

        for i, p in enumerate(page_posts):
            emoji = TYPE_EMOJIS.get(p['type'], '')
            block = (
                f"ID: {escape_markdown_v2(p['id'])}\n"
                f"{emoji} **{escape_markdown_v2(p['type'].capitalize())}**\n"
                f"🔹 {escape_markdown_v2(p['description'])}\n"
            )
            if p['username']:
                if p['username'].isdigit():
                    block += "👤 Автор: \\_Приватний користувач\\_\n"
                else:
                    block += f"👤 Автор: \\@{escape_markdown_v2(p['username'])}\n"
            if p.get('contacts'):
                block += f"📞 Контакт: {escape_markdown_v2(p['contacts'])}\n"

            full_text += block
            if i < len(page_posts) - 1:
                full_text += "\n—\n\n"

        await update_or_send_interface_message(
            bot_obj, chat_id, state,
            full_text, kb,
            parse_mode='MarkdownV2',
            disable_web_page_preview=True
        )
    except Exception as e:
        logging.error(f"show_view_posts_page error: {e}", exc_info=True)
        await update_or_send_interface_message(
            bot_obj, chat_id, state,
            "Ошибка при показе объявлений. Спробуйте ще раз.",
            main_kb(),
            parse_mode='MarkdownV2'
        )
        await state.set_state(AppStates.MAIN_MENU)


# ————— ОДНО ЗМІНЕНЕ: ПЕРЕГЛЯД ОГОЛОШЕНЬ —————

@dp.callback_query_handler(lambda c: c.data == 'view_posts', state="*")
async def view_start(call: CallbackQuery, state: FSMContext):
    logging.info(f"{call.from_user.id} → View Posts")
    await call.answer()
    # Крок 1: вибір типу
    await update_or_send_interface_message(
        call.message.bot, call.message.chat.id, state,
        "🔎 Оберіть тип оголошень для пошуку:",
        search_type_kb()
    )
    await state.set_state(AppStates.SEARCH_TYPE)

@dp.callback_query_handler(lambda c: c.data.startswith('search_type:'), state=AppStates.SEARCH_TYPE)
async def process_search_type(call: CallbackQuery, state: FSMContext):
    logging.info(f"{call.from_user.id} → selected search_type: {call.data}")
    await call.answer()
    typ = call.data.split(':')[1]  # 'job' або 'service'
    await state.update_data(search_type=typ)
    # Крок 2: вибір категорії
    await update_or_send_interface_message(
        call.message.bot, call.message.chat.id, state,
        f"Тип «{'Робота' if typ=='job' else 'Послуга'}» обрано.\n🔎 Оберіть категорію:",
        categories_kb(is_post_creation=False)
    )
    await state.set_state(AppStates.VIEW_CAT)

@dp.callback_query_handler(lambda c: c.data.startswith('view_cat_'), state=AppStates.VIEW_CAT)
async def view_cat(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split('_')[2])
    cat_name = CATEGORIES[idx][1]
    logging.info(f"{call.from_user.id} → selected category: {cat_name}")
    await call.answer()
    await state.update_data(current_view_category=cat_name, current_category_idx=idx)
    await show_view_posts_page(call.message.bot, call.message.chat.id, state, 0)
    await state.set_state(AppStates.VIEW_LISTING)

@dp.callback_query_handler(lambda c: c.data.startswith('viewpage_'), state=AppStates.VIEW_LISTING)
async def view_paginate(call: CallbackQuery, state: FSMContext):
    await call.answer()
    offset = int(call.data.split('_')[1])
    await show_view_posts_page(call.message.bot, call.message.chat.id, state, offset)

# ————— ВСІ ІНШІ ОБРОБНИКИ БЕЗ ЗМІН —————
# add_post, my_posts, edit, delete, help, debug, error handlers, startup/shutdown …

if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT
    )
