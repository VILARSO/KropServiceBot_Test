import re
from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified, MessageToDeleteNotFound, BadRequest
from aiogram import Bot # Імпортуємо Bot для типізації
import motor.motor_asyncio # Додано імпорт motor для get_next_sequence_value
from pymongo import ReturnDocument # ДОДАНО: Імпорт ReturnDocument з pymongo

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
    Редагує останнє повідомлення бота, якщо можливо, або надсилає нове.
    Зберігає ID останнього повідомлення бота для подальшого редагування.
    """
    data = await state.get_data()
    last_bot_message_id = data.get('last_bot_message_id')
    
    # Логування для налагодження
    logging.info(f"Attempting to update/send message for user {chat_id}. Last message ID: {last_bot_message_id}")

    try:
        if last_bot_message_id:
            # Спроба редагувати існуюче повідомлення
            message = await bot_obj.edit_message_text( # Використовуємо переданий bot_obj
                chat_id=chat_id,
                message_id=last_bot_message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            # logging.info(f"Updated interface message for user {chat_id}. Message ID: {message.message_id}")
        else:
            # Якщо немає останнього ID, або сталася помилка редагування, надсилаємо нове повідомлення
            message = await bot_obj.send_message( # Використовуємо переданий bot_obj
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            # logging.info(f"Sent new interface message for user {chat_id}. Message ID: {message.message_id}")
        
        await state.update_data(last_bot_message_id=message.message_id)

    except MessageNotModified:
        logging.info(f"Message for user {chat_id} was not modified. Skipping update.")
        pass # Нічого не робимо, якщо повідомлення не змінилося
    except MessageToDeleteNotFound:
        logging.warning(f"Message to delete not found for user {chat_id}. Sending new message.")
        message = await bot_obj.send_message( # Використовуємо переданий bot_obj
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
    except BadRequest as e:
        # Обробка інших BadRequest помилок, наприклад, "Message can't be edited"
        logging.error(f"BadRequest when updating message for user {chat_id}: {e}")
        message = await bot_obj.send_message( # Використовуємо переданий bot_obj
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
    except Exception as e:
        logging.critical(f"Unexpected error in update_or_send_interface_message for user {chat_id}: {e}", exc_info=True)
        # У випадку будь-якої іншої непередбаченої помилки, спробуйте надіслати нове повідомлення як останній варіант
        message = await bot_obj.send_message( # Використовуємо переданий bot_obj
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
        # logging.info(f"Sent new interface message (after unexpected error) for user {chat_id}. Message ID: {new_msg.message_id}")

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
        upsert=True,
        return_document=ReturnDocument.AFTER # ВИПРАВЛЕНО: Використовуємо ReturnDocument
    )
    return result['sequence_value']
