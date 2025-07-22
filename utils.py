import re
from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified, MessageToDeleteNotFound, BadRequest
from aiogram import Bot # Імпортуємо Bot для типізації
import logging # Додано імпорт logging
import asyncio # Додано імпорт asyncio для затримки (хоча для цього варіанту вона менш критична)

# Регулярний вираз для перевірки номера телефону (приклад: +380XXXXXXXXX)
# Це вже використовується в main.py, але залишено тут як приклад, якщо потрібно буде знову
phone_pattern = re.compile(r'^\+?\d{10,15}$')

def escape_markdown_v2(text: str) -> str:
    """
    Екранує спеціальні символи MarkdownV2 в тексті,
    які не повинні інтерпретуватися як форматування.
    """
    if not isinstance(text, str):
        text = str(text) 
    
    # Список всіх спеціальних символів MarkdownV2, які потребують екранування
    # https://core.telegram.org/bots/api#markdownv2-style
    special_chars = r'_*[]()~`>#+-=|{}.!' 
    
    # Використовуємо re.sub для більш ефективного екранування
    return re.sub(f'([{re.escape(special_chars)}])', r'\\\1', text)

async def update_or_send_interface_message(bot_obj: Bot, chat_id: int, state: FSMContext, text: str, reply_markup=None, parse_mode='HTML', disable_web_page_preview: bool = False):
    """
    Редагує існуюче повідомлення інтерфейсу або надсилає нове, якщо його немає.
    Зберігає message_id останнього повідомлення бота у стані.
    Приймає об'єкт bot як перший аргумент.
    """
    data = await state.get_data()
    last_bot_message_id = data.get('last_bot_message_id')

    try:
        if last_bot_message_id:
            # Спроба відредагувати існуюче повідомлення
            message = await bot_obj.edit_message_text( # Використовуємо переданий bot_obj
                chat_id=chat_id,
                message_id=last_bot_message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            logging.info(f"Edited existing interface message for user {chat_id}. Message ID: {last_bot_message_id}")
        else:
            # Надсилання нового повідомлення, якщо немає існуючого
            message = await bot_obj.send_message( # Використовуємо переданий bot_obj
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            await state.update_data(last_bot_message_id=message.message_id)
            logging.info(f"Sent new interface message for user {chat_id}. Message ID: {message.message_id}")
    except MessageNotModified:
        # Це нормальна ситуація, якщо текст або клавіатура не змінилися
        logging.info(f"Message not modified for user {chat_id}. Message ID: {last_bot_message_id}")
        pass 
    except (MessageToDeleteNotFound, BadRequest) as e:
        # Якщо повідомлення було видалено або є інші помилки редагування, надсилаємо нове
        logging.warning(f"Failed to edit message {last_bot_message_id} for user {chat_id} (Error: {e}). Sending new message.")
        message = await bot_obj.send_message( # Використовуємо переданий bot_obj
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
        logging.info(f"Sent new interface message (after edit failure) for user {chat_id}. Message ID: {message.message_id}")
    except Exception as e:
        logging.error(f"Unexpected error in update_or_send_interface_message for user {chat_id}: {e}", exc_info=True)
        # У випадку будь-якої іншої непередбаченої помилки, спробуйте надіслати нове повідомлення як останній варіант
        message = await bot_obj.send_message( # Використовуємо переданий bot_obj
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
        logging.info(f"Sent new interface message (after unexpected error) for user {chat_id}. Message ID: {message.message_id}")


def can_edit(post: dict) -> bool:
    """Перевіряє, чи можна редагувати оголошення (протягом 15 хвилин після створення)."""
    # MongoDB зберігає datetime об'єкти, тому прямо порівнюємо
    return datetime.utcnow() - post['created_at'] < timedelta(minutes=15)

async def get_next_sequence_value(db_obj, sequence_name: str) -> int:
    """
    Генерує послідовний цілочисловий ID за допомогою MongoDB-лічильника.
    Приймає об'єкт db (motor.core.AgnosticDatabase) як перший аргумент.
    """
    # Збільшуємо лічильник і повертаємо нове значення
    result = await db_obj.counters.find_one_and_update(
        {'_id': sequence_name},
        {'$inc': {'sequence_value': 1}},
        upsert=True, # Створити документ, якщо його немає
        return_document=motor.motor_asyncio.ReturnDocument.AFTER # Повернути документ після оновлення
    )
    return result['sequence_value']
