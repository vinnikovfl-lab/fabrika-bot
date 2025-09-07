from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_payments_menu():
    keyboard = [
        [InlineKeyboardButton("📅 Моя подписка", callback_data="payments_subscription")],
        [InlineKeyboardButton("📦 Тарифы", callback_data="payments_tariffs")],
        [InlineKeyboardButton("💳 Оплатить подписку", callback_data="payments_pay")],
        [InlineKeyboardButton("📈 История оплат", callback_data="payments_history")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_tariffs_menu():
    keyboard = [
        [InlineKeyboardButton("🟢 Базовый — 5000₽/мес", callback_data="payments_pay")],
        [InlineKeyboardButton("🔵 Продвинутый — 10 000₽/мес", callback_data="payments_pay")],
        [InlineKeyboardButton("🟣 Индивидуальный проект", url="https://t.me/fabricf_manager")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_payment")],
    ]
    return InlineKeyboardMarkup(keyboard)