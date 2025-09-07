from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
from menus.posts_menu import get_posts_menu


# === Главное меню (остается как было) ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    kb = [
        [InlineKeyboardButton("📂 Публикации", callback_data="menu_posts")],
        [InlineKeyboardButton("✍ Одобрение и правки", callback_data="menu_approve")],
        [InlineKeyboardButton("💰 Оплата", callback_data="menu_payment")],
        [InlineKeyboardButton("🆘 Помощь", url="https://t.me/fabricf_manager")],
    ]
    await update.message.reply_text(
        "👋 Добро пожаловать в «Фабрику Будущего»!\nВыберите раздел 👇",
        reply_markup=InlineKeyboardMarkup(kb)
    )


# === Меню публикаций ===
async def menu_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📂 Раздел публикаций:", reply_markup=get_posts_menu())


# === Обработчики кнопок ===
async def view_current_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📅 Показ публикаций за текущую неделю (заглушка)")


async def view_archive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📦 Архив публикаций (заглушка)")


async def create_week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📊 Итоги недели (заглушка)")


# === Регистрируем все обработчики ===
def get_handler():
    return [
        CallbackQueryHandler(menu_posts, pattern="^menu_posts$"),
        CallbackQueryHandler(view_current_posts, pattern="^posts_view_current$"),
        CallbackQueryHandler(view_archive, pattern="^posts_view_archive$"),
        CallbackQueryHandler(create_week_summary, pattern="^posts_create_week$"),
    ]