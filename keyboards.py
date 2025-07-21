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
    kb = InlineKeyboardMarkup(row_width=2)
    for i, (emoji, cat_name) in enumerate(CATEGORIES):
        prefix = "post_cat" if is_post_creation else "view_cat"
        kb.add(InlineKeyboardButton(f"{emoji} {cat_name}", callback_data=f"{prefix}_{i}"))
    # Кнопка "Назад до головного меню" внизу
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_main_menu"))
    return kb

def confirm_add_post_kb():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_add_post"),
        InlineKeyboardButton("❌ Скасувати", callback_data="cancel_add_post")
    )
    return kb

def post_actions_kb(post_id: int, can_edit_flag: bool):
    kb = InlineKeyboardMarkup(row_width=2)
    if can_edit_flag:
        kb.add(InlineKeyboardButton("✏️ Редагувати", callback_data=f"edit_{post_id}"))
    kb.add(InlineKeyboardButton("🗑️ Видалити", callback_data=f"delete_{post_id}"))
    kb.add(InlineKeyboardButton("⬅️ Назад до моїх оголошень", callback_data="my_posts")) # Кнопка назад
    return kb

def edit_post_kb(post_id: int):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("✏️ Редагувати опис", callback_data=f"edit_desc_{post_id}"),
        InlineKeyboardButton("⬅️ Назад", callback_data=f"my_posts") # Повернутись до списку моїх оголошень
    )
    return kb

def pagination_kb(total_posts: int, current_offset: int, posts_per_page: int, action_prefix: str, context_id: str):
    """
    Генерує клавіатуру для пагінації.
    :param total_posts: Загальна кількість оголошень.
    :param current_offset: Поточний відступ (offset).
    :param posts_per_page: Кількість оголошень на сторінці.
    :param action_prefix: Префікс для callback_data ('viewpage' або 'mypage').
    :param context_id: ID категорії або ID користувача для збереження контексту (не використовується для пагінації).
    """
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []

    has_prev = current_offset > 0
    has_next = (current_offset + posts_per_page) < total_posts

    # Створюємо callback_data, що відповідає обробникам у main.py
    if has_prev:
        buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data=f'{action_prefix}_{current_offset - posts_per_page}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    current_page_num = (current_offset // posts_per_page) + 1
    total_pages = (total_posts + posts_per_page - 1) // posts_per_page
    buttons.append(InlineKeyboardButton(f"Сторінка {current_page_num}/{total_pages}", callback_data='ignore'))

    if has_next:
        buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'{action_prefix}_{current_offset + posts_per_page}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    kb.add(*buttons)
    if action_prefix == 'mypage': # Для моїх оголошень
        kb.add(InlineKeyboardButton("⬅️ Назад до головного меню", callback_data='go_back_to_main_menu'))
    else: # Для перегляду оголошень
        kb.add(InlineKeyboardButton("⬅️ Назад до вибору категорії", callback_data='view_posts'))
    return kb


def confirm_delete_kb(post_id: int):
    """Клавіатура для підтвердження видалення оголошення."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Так, видалити", callback_data=f"confirm_delete_{post_id}"),
        InlineKeyboardButton("❌ Скасувати", callback_data=f"cancel_delete_{post_id}")
    )
    return kb

def contact_kb():
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Пропустити", callback_data="skip_cont"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb
