from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from config import CATEGORIES, MY_POSTS_PER_PAGE, VIEW_POSTS_PER_PAGE, TYPE_EMOJIS

def main_kb() -> InlineKeyboardMarkup:
    """Головне меню бота."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("➕ Додати оголошення", callback_data='add_post'),
        InlineKeyboardButton("👀 Переглянути оголошення", callback_data='view_posts'),
        InlineKeyboardButton("📝 Мої оголошення", callback_data='my_posts'),
        InlineKeyboardButton("❓ Допомога", callback_data='help')
    )
    return kb

def categories_kb(is_post_creation: bool) -> InlineKeyboardMarkup:
    """Клавіатура для вибору категорії."""
    kb = InlineKeyboardMarkup(row_width=2)
    buttons = []
    for i, cat in enumerate(CATEGORIES): # Перебираємо список категорій (рядків)
        if is_post_creation:
            buttons.append(InlineKeyboardButton(cat, callback_data=f'post_cat_{i}'))
        else:
            buttons.append(InlineKeyboardButton(cat, callback_data=f'view_cat_{i}'))
    kb.add(*buttons)
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb

def type_kb() -> InlineKeyboardMarkup:
    """Клавіатура для вибору типу оголошення (робота/послуга)."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"{TYPE_EMOJIS['робота']} Робота", callback_data='type_work'),
        InlineKeyboardButton(f"{TYPE_EMOJIS['послуга']} Послуга", callback_data='type_service')
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb

def view_types_kb() -> InlineKeyboardMarkup:
    """Нова клавіатура для вибору типу оголошення при перегляді."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"{TYPE_EMOJIS['робота']} Робота", callback_data='view_type_work'),
        InlineKeyboardButton(f"{TYPE_EMOJIS['послуга']} Послуга", callback_data='view_type_service')
    )
    kb.add(InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu"))
    return kb

def confirm_add_post_kb() -> InlineKeyboardMarkup:
    """Клавіатура для підтвердження додавання оголошення."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_add_post"),
        InlineKeyboardButton("❌ Скасувати", callback_data="go_back_to_main_menu")
    )
    return kb

def pagination_kb(current_page: int, posts_per_page: int, total_posts: int, action_prefix: str, category: str = None, post_type: str = None) -> InlineKeyboardMarkup:
    """
    Клавіатура для пагінації.
    :param current_page: Поточна сторінка (0-індекс).
    :param posts_per_page: Кількість оголошень на сторінці.
    :param total_posts: Загальна кількість оголошень.
    :param action_prefix: Префікс для callback_data (наприклад, 'view' або 'my').
    :param category: Назва категорії (для 'view' оголошень).
    :param post_type: Тип оголошення (для 'view' оголошень).
    """
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []

    has_prev = current_page > 0
    has_next = (current_page + 1) * posts_per_page < total_posts

    if has_prev:
        if action_prefix == 'view':
            buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f'{action_prefix}_page_{current_page - 1}_{category}_{post_type}'))
        else: # 'my'
            buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f'{action_prefix}_page_{current_page - 1}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    buttons.append(InlineKeyboardButton(f"Сторінка {current_page + 1}", callback_data='ignore'))

    if has_next:
        if action_prefix == 'view':
            buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'{action_prefix}_page_{current_page + 1}_{category}_{post_type}'))
        else: # 'my'
            buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data=f'{action_prefix}_page_{current_page + 1}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    kb.add(*buttons)

    if action_prefix == 'my':
        kb.add(InlineKeyboardButton("⬅️ Назад до головного меню", callback_data='go_back_to_main_menu'))
    elif action_prefix == 'view':
        # Коли переглядаємо, якщо ми обираємо категорію, нам потрібно повернутися до вибору типу, а не одразу до головного меню.
        kb.add(InlineKeyboardButton("⬅️ Назад до вибору категорії", callback_data='go_back_to_prev_step')) # Це поверне користувача до вибору типу, якщо поточний стан VIEW_POSTS_CATEGORY
        kb.add(InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu")) # Також надаємо прямий шлях до головного меню
    return kb

def post_actions_kb(post_id: int) -> InlineKeyboardMarkup:
    """Клавіатура для дій з конкретним оголошенням (редагувати, видалити)."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✏️ Редагувати", callback_data=f'edit_{post_id}'),
        InlineKeyboardButton("🗑️ Видалити", callback_data=f'delete_{post_id}')
    )
    kb.add(InlineKeyboardButton("⬅️ Назад до моїх оголошень", callback_data='my_posts'))
    return kb

def edit_post_kb(post_id: int) -> InlineKeyboardMarkup:
    """Клавіатура для вибору поля оголошення для редагування."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Опис", callback_data=f'edit_desc_{post_id}')
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data=f"my_posts"))
    return kb

def confirm_delete_kb(post_id: int) -> InlineKeyboardMarkup:
    """Клавіатура для підтвердження видалення оголошення."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Так, видалити", callback_data=f'confirm_delete_{post_id}'),
        InlineKeyboardButton("❌ Ні, скасувати", callback_data=f'cancel_delete_{post_id}')
    )
    return kb

def contact_kb() -> InlineKeyboardMarkup:
    """Клавіатура для пропуску введення контакту."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("Пропустити", callback_data="skip_cont"))
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb

def back_kb() -> InlineKeyboardMarkup:
    """Універсальна клавіатура з кнопкою "Назад"."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb
