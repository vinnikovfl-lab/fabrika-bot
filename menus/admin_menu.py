# menus/admin_menu.py
# Полное меню админ-панели для бота «Фабрика Будущего».
# Кнопки и callback_data синхронизированы с handlers/admin.py.

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_admin_main_menu() -> InlineKeyboardMarkup:
    """
    Главное меню админ-панели.
    Разделы:
      - FAQ
      - Посты
      - Оплаты и подписки
      - Возврат в пользовательское меню
    """
    keyboard = [
        [InlineKeyboardButton("📖 FAQ", callback_data="admin_faq")],
        [InlineKeyboardButton("📂 Посты", callback_data="admin_posts")],
        [InlineKeyboardButton("💳 Оплаты и подписки", callback_data="admin_payments")],
        [InlineKeyboardButton("🔙 Пользовательское меню", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_faq_menu() -> InlineKeyboardMarkup:
    """
    Подменю управления FAQ:
      - Добавить FAQ
      - Список FAQ
      - Назад в админ-меню
    """
    keyboard = [
        [InlineKeyboardButton("➕ Добавить FAQ", callback_data="admin_faq_add")],
        [InlineKeyboardButton("📋 Список FAQ", callback_data="admin_faq_list")],
        [InlineKeyboardButton("🔙 В админ‑меню", callback_data="admin_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_posts_menu() -> InlineKeyboardMarkup:
    """
    Подменю управления постами:
      - Добавить пост
      - Список постов недели
      - Назад в админ-меню
    """
    keyboard = [
        [InlineKeyboardButton("➕ Добавить пост", callback_data="admin_post_add")],
        [InlineKeyboardButton("📋 Список постов недели", callback_data="admin_post_list")],
        [InlineKeyboardButton("🔙 В админ‑меню", callback_data="admin_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def get_admin_payments_menu() -> InlineKeyboardMarkup:
    """
    Подменю управления оплатами и подписками:
      - Добавить оплату
      - История оплат
      - Инфо подписки
      - Отменить подписку
      - Назад в админ-меню
    """
    keyboard = [
        [InlineKeyboardButton("➕ Добавить оплату", callback_data="admin_payment_add")],
        [InlineKeyboardButton("📊 История оплат", callback_data="admin_payment_history")],
        [InlineKeyboardButton("📅 Инфо подписки", callback_data="admin_sub_info")],
        [InlineKeyboardButton("🛑 Отменить подписку", callback_data="admin_sub_cancel")],
        [InlineKeyboardButton("🔙 В админ‑меню", callback_data="admin_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)