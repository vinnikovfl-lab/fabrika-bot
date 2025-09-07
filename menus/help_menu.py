from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_help_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Связаться с менеджером", callback_data="help_contact")],
        [InlineKeyboardButton("📖 FAQ", callback_data="help_faq")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ])


def get_faq_menu(rows):
    """Строим меню FAQ из базы"""
    faq_buttons = []
    for row in rows:
        faq_buttons.append([InlineKeyboardButton(f"❓ {row[1]}", callback_data=f"faq_{row[0]}")])

    faq_buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="menu_help")])
    return InlineKeyboardMarkup(faq_buttons)


def get_back_to_faq_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад в FAQ", callback_data="help_faq")],
        [InlineKeyboardButton("🏠 Главное меню помощи", callback_data="menu_help")],
    ])