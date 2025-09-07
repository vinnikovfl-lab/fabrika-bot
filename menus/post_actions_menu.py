from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_post_actions_menu(post_id: int):
    """Кнопки действий для поста"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{post_id}"),
            InlineKeyboardButton("✍ На правку", callback_data=f"reject_{post_id}"),
            InlineKeyboardButton("🔄 Заменить", callback_data=f"replace_{post_id}")
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data="projects_edits")]
    ]
    return InlineKeyboardMarkup(keyboard)