from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import CATEGORIES, TYPE_EMOJIS # Імпортуємо CATEGORIES та TYPE_EMOJIS з config

def main_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("➕ Додати", callback_data="add_post"),
        InlineKeyboardButton("🔍 Пошук", callback_data="view_posts"),
        InlineKeyboardButton("🗂️ Мої", callback_data="my_posts"),
        InlineKeyboardButton("❓ Допомога", callback_data="help"),
    )
    return kb

def back_kb():
    kb = InlineKeyboardMarkup()
    # Кнопка "Назад" завжди внизу
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step")) 
    return kb

def type_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Робота", callback_data="type_work"),
        InlineKeyboardButton("Послуга", callback_data="type_service"),
    )
    # Кнопка "Назад до головного меню" внизу
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_main_menu"))
    return kb

def categories_kb(is_post_creation=True):
    """
    Клавіатура для вибору категорії.
    :param is_post_creation: Якщо True, callback_data буде 'post_cat_X', інакше 'view_cat_X'.
    """
    kb = InlineKeyboardMarkup(row_width=1)
    for i, (lbl, _) in enumerate(CATEGORIES):
        cb = f"{'post' if is_post_creation else 'view'}_cat_{i}"
        kb.add(InlineKeyboardButton(lbl, callback_data=cb))
    # Кнопка "Назад" завжди внизу
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step")) 
    return kb

def contact_kb():
    kb = InlineKeyboardMarkup()
    kb.add(
        InlineKeyboardButton("❎ Пропустити", callback_data="skip_cont"),
    )
    # Кнопка "Назад" завжди внизу
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb

# Ці клавіатури не використовуються в поточній логіці, але залишені для повноти
def confirm_add_post_kb():
    """Клавіатура для підтвердження додавання оголошення."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Підтвердити", callback_data='confirm_add_post'),
        InlineKeyboardButton("❌ Скасувати", callback_data='cancel_add_post')
    )
    return kb

def post_actions_kb(post_id: int):
    """Клавіатура для дій з конкретним оголошенням (редагувати, видалити)."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✏️ Редагувати", callback_data=f'edit_{post_id}'),
        InlineKeyboardButton("🗑️ Видалити", callback_data=f'delete_{post_id}')
    )
    kb.add(InlineKeyboardButton("⬅️ Назад до моїх оголошень", callback_data='my_posts'))
    return kb

def edit_post_kb(post_id: int):
    """Клавіатура для вибору поля оголошення для редагування."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Опис", callback_data=f'edit_field_description_{post_id}'),
        InlineKeyboardButton("Контакт", callback_data=f'edit_field_contact_{post_id}')
    )
    kb.add(InlineKeyboardButton("⬅️ Назад до деталей оголошення", callback_data=f'post_details_{post_id}'))
    return kb

def pagination_kb(current_page: int, posts_per_page: int, total_posts: int, action_prefix: str, context_id: str | int):
    """
    Клавіатура для пагінації.
    :param current_page: Поточна сторінка (0-індекс).
    :param posts_per_page: Кількість оголошень на сторінці.
    :param total_posts: Загальна кількість оголошень.
    :param action_prefix: Префікс для callback_data (наприклад, 'view' або 'my').
    :param context_id: ID категорії або ID користувача для збереження контексту.
    """
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []

    has_prev = current_page > 0
    has_next = (current_page + 1) * posts_per_page < total_posts

    if has_prev:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'{action_prefix}_page_prev_{context_id}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    buttons.append(InlineKeyboardButton(f"Сторінка {current_page + 1}", callback_data='ignore'))

    if has_next:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'{action_prefix}_page_next_{context_id}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    kb.add(*buttons)
    if action_prefix == 'my':
        kb.add(InlineKeyboardButton("⬅️ Назад до головного меню", callback_data='go_back_to_main_menu'))
    else:
        kb.add(InlineKeyboardButton("⬅️ Назад до вибору категорії", callback_data='view_posts'))
    return kb

def confirm_delete_kb(post_id: int):
    """Клавіатура для підтвердження видалення оголошення."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Так, видалити", callback_data=f'confirm_delete_{post_id}'),
        InlineKeyboardButton("❌ Ні, скасувати", callback_data=f'cancel_delete_{post_id}')
    )
    return kb
