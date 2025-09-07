from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_projects_menu():
    """Главное подменю раздела 'Проекты'"""
    keyboard = [
        [InlineKeyboardButton("📰 Публикации", callback_data="projects_publications")],
        [InlineKeyboardButton("✍ Одобрение и правки", callback_data="projects_edits")],
        [InlineKeyboardButton("📊 Итоги недели", callback_data="projects_summary")],
        [InlineKeyboardButton("📦 Архив", callback_data="projects_archive")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)