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
    # Кнопка "Назад" тепер залежить від контексту:
    # При створенні оголошення повертає до вибору типу (ADD_TYPE)
    # При перегляді оголошень повертає до вибору типу (VIEW_TYPE)
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb

def type_kb() -> InlineKeyboardMarkup:
    """Клавіатура для вибору типу оголошення (робота/послуга) при ДОДАВАННІ."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"{TYPE_EMOJIS['робота']} Робота", callback_data='type_work'),
        InlineKeyboardButton(f"{TYPE_EMOJIS['послуга']} Послуга", callback_data='type_service')
    )
    kb.add(InlineKeyboardButton("⬅️ Назад", callback_data="go_back_to_prev_step"))
    return kb

def view_types_kb() -> InlineKeyboardMarkup:
    """Нова клавіатура для вибору типу оголошення (робота/послуга) при ПЕРЕГЛЯДІ."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(f"{TYPE_EMOJIS['робота']} Робота", callback_data='view_type_work'),
        InlineKeyboardButton(f"{TYPE_EMOJIS['послуга']} Послуга", callback_data='view_type_service')
    )
    kb.add(InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu")) # Прямий шлях до головного меню
    return kb

def confirm_add_post_kb() -> InlineKeyboardMarkup:
    """Клавіатура для підтвердження додавання оголошення."""
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("✅ Підтвердити", callback_data="confirm_add_post"),
        InlineKeyboardButton("❌ Скасувати", callback_data="go_back_to_main_menu")
    )
    return kb

def pagination_kb(total_posts: int, offset: int, posts_per_page: int, action_prefix: str, category: str = None, post_type: str = None) -> InlineKeyboardMarkup:
    """
    Клавіатура для пагінації.
    :param total_posts: Загальна кількість оголошень.
    :param offset: Зміщення для поточної сторінки (скільки оголошень пропущено).
    :param posts_per_page: Кількість оголошень на сторінці.
    :param action_prefix: Префікс для callback_data (наприклад, 'viewpage' або 'mypage').
    :param category: Назва категорії (для 'viewpage' оголошень).
    :param post_type: Тип оголошення (для 'viewpage' оголошень).
    """
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = []

    # Визначаємо, чи є попередня/наступна сторінка
    has_prev = offset > 0
    has_next = offset + posts_per_page < total_posts

    # Кнопка "Попередня"
    if has_prev:
        if action_prefix == 'viewpage':
            # Передаємо всі необхідні параметри для збереження фільтрів
            buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f'{action_prefix}_{offset - posts_per_page}_{category}_{post_type}'))
        else: # 'mypage'
            buttons.append(InlineKeyboardButton("⬅️ Попередня", callback_data=f'{action_prefix}_{offset - posts_per_page}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    # Кнопка поточної сторінки
    current_page_num = offset // posts_per_page + 1
    total_pages = (total_posts + posts_per_page - 1) // posts_per_page
    buttons.append(InlineKeyboardButton(f"Сторінка {current_page_num}/{total_pages}", callback_data='ignore'))

    # Кнопка "Наступна"
    if has_next:
        if action_prefix == 'viewpage':
            # Передаємо всі необхідні параметри для збереження фільтрів
            buttons.append(InlineKeyboardButton("Наступна ➡️", callback_data=f'{action_prefix}_{offset + posts_per_page}_{category}_{post_type}'))
        else: # 'mypage'
            buttons.append(InlineKeyboardButton("Наступна ➡️", callback_data=f'{action_prefix}_{offset + posts_per_page}'))
    else:
        buttons.append(InlineKeyboardButton(" ", callback_data='ignore')) # Пуста кнопка для вирівнювання

    kb.row(*buttons) # Додаємо кнопки пагінації в один ряд

    # Додаємо кнопки навігації "Назад" та "Головне меню"
    if action_prefix == 'viewpage':
        kb.add(InlineKeyboardButton("⬅️ Назад до категорій", callback_data='go_back_to_prev_step')) # Повертає до вибору категорії
        kb.add(InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu"))
    elif action_prefix == 'mypage':
        kb.add(InlineKeyboardButton("🏠 Головне меню", callback_data="go_back_to_main_menu"))
    
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
