# handlers/admin.py
# Админ‑панель для бота «Фабрика Будущего»
# Workflow согласования постов (on_review -> approved/revisions/scheduled/published/archived)
# ВАЖНО: текстовый роутер админки зарегистрирован с block=False, чтобы не перехватывать клиентские сценарии.

import logging
from typing import Callable, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from menus.admin_menu import (
    get_admin_main_menu,
    get_admin_faq_menu,
    get_admin_posts_menu,
    get_admin_payments_menu,
)

from services import help as help_service
from services import posts as posts_service
from services import payments as payments_service

logger = logging.getLogger(__name__)

# ------------------------------------------------
# Обёртка проверки прав: инъекция is_admin_user
# ------------------------------------------------
def ensure_admin(func, is_admin_user: Callable):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user if update.effective_user else None
        if not user or not is_admin_user(user):
            if update.message:
                await update.message.reply_text("❌ Доступ запрещён")
            elif update.callback_query:
                await update.callback_query.answer("❌ Доступ запрещён", show_alert=True)
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

# ------------------------------------------------
# Экран админ‑панели
# ------------------------------------------------
async def admin_start_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛠 Админ‑панель:\nВыберите раздел 👇", reply_markup=get_admin_main_menu())

async def admin_menu_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🛠 Админ‑панель:\nВыберите раздел 👇", reply_markup=get_admin_main_menu())

# ------------------------------------------------
# Раздел FAQ
# ------------------------------------------------
async def admin_faq_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📖 Управление FAQ", reply_markup=get_admin_faq_menu())

async def admin_faq_list_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rows = await help_service.get_faq()
    if not rows:
        text = "⚠️ FAQ пуст"
    else:
        text = "📋 FAQ:\n\n" + "\n".join([f"ID:{r[0]} — ❓ {r[1]}" for r in rows])
    await query.edit_message_text(text, reply_markup=get_admin_faq_menu())

async def start_add_faq_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "faq"
    context.user_data["faq_state"] = "waiting_question"
    await query.edit_message_text("✍ Введите текст вопроса:")

# ------------------------------------------------
# Раздел Посты (workflow)
# ------------------------------------------------
def _post_card_kb(post_id: int) -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"ap_post_approve:{post_id}"),
            InlineKeyboardButton("✏️ Запросить правки", callback_data=f"ap_post_revisions:{post_id}"),
        ],
        [
            InlineKeyboardButton("🗓 Запланировать", callback_data=f"ap_post_schedule:{post_id}"),
            InlineKeyboardButton("🚀 Опубликовать", callback_data=f"ap_post_publish:{post_id}"),
        ],
        [
            InlineKeyboardButton("🗄 Архив", callback_data=f"ap_post_archive:{post_id}"),
            InlineKeyboardButton("🔙 Назад к списку", callback_data="admin_on_review_list"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)

async def admin_posts_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📂 Управление постами", reply_markup=get_admin_posts_menu())

async def admin_post_list_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await posts_service.init_db()
    rows = await posts_service.get_current_week_posts()
    if not rows:
        text = "⚠️ Постов на этой неделе нет"
    else:
        text_lines = ["📰 Посты недели:\n"]
        for row in rows:
            text_lines.append(f"ID:{row.id} — {row.title} | {row.status}")
        text = "\n".join(text_lines)
    await query.edit_message_text(text, reply_markup=get_admin_posts_menu())

async def start_add_post_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "posts"
    context.user_data["post_state"] = "waiting_title"
    await query.edit_message_text("✍ Введите заголовок поста:")

# --- Новые экраны для очереди на согласование ---
async def admin_on_review_list_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await posts_service.init_db()
    rows = await posts_service.list_by_status("on_review", limit=20, offset=0)
    if not rows:
        text = "🗂 Очередь на согласование пуста."
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data="admin_posts")]])
    else:
        lines = ["🗂 На согласовании:\n"]
        for p in rows:
            lines.append(f"ID:{p.id} — {p.title}")
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Открыть пост по ID", callback_data="admin_open_post_prompt")],
            [InlineKeyboardButton("🔙 Назад", callback_data="admin_posts")],
        ])
    await query.edit_message_text(text, reply_markup=kb)

async def admin_open_post_prompt_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["flow"] = "posts"
    context.user_data["post_state"] = "waiting_open_post_id"
    await query.edit_message_text("🔎 Введите ID поста, чтобы открыть карточку:")

async def admin_open_post_card_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    post = await posts_service.get_post(post_id)
    if not post:
        await update.callback_query.edit_message_text("❌ Пост не найден.", reply_markup=get_admin_posts_menu())
        return
    text = (
        f"📝 Пост ID:{post.id}\n"
        f"📌 Статус: {post.status}\n"
        f"📄 Заголовок: {post.title}\n\n"
        f"🧾 Комментарий редактора: {post.review_comment or '—'}\n"
        f"🗓 Запланирован на: {post.scheduled_at or '—'}\n"
    )
    await update.callback_query.edit_message_text(text, reply_markup=_post_card_kb(post.id))

# --- Действия на карточке ---
async def admin_post_approve_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    query = update.callback_query
    await query.answer()
    await posts_service.set_status(post_id, "approved", reviewer_id=update.effective_user.id)
    await admin_open_post_card_impl(update, context, post_id)

async def admin_post_request_revisions_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    query = update.callback_query
    await query.answer()
    context.user_data["flow"] = "posts"
    context.user_data["post_state"] = "waiting_revision_comment"
    context.user_data["review_post_id"] = post_id
    await query.edit_message_text("✏️ Введите комментарий к правкам (что исправить):")

async def admin_post_schedule_prompt_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    query = update.callback_query
    await query.answer()
    context.user_data["flow"] = "posts"
    context.user_data["post_state"] = "waiting_schedule_dt"
    context.user_data["schedule_post_id"] = post_id
    await query.edit_message_text("🗓 Введите дату и время публикации (формат: YYYY-MM-DD HH:MM):")

async def admin_post_publish_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    query = update.callback_query
    await query.answer()
    await posts_service.set_status(post_id, "published", reviewer_id=update.effective_user.id)
    await admin_open_post_card_impl(update, context, post_id)

async def admin_post_archive_impl(update: Update, context: ContextTypes.DEFAULT_TYPE, post_id: int):
    query = update.callback_query
    await query.answer()
    await posts_service.set_status(post_id, "archived", reviewer_id=update.effective_user.id)
    await admin_open_post_card_impl(update, context, post_id)

# ------------------------------------------------
# Раздел Оплаты/Подписки
# ------------------------------------------------
async def admin_payments_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("💳 Управление оплатами и подписками", reply_markup=get_admin_payments_menu())

async def start_add_payment_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "payments"
    context.user_data["payment_state"] = "waiting_user"
    await query.edit_message_text("👤 Введите ID пользователя:")

async def start_cancel_sub_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "payments"
    context.user_data["sub_state"] = "waiting_cancel_user"
    await query.edit_message_text("👤 Введите ID пользователя, чью подписку хотите отменить:")

async def start_sub_info_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "payments"
    context.user_data["sub_state"] = "waiting_info_user"
    await query.edit_message_text("👤 Введите ID пользователя для просмотра подписки:")

async def start_payment_history_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    context.user_data["flow"] = "payments"
    context.user_data["payment_state"] = "waiting_history_user"
    await query.edit_message_text("👤 Введите ID пользователя для просмотра истории оплат:")

# ------------------------------------------------
# ЕДИНЫЙ ТЕКСТОВЫЙ РОУТЕР
# ------------------------------------------------
async def admin_text_router_impl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    flow: Optional[str] = context.user_data.get("flow")
    if not flow:
        logger.debug("admin_text_router: no active flow; passing through")
        return

    # -------- FAQ flow ----------
    if flow == "faq":
        state = context.user_data.get("faq_state")
        if state == "waiting_question":
            context.user_data["new_faq_q"] = text
            context.user_data["faq_state"] = "waiting_answer"
            await update.message.reply_text("💡 Теперь введите ответ:")
            return
        elif state == "waiting_answer":
            q = context.user_data.get("new_faq_q")
            try:
                await help_service.add_faq(q, text)
                await update.message.reply_text("✅ Новый FAQ добавлен!", reply_markup=get_admin_faq_menu())
            except Exception as e:
                logger.exception("FAQ add failed")
                await update.message.reply_text(f"❌ Ошибка при добавлении FAQ: {e}", reply_markup=get_admin_faq_menu())
            finally:
                context.user_data.clear()
            return

    # -------- Posts flow ----------
    if flow == "posts":
        state = context.user_data.get("post_state")
        logger.info(f"post_state={state}")

        # Добавление нового поста
        if state == "waiting_title":
            context.user_data["new_post_title"] = text
            context.user_data["post_state"] = "waiting_content"
            await update.message.reply_text("📝 Теперь отправьте текст поста:")
            return
        elif state == "waiting_content":
            title = context.user_data.get("new_post_title")
            try:
                await posts_service.init_db()
                post = await posts_service.create_post(title, text)
                await update.message.reply_text(f"✅ Пост добавлен (ID:{post.id})", reply_markup=get_admin_posts_menu())
            except Exception as e:
                logger.exception("Post add failed")
                await update.message.reply_text(f"❌ Ошибка при добавлении поста: {e}", reply_markup=get_admin_posts_menu())
            finally:
                context.user_data.clear()
            return

        # Открыть карточку: ожидали ID
        if state == "waiting_open_post_id":
            try:
                post_id = int(text)
                post = await posts_service.get_post(post_id)
                if not post:
                    await update.message.reply_text("❌ Пост не найден.")
                else:
                    card = (
                        f"📝 Пост ID:{post.id}\n"
                        f"📌 Статус: {post.status}\n"
                        f"📄 Заголовок: {post.title}\n\n"
                        f"🧾 Комментарий редактора: {post.review_comment or '—'}\n"
                        f"🗓 Запланирован на: {post.scheduled_at or '—'}\n"
                    )
                    await update.message.reply_text(card, reply_markup=_post_card_kb(post.id))
            except Exception as e:
                await update.message.reply_text(f"⚠️ Ошибка: {e}")
            finally:
                context.user_data.pop("post_state", None)
            return

        # Запрос правок: ждём комментарий
        if state == "waiting_revision_comment":
            post_id = context.user_data.get("review_post_id")
            try:
                await posts_service.set_status(post_id, "revisions_requested", reviewer_id=update.effective_user.id, review_comment=text)
                await update.message.reply_text("✏️ Запрошены правки у автора.", reply_markup=get_admin_posts_menu())
            except Exception as e:
                logger.exception("request revisions failed")
                await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=get_admin_posts_menu())
            finally:
                context.user_data.clear()
            return

        # Планирование: ждём дату/время
        if state == "waiting_schedule_dt":
            post_id = context.user_data.get("schedule_post_id")
            dt = text
            try:
                if len(dt) < 16 or dt[4] != "-" or dt[7] != "-" or dt[10] != " " or dt[13] != ":":
                    await update.message.reply_text("⚠️ Формат неверный. Пример: 2025-09-06 14:30")
                    return
                await posts_service.set_schedule(post_id, dt)
                await update.message.reply_text(f"🗓 Запланировано на {dt}.", reply_markup=get_admin_posts_menu())
            except Exception as e:
                logger.exception("schedule failed")
                await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=get_admin_posts_menu())
            finally:
                context.user_data.clear()
            return

    # -------- Payments flow ----------
    if flow == "payments":
        p_state = context.user_data.get("payment_state")
        s_state = context.user_data.get("sub_state")

        if p_state == "waiting_user":
            try:
                user_id = int(text)
                context.user_data["payment_user"] = user_id
                context.user_data["payment_state"] = "waiting_amount"
                await update.message.reply_text("💵 Введите сумму оплаты:")
            except Exception:
                await update.message.reply_text("⚠️ Введите число (ID пользователя)")
            return
        elif p_state == "waiting_amount":
            try:
                amount = float(text)
                user_id = context.user_data.get("payment_user")
                await payments_service.init_db()
                pay = await payments_service.create_payment(user_id, amount)
                await update.message.reply_text(
                    f"✅ Оплата {amount}₽ добавлена (UserID:{user_id}, ID:{pay.id})",
                    reply_markup=get_admin_payments_menu()
                )
            except Exception as e:
                logger.exception("Payment add failed")
                await update.message.reply_text(f"⚠️ Ошибка: {e}")
            finally:
                context.user_data.clear()
            return

        if p_state == "waiting_history_user":
            try:
                user_id = int(text)
                await payments_service.init_db()
                rows = await payments_service.get_payments(user_id)
                if not rows:
                    await update.message.reply_text("📊 У пользователя нет оплат", reply_markup=get_admin_payments_menu())
                else:
                    out = ["📊 История оплат:\n"]
                    for r in rows:
                        amount, currency, desc, created_at = r
                        when = created_at.strftime('%d.%m.%Y') if hasattr(created_at, "strftime") else str(created_at)
                        out.append(f"💵 {currency} {amount} — {desc} ({when})")
                    await update.message.reply_text("\n".join(out), reply_markup=get_admin_payments_menu())
            except Exception as e:
                logger.exception("Payment history failed")
                await update.message.reply_text(f"⚠️ Ошибка: {e}", reply_markup=get_admin_payments_menu())
            finally:
                context.user_data.clear()
            return

        if s_state == "waiting_info_user":
            try:
                user_id = int(text)
                sub = await payments_service.get_subscription(user_id)
                if not sub:
                    await update.message.reply_text("⚠️ Подписка не найдена", reply_markup=get_admin_payments_menu())
                else:
                    uid, plan, price, status, next_charge_at = sub
                    when = next_charge_at.strftime('%d.%m.%Y') if hasattr(next_charge_at, "strftime") else (next_charge_at or "—")
                    info = (
                        f"📅 Подписка пользователя {uid}\n\n"
                        f"🔹 Тариф: {plan}\n"
                        f"💵 Цена: {price}₽\n"
                        f"📌 Статус: {status}\n"
                        f"📆 Следующее списание: {when}"
                    )
                    await update.message.reply_text(info, reply_markup=get_admin_payments_menu())
            except Exception as e:
                logger.exception("Subscription info failed")
                await update.message.reply_text(f"⚠️ Ошибка: {e}", reply_markup=get_admin_payments_menu())
            finally:
                context.user_data.clear()
            return

        if s_state == "waiting_cancel_user":
            try:
                user_id = int(text)
                await payments_service.init_db()
                result = await payments_service.cancel_subscription(user_id)
                if result:
                    await update.message.reply_text("🛑 Подписка отменена", reply_markup=get_admin_payments_menu())
                else:
                    await update.message.reply_text("⚠️ У этого пользователя нет активной подписки", reply_markup=get_admin_payments_menu())
            except Exception as e:
                logger.exception("Cancel subscription failed")
                await update.message.reply_text(f"⚠️ Ошибка: {e}", reply_markup=get_admin_payments_menu())
            finally:
                context.user_data.clear()
            return

    logger.debug("admin_text_router: unrecognized state; passing through")

# ------------------------------------------------
# Экспорт: фабрика хендлеров
# ------------------------------------------------
def get_admin_handlers(is_admin_user_callable: Callable):
    # Оборачиваем все функции проверкой прав
    admin_start = ensure_admin(admin_start_impl, is_admin_user_callable)
    admin_menu = ensure_admin(admin_menu_impl, is_admin_user_callable)

    admin_faq = ensure_admin(admin_faq_impl, is_admin_user_callable)
    admin_faq_list = ensure_admin(admin_faq_list_impl, is_admin_user_callable)
    start_add_faq = ensure_admin(start_add_faq_impl, is_admin_user_callable)

    admin_posts = ensure_admin(admin_posts_impl, is_admin_user_callable)
    admin_post_list = ensure_admin(admin_post_list_impl, is_admin_user_callable)
    start_add_post = ensure_admin(start_add_post_impl, is_admin_user_callable)

    # Новые по согласованию
    admin_on_review_list = ensure_admin(admin_on_review_list_impl, is_admin_user_callable)
    admin_open_post_prompt = ensure_admin(admin_open_post_prompt_impl, is_admin_user_callable)

    # callback с параметром ID через lambda-обёртку
    def with_id(handler, prefix):
        async def _wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE):
            query = update.callback_query
            data = query.data  # e.g. "ap_post_approve:123"
            try:
                post_id = int(data.split(":")[1])
            except Exception:
                await query.answer("❌ Некорректный ID", show_alert=True)
                return
            await handler(update, context, post_id)
        return ensure_admin(_wrapped, is_admin_user_callable)

    admin_open_post_card = with_id(admin_open_post_card_impl, "ap_post_open")
    admin_post_approve = with_id(admin_post_approve_impl, "ap_post_approve")
    admin_post_request_revisions = with_id(admin_post_request_revisions_impl, "ap_post_revisions")
    admin_post_schedule_prompt = with_id(admin_post_schedule_prompt_impl, "ap_post_schedule")
    admin_post_publish = with_id(admin_post_publish_impl, "ap_post_publish")
    admin_post_archive = with_id(admin_post_archive_impl, "ap_post_archive")

    admin_payments = ensure_admin(admin_payments_impl, is_admin_user_callable)
    start_add_payment = ensure_admin(start_add_payment_impl, is_admin_user_callable)
    start_cancel_sub = ensure_admin(start_cancel_sub_impl, is_admin_user_callable)
    start_sub_info = ensure_admin(start_sub_info_impl, is_admin_user_callable)
    start_payment_history = ensure_admin(start_payment_history_impl, is_admin_user_callable)

    admin_text_router = ensure_admin(admin_text_router_impl, is_admin_user_callable)

    return [
        # Вход в админку
        CommandHandler("admin", admin_start),
        CallbackQueryHandler(admin_menu, pattern="^admin_menu$"),

        # FAQ
        CallbackQueryHandler(admin_faq, pattern="^admin_faq$"),
        CallbackQueryHandler(admin_faq_list, pattern="^admin_faq_list$"),
        CallbackQueryHandler(start_add_faq, pattern="^admin_faq_add$"),

        # Посты (старое меню)
        CallbackQueryHandler(admin_posts, pattern="^admin_posts$"),
        CallbackQueryHandler(admin_post_list, pattern="^admin_post_list$"),
        CallbackQueryHandler(start_add_post, pattern="^admin_post_add$"),

        # Посты: согласование
        CallbackQueryHandler(admin_on_review_list, pattern="^admin_on_review_list$"),
        CallbackQueryHandler(admin_open_post_prompt, pattern="^admin_open_post_prompt$"),
        CallbackQueryHandler(admin_open_post_card, pattern="^ap_post_open:\\d+$"),
        CallbackQueryHandler(admin_post_approve, pattern="^ap_post_approve:\\d+$"),
        CallbackQueryHandler(admin_post_request_revisions, pattern="^ap_post_revisions:\\d+$"),
        CallbackQueryHandler(admin_post_schedule_prompt, pattern="^ap_post_schedule:\\d+$"),
        CallbackQueryHandler(admin_post_publish, pattern="^ap_post_publish:\\d+$"),
        CallbackQueryHandler(admin_post_archive, pattern="^ap_post_archive:\\d+$"),

        # Оплаты и подписки
        CallbackQueryHandler(admin_payments, pattern="^admin_payments$"),
        CallbackQueryHandler(start_add_payment, pattern="^admin_payment_add$"),
        CallbackQueryHandler(start_payment_history, pattern="^admin_payment_history$"),
        CallbackQueryHandler(start_sub_info, pattern="^admin_sub_info$"),
        CallbackQueryHandler(start_cancel_sub, pattern="^admin_sub_cancel$"),

        # ЕДИНЫЙ текстовый роутер: НЕ блокируем другие хендлеры
        MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_router, block=False),
    ]