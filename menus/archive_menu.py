from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_archive_menu(week_num: int):
    """Кнопки для навигации по архиву"""
    keyboard = [
        [
            InlineKeyboardButton("⬅ Предыдущая", callback_data=f"archive_{week_num-1}"),
            InlineKeyboardButton("➡ Следующая", callback_data=f"archive_{week_num+1}")
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_projects")],
    ]
    return InlineKeyboardMarkup(keyboard)