# handlers/payments.py
# Полный файл: пользовательский раздел «Оплата»
# Возможности:
# - Статус подписки (по текущему пользователю)
# - История оплат (по текущему пользователю)
# - Кнопка «Оплатить» — плейсхолдер под ЮKassa (сообщение с инструкцией)

import os
import logging
from typing import List, Tuple, Any

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CallbackQueryHandler

from services import payments as payments_service

logger = logging.getLogger(__name__)

# Можно использовать ENV для будущей интеграции
CURRENCY = os.getenv("CURRENCY", "RUB")

# -------------------------
# Меню раздела «Оплата»
# -------------------------
def get_user_payments_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📅 Статус подписки", callback_data="pay_status")],
        [InlineKeyboardButton("📊 История оплат", callback_data="pay_history")],
        [InlineKeyboardButton("💳 Оплатить (ЮKassa)", callback_data="pay_pay")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------
# Корневой экран оплаты
# -------------------------
async def payments_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "💰 Оплата и подписка\n\n"
        "Здесь вы можете посмотреть статус подписки, историю оплат и оформить оплату."
    )
    await query.edit_message_text(text, reply_markup=get_user_payments_menu())

# -------------------------
# Статус подписки
# -------------------------
async def payments_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    try:
        sub = await payments_service.get_subscription(user_id)
        if not sub:
            text = (
                "📅 Подписка не оформлена.\n\n"
                "Нажмите «Оплатить (ЮKassa)», чтобы активировать подписку."
            )
        else:
            uid, plan, price, status, next_charge_at = sub
            when = next_charge_at.strftime('%d.%m.%Y') if hasattr(next_charge_at, "strftime") else (next_charge_at or "—")
            text = (
                f"📅 Ваша подписка\n\n"
                f"🔹 Тариф: {plan}\n"
                f"💵 Цена: {price} {CURRENCY}\n"
                f"📌 Статус: {status}\n"
                f"📆 Следующее списание: {when}"
            )
    except Exception as e:
        logger.exception("payments_status failed")
        text = f"❌ Ошибка при получении статуса подписки: {e}"

    await query.edit_message_text(text, reply_markup=get_user_payments_menu())

# -------------------------
# История оплат
# -------------------------
async def payments_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    try:
        await payments_service.init_db()
        rows: List[Tuple[float, str, str, Any]] = await payments_service.get_payments(user_id)
        if not rows:
            text = "📊 История оплат пуста."
        else:
            out = ["📊 История оплат:\n"]
            for amount, currency, desc, created_at in rows:
                when = created_at.strftime('%d.%m.%Y') if hasattr(created_at, "strftime") else str(created_at)
                out.append(f"💵 {currency} {amount} — {desc} ({when})")
            text = "\n".join(out)
    except Exception as e:
        logger.exception("payments_history failed")
        text = f"❌ Ошибка при получении истории оплат: {e}"

    await query.edit_message_text(text, reply_markup=get_user_payments_menu())

# -------------------------
# Оплатить (плейсхолдер ЮKassa)
# -------------------------
async def payments_pay(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Здесь будет интеграция ЮKassa (создание платежа, получение ссылки).
    # Пока безопасный плейсхолдер без внешних URL.
    text = (
        "💳 Оплата через ЮKassa\n\n"
        "Скоро здесь появится удобная ссылка на оплату. "
        "Пока что свяжитесь с менеджером для выставления счёта.\n\n"
        "После оплаты подписка активируется автоматически."
    )
    await query.edit_message_text(text, reply_markup=get_user_payments_menu())

# -------------------------
# Экспорт хендлеров
# -------------------------
def get_payment_handlers():
    return [
        CallbackQueryHandler(payments_root, pattern="^menu_payments$"),
        CallbackQueryHandler(payments_status, pattern="^pay_status$"),
        CallbackQueryHandler(payments_history, pattern="^pay_history$"),
        CallbackQueryHandler(payments_pay, pattern="^pay_pay$"),
    ]