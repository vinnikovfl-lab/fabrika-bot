# handlers/help.py
# Полный файл: пользовательский раздел «Помощь»
# Возможности:
# - Быстрый FAQ (чтение из базы)
# - Контакт менеджера (username из ENV)
# - Аккуратная навигация кнопками

import os
import logging
from typing import List, Tuple, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from services import help as help_service

logger = logging.getLogger(__name__)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "FabricF_Manager").strip()

# -------------------------
# Меню раздела «Помощь»
# -------------------------
def get_help_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📖 FAQ", callback_data="help_faq")],
        [InlineKeyboardButton("👤 Связаться с менеджером", callback_data="help_contact")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------
# Корневой экран помощи
# -------------------------
async def help_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🆘 Помощь\n\n"
        "Здесь вы найдёте быстрые ответы и контакты менеджера."
    )
    await query.edit_message_text(text, reply_markup=get_help_menu())

# -------------------------
# FAQ
# -------------------------
async def help_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    try:
        rows: List[Tuple[int, str, str, str]] = await help_service.get_faq(limit=10, offset=0)
        if not rows:
            text = "📖 FAQ пока пуст. Задайте вопрос менеджеру."
        else:
            parts = ["📖 Топ вопросов:\n"]
            for row in rows:
                faq_id, question, answer, created_at = row
                parts.append(f"❓ {question}\n💡 {answer}\n")
            text = "\n".join(parts)
    except Exception as e:
        logger.exception("help_faq failed")
        text = f"❌ Ошибка при загрузке FAQ: {e}"

    await query.edit_message_text(text, reply_markup=get_help_menu())

# -------------------------
# Контакт менеджера
# -------------------------
async def help_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "👤 Связаться с менеджером\n\n"
        f"Напишите: @{ADMIN_USERNAME}\n"
        "Обычно отвечаем в течение пары часов."
    )
    await query.edit_message_text(text, reply_markup=get_help_menu())

# -------------------------
# Экспорт хендлеров
# -------------------------
def get_help_handlers():
    return [
        CallbackQueryHandler(help_root, pattern="^menu_help$"),
        CallbackQueryHandler(help_faq, pattern="^help_faq$"),
        CallbackQueryHandler(help_contact, pattern="^help_contact$"),
    ]