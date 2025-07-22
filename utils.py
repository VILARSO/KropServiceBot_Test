import os
import re
import logging
from datetime import datetime, timedelta

from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import (
    MessageNotModified,
    MessageToDeleteNotFound,
    BadRequest
)
from aiogram import Bot  # для типізації
from pymongo import ReturnDocument
from motor.motor_asyncio import AsyncIOMotorClient

# ----------- Налаштування MongoDB -----------
MONGO_URI = os.getenv("MONGO_URI")            # має бути задано в середовищі
DB_NAME   = os.getenv("DB_NAME", "kropbot")   # за замовчуванням "kropbot"
client    = AsyncIOMotorClient(MONGO_URI)
db        = client[DB_NAME]
posts_collection = db["posts"]                # ваша колекція з оголошеннями
# ---------------------------------------------

# Регулярний вираз для перевірки номера телефону (+380XXXXXXXXX або без +)
phone_pattern = re.compile(r'^\+?\d{10,15}$')


def escape_markdown_v2(text: str) -> str:
    """
    Екранує спеціальні символи MarkdownV2 в тексті.
    """
    if not isinstance(text, str):
        text = str(text)

    special_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(special_chars)}])', r'\\\1', text)


async def update_or_send_interface_message(
    bot_obj: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_markup=None,
    parse_mode='HTML',
    disable_web_page_preview: bool = False
):
    """
    Редагує останнє повідомлення бота або надсилає нове.
    Зберігає ID останнього повідомлення для подальшого редагування.
    """
    data = await state.get_data()
    last_bot_message_id = data.get('last_bot_message_id')

    logging.info(
        f"[update_interface] User={chat_id} LastMsgID={last_bot_message_id}"
    )

    try:
        if last_bot_message_id:
            message = await bot_obj.edit_message_text(
                chat_id=chat_id,
                message_id=last_bot_message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
        else:
            message = await bot_obj.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )

        await state.update_data(last_bot_message_id=message.message_id)

    except MessageNotModified:
        logging.info(f"MessageNotModified for user {chat_id}, skipping edit.")
    except MessageToDeleteNotFound:
        logging.warning(f"MessageToDeleteNotFound for user {chat_id}, sending new.")
        message = await bot_obj.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
    except BadRequest as e:
        logging.error(f"BadRequest editing msg for user {chat_id}: {e}")
        message = await bot_obj.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
    except Exception as e:
        logging.critical(
            f"Unexpected error in update_interface for user {chat_id}: {e}",
            exc_info=True
        )
        message = await bot_obj.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)


def can_edit(post: dict) -> bool:
    """
    Перевіряє, чи можна редагувати оголошення
    (15 хв після created_at).
    """
    return datetime.utcnow() - post['created_at'] < timedelta(minutes=15)


async def get_next_sequence_value(db_obj, sequence_name: str) -> int:
    """
    Генерує послідовний ID через MongoDB лічильник.
    """
    result = await db_obj.counters.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'sequence_value': 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )
    return result['sequence_value']


async def get_posts(
    filter_dict: dict,
    limit: int = 5,
    last_created_at=None
) -> list:
    """
    Повертає список оголошень з фільтрацією:
      • filter_dict['type']     : "job" або "service"
      • filter_dict['category'] : категорія з CATEGORIES
      • last_created_at         : для пагінації (ISODate)
    """
    query = {}

    # 1) Фільтруємо за типом
    if filter_dict.get('type'):
        query['type'] = filter_dict['type']

    # 2) Фільтруємо за категорією
    if filter_dict.get('category'):
        query['category'] = filter_dict['category']

    # 3) Пагінація за датою
    if last_created_at:
        query['created_at'] = {'$lt': last_created_at}

    cursor = posts_collection.find(query) \
                              .sort("created_at", -1) \
                              .limit(limit)
    return await cursor.to_list(length=limit)
