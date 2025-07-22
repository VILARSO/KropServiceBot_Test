import re
from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified, MessageToDeleteNotFound, BadRequest
from aiogram import Bot # Імпортуємо Bot для типізації
import motor.motor_asyncio
from pymongo import ReturnDocument
import logging # ДОДАНО: Імпорт модуля logging
import asyncio # ДОДАНО: Імпорт asyncio для затримки

# Регулярний вираз для перевірки номера телефону (приклад: +380XXXXXXXXX)
phone_pattern = re.compile(r'^\+?\d{10,15}$')

def escape_markdown_v2(text: str) -> str:
    """Екранує спеціальні символи MarkdownV2 у тексті."""
    if not isinstance(text, str):
        return str(text) # Перетворюємо на рядок, якщо це не рядок
    
    # Символи, які потрібно екранувати
    # _ * [ ] ( ) ~ ` > # + - = | { } . !
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

async def update_or_send_interface_message(bot_obj: Bot, chat_id: int, state: FSMContext, text: str, reply_markup=None, parse_mode='HTML', disable_web_page_preview: bool = False):
    """
    Редагує існуюче повідомлення інтерфейсу або надсилає нове, якщо його немає.
    У випадку помилки редагування, намагається видалити старе повідомлення і надсилає нове.
    Зберігає ID останнього повідомлення бота для подальшого редагування.
    """
    data = await state.get_data()
    last_bot_message_id = data.get('last_bot_message_id')
    
    logging.info(f"Attempting to update/send message for user {chat_id}. Last message ID: {last_bot_message_id}")

    try:
        if last_bot_message_id:
            # Спроба відредагувати існуюче повідомлення
            message = await bot_obj.edit_message_text(
                chat_id=chat_id,
                message_id=last_bot_message_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            logging.info(f"Edited existing interface message {last_bot_message_id} for user {chat_id}.")
            await state.update_data(last_bot_message_id=message.message_id) # Оновлюємо ID (хоча він той самий)
        else:
            # Якщо немає останнього ID, надсилаємо нове повідомлення
            message = await bot_obj.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            await state.update_data(last_bot_message_id=message.message_id)
            logging.info(f"Sent new interface message {message.message_id} for user {chat_id} (no previous ID).")

    except MessageNotModified:
        logging.info(f"Message {last_bot_message_id} for user {chat_id} was not modified. Skipping update.")
        pass # Нічого не робимо, якщо повідомлення не змінилося

    except (MessageToDeleteNotFound, BadRequest) as e:
        # Цей блок виконується, якщо edit_message_text не вдалося
        # (наприклад, повідомлення не знайдено, або його не можна редагувати)
        logging.warning(f"Failed to edit message {last_bot_message_id} for user {chat_id} (Error: {e}). Attempting to delete and send new.")
        
        # Явно намагаємося видалити старе повідомлення, якщо його ID було відомо
        if last_bot_message_id:
            try:
                await bot_obj.delete_message(chat_id=chat_id, message_id=last_bot_message_id)
                logging.info(f"Successfully deleted old message {last_bot_message_id} after edit failure for user {chat_id}.")
                await asyncio.sleep(0.01) # Невелика затримка для обробки видалення клієнтом
            except MessageToDeleteNotFound:
                logging.warning(f"Old message {last_bot_message_id} already gone for user {chat_id}.")
            except Exception as delete_e:
                logging.error(f"Error trying to delete old message {last_bot_message_id} after edit failure for user {chat_id}: {delete_e}", exc_info=True)
        
        # Тепер надсилаємо нове повідомлення та оновлюємо стан
        message = await bot_obj.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
        logging.info(f"Sent new interface message {message.message_id} for user {chat_id} after edit failure and delete attempt.")

    except Exception as e:
        # Обробка будь-яких інших непередбачених помилок під час операцій з повідомленнями
        logging.critical(f"Unhandled error in update_or_send_interface_message for user {chat_id}: {e}", exc_info=True)
        # Як останній засіб, спробуйте надіслати нове повідомлення, не покладаючись на попередній стан
        try:
            message = await bot_obj.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            await state.update_data(last_bot_message_id=message.message_id)
            logging.info(f"Sent new interface message {message.message_id} for user {chat_id} after critical error.")
        except Exception as inner_e:
            logging.critical(f"CRITICAL: Failed to send message even after retry for user {chat_id}: {inner_e}", exc_info=True)


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
        return_document=ReturnDocument.AFTER
    )
    return result['sequence_value']
