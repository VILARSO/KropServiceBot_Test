import re
from datetime import datetime, timedelta
from aiogram.types import Message, CallbackQuery
from aiogram.dispatcher import FSMContext
from aiogram.utils.exceptions import MessageNotModified, MessageToDeleteNotFound, BadRequest
from aiogram import Bot # Імпортуємо Bot для типізації
import motor.motor_asyncio # Додано імпорт motor для get_next_sequence_value
import logging # Додано імпорт logging

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
    Редагує останнє повідомлення бота або надсилає нове, якщо редагування неможливе.
    Перед надсиланням нового повідомлення намагається видалити попереднє повідомлення бота.
    """
    data = await state.get_data()
    last_bot_message_id = data.get('last_bot_message_id')

    # Спроба видалити попереднє повідомлення бота
    if last_bot_message_id:
        try:
            await bot_obj.delete_message(chat_id=chat_id, message_id=last_bot_message_id)
            logging.info(f"Deleted old message {last_bot_message_id} for user {chat_id}.")
            await state.update_data(last_bot_message_id=None) # Очищаємо ID після видалення
        except MessageToDeleteNotFound:
            logging.warning(f"Message {last_bot_message_id} not found to delete for user {chat_id}. It might have been deleted by user or Telegram.")
            await state.update_data(last_bot_message_id=None) # Очищаємо ID, якщо не знайдено
        except Exception as e:
            logging.error(f"Error deleting message {last_bot_message_id} for user {chat_id}: {e}", exc_info=True)
            # Якщо не вдалося видалити, все одно спробуємо надіслати нове повідомлення

    # Надсилаємо нове повідомлення
    try:
        message = await bot_obj.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            disable_web_page_preview=disable_web_page_preview
        )
        await state.update_data(last_bot_message_id=message.message_id)
        logging.info(f"Sent new interface message for user {chat_id}. Message ID: {message.message_id}")
    except Exception as e:
        logging.error(f"Failed to send new interface message for user {chat_id}: {e}", exc_info=True)
        # У випадку будь-якої іншої непередбаченої помилки, спробуйте надіслати нове повідомлення як останній варіант
        # Цей блок може бути надлишковим, оскільки ми вже намагаємося send_message вище.
        # Можна залишити для додаткової надійності, якщо перша спроба send_message також впала.
        try:
            message = await bot_obj.send_message( 
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode,
                disable_web_page_preview=disable_web_page_preview
            )
            await state.update_data(last_bot_message_id=message.message_id)
            logging.info(f"Sent new interface message (after unexpected error) for user {chat_id}. Message ID: {message.message_id}")
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
        upsert=True, # Створити документ, якщо його немає
        return_document=motor.motor_asyncio.ReturnDocument.AFTER # Повернути документ після оновлення
    )
    return result['sequence_value']
