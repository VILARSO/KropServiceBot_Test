
from aiogram.dispatcher.filters.state import State, StatesGroup

class AppStates(StatesGroup):
    MAIN_MENU = State() # Головне меню
    ADD_TYPE = State()
    ADD_CAT = State()
    ADD_DESC = State()
    ADD_CONT = State()
    ADD_CONFIRM = State()

    VIEW_CAT = State()
    VIEW_LISTING = State() # Цей стан тепер знову для пагінації загальних оголошень
    
    MY_POSTS_VIEW = State()
    EDIT_DESC = State()

# Для пошуку за типом
    SEARCH_TYPE = State()       # крок 1: обрати “робота”/“послуга”
    SEARCH_CATEGORY = State()   # крок 2: обрати категорію
