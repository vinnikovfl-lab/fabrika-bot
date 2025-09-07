from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_posts_menu():
    """Возвращает inline-меню для раздела публикаций"""
    keyboard = [
        [InlineKeyboardButton("📅 Текущая неделя", callback_data="posts_view_current")],
        [InlineKeyboardButton("📦 Архив", callback_data="posts_view_archive")],
        [InlineKeyboardButton("📊 Итоги недели", callback_data="posts_create_week")]
    ]
    return InlineKeyboardMarkup(keyboard)