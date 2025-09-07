# handlers/projects.py
# Пользовательский раздел «Проекты»: публикации, согласование, архив, предложения (плейсхолдер)
# Обновления:
# - При старте добавления публикации очищаем админский flow (context.user_data["flow"]) на всякий случай.
# - Регистрируем клиентский текстовый роутер с block=False, чтобы он гарантированно не блокировал другие хендлеры
#   и всегда получал сообщения, даже если админский роутер в том же чате активен.

import logging
from typing import List, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from services import posts as posts_service

logger = logging.getLogger(__name__)

# -------------------------
# Меню раздела «Проекты»
# -------------------------
def get_projects_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📰 Публикации", callback_data="proj_publications")],
        [InlineKeyboardButton("✅ Одобрение и правки", callback_data="proj_approval")],
        [InlineKeyboardButton("🗄 Архив", callback_data="proj_archive")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_publications_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("➕ Добавить публикацию (черновик)", callback_data="proj_pub_add")],
        [InlineKeyboardButton("📋 Посты недели", callback_data="proj_pub_list_week")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_projects")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_approval_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📤 Отправить на согласование", callback_data="proj_send_review")],
        [InlineKeyboardButton("🔎 Проверить статус по ID", callback_data="proj_check_status")],
        [InlineKeyboardButton("✏️ Отправить исправленную версию", callback_data="proj_submit_revision")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_projects")],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_archive_menu() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("📦 Архив постов (опубликованные)", callback_data="proj_archive_list")],
        [InlineKeyboardButton("🔙 Назад", callback_data="menu_projects")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------------
# Экран раздела «Проекты»
# -------------------------
async def projects_root(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📂 Проекты\n\n"
        "Управляйте публикациями, согласованием и архивом материалов.\n"
        "Выберите раздел:"
    )
    await query.edit_message_text(text, reply_markup=get_projects_menu())

# -------------------------
# Публикации
# -------------------------
async def publications_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "📰 Публикации\n\n"
        "— Посмотреть посты текущей недели\n"
        "— Добавить черновик поста\n\n"
        "Выберите действие:"
    )
    await query.edit_message_text(text, reply_markup=get_publications_menu())

async def publications_list_week(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await posts_service.init_db()
        posts = await posts_service.get_current_week_posts()
        if not posts:
            text = "На этой неделе публикаций пока нет."
        else:
            lines: List[str] = ["🗓 Посты этой недели:\n"]
            for p in posts:
                lines.append(f"ID:{p.id} — {p.title} | {p.status}")
            text = "\n".join(lines)
    except Exception as e:
        logger.exception("publications_list_week failed")
        text = f"❌ Ошибка при получении постов: {e}"
    await query.edit_message_text(text, reply_markup=get_publications_menu())

async def start_add_publication(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # ВАЖНО: полностью очищаем любые предыдущие состояния
    context.user_data.pop("flow", None)                  # возможный админский flow
    context.user_data.pop("post_state", None)            # возможный админский state
    context.user_data.pop("review_post_id", None)        # хвосты от админских действий
    context.user_data.pop("schedule_post_id", None)

    context.user_data.pop("flow_client", None)
    context.user_data.pop("client_post_state", None)
    context.user_data.pop("client_new_post_title", None)

    # Устанавливаем клиентский поток добавления публикации
    context.user_data["flow_client"] = "publications"
    context.user_data["client_post_state"] = "waiting_title"
    await query.edit_message_text("✍ Введите заголовок публикации:")

# -------------------------
# Одобрение и правки
# -------------------------
async def approval_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "✅ Одобрение и правки\n\n"
        "— Отправьте черновик на согласование (нужен ID поста)\n"
        "— Проверьте статус и комментарии редактора\n"
        "— Отправьте исправленную версию при запросе правок\n"
    )
    await query.edit_message_text(text, reply_markup=get_approval_menu())

async def approval_send_review_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["flow_client"] = "approval"
    context.user_data["client_approval_state"] = "waiting_post_id_for_review"
    await query.edit_message_text("📤 Введите ID черновика, чтобы отправить на согласование:")

async def approval_check_status_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["flow_client"] = "approval"
    context.user_data["client_approval_state"] = "waiting_post_id_for_check"
    await query.edit_message_text("🔎 Введите ID поста для проверки статуса:")

async def approval_submit_revision_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["flow_client"] = "approval"
    context.user_data["client_approval_state"] = "waiting_post_id_for_revision"
    await query.edit_message_text("✏️ Введите ID поста для отправки исправленной версии:")

# -------------------------
# Архив
# -------------------------
async def archive_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = "🗄 Архив опубликованных материалов.\nВыберите действие:"
    await query.edit_message_text(text, reply_markup=get_archive_menu())

async def archive_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        await posts_service.init_db()
        archived = await posts_service.list_posts(status="archived", limit=20, offset=0)
        if not archived:
            text = "В архиве пусто."
        else:
            lines: List[str] = ["📦 Архив:\n"]
            for p in archived:
                lines.append(f"ID:{p.id} — {p.title}")
            text = "\n".join(lines)
    except Exception as e:
        logger.exception("archive_list failed")
        text = f"❌ Ошибка при получении архива: {e}"
    await query.edit_message_text(text, reply_markup=get_archive_menu())

# -------------------------
# ЕДИНЫЙ текстовый роутер (клиентский)
# -------------------------
async def client_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Пошаговые сценарии клиента:
    - Добавление черновика: waiting_title -> waiting_content
    - Согласование:
      - waiting_post_id_for_review -> set_status on_review
      - waiting_post_id_for_check -> показать статус/комментарий
      - waiting_post_id_for_revision -> затем waiting_revision_content -> add_revision + on_review
    """
    text = (update.message.text or "").strip()
    flow = context.user_data.get("flow_client")
    if not flow:
        # Ничего не делаем — пропускаем дальше (block=False позволит другим хендлерам сработать)
        logger.debug("client_text_router: no flow_client, pass-through")
        return

    # Черновик
    if flow == "publications":
        state = context.user_data.get("client_post_state")
        logger.debug(f"client_text_router publications state={state}")
        if state == "waiting_title":
            context.user_data["client_new_post_title"] = text
            context.user_data["client_post_state"] = "waiting_content"
            await update.message.reply_text("📝 Теперь отправьте текст публикации:")
            return
        elif state == "waiting_content":
            title = context.user_data.get("client_new_post_title")
            content = text
            try:
                await posts_service.init_db()
                post = await posts_service.create_post(title=title, content=content, status="draft")
                await update.message.reply_text(
                    f"✅ Черновик создан (ID:{post.id}). "
                    f"Чтобы отправить на согласование — перейдите в «Одобрение и правки».",
                    reply_markup=get_publications_menu()
                )
            except Exception as e:
                logger.exception("client draft add failed")
                await update.message.reply_text(f"❌ Ошибка при создании черновика: {e}", reply_markup=get_publications_menu())
            finally:
                context.user_data.pop("client_post_state", None)
                context.user_data.pop("client_new_post_title", None)
                context.user_data.pop("flow_client", None)
            return

    # Согласование
    if flow == "approval":
        state = context.user_data.get("client_approval_state")
        logger.debug(f"client_text_router approval state={state}")

        # Отправить на согласование
        if state == "waiting_post_id_for_review":
            try:
                post_id = int(text)
                post = await posts_service.get_post(post_id)
                if not post:
                    await update.message.reply_text("❌ Пост не найден.")
                    return
                if post.status not in {"draft", "revisions_requested", "approved"}:
                    await update.message.reply_text(f"⚠️ Нельзя отправить пост в статусе {post.status}.")
                    return
                await posts_service.set_status(post_id, "on_review")
                await update.message.reply_text("📤 Отправлено на согласование.")
            except Exception as e:
                logger.exception("send to review failed")
                await update.message.reply_text(f"❌ Ошибка: {e}")
            finally:
                context.user_data.clear()
            return

        # Проверить статус
        if state == "waiting_post_id_for_check":
            try:
                post_id = int(text)
                post = await posts_service.get_post(post_id)
                if not post:
                    await update.message.reply_text("❌ Пост не найден.")
                else:
                    txt = (
                        f"📝 Пост ID:{post.id}\n"
                        f"📌 Статус: {post.status}\n"
                        f"🧾 Комментарий редактора: {post.review_comment or '—'}\n"
                        f"🗓 Запланирован на: {post.scheduled_at or '—'}\n"
                    )
                    await update.message.reply_text(txt, reply_markup=get_approval_menu())
            except Exception as e:
                logger.exception("check status failed")
                await update.message.reply_text(f"❌ Ошибка: {e}")
            finally:
                context.user_data.clear()
            return

        # Отправить исправленную версию: шаг 1 — ID
        if state == "waiting_post_id_for_revision":
            try:
                post_id = int(text)
                post = await posts_service.get_post(post_id)
                if not post:
                    await update.message.reply_text("❌ Пост не найден.")
                    context.user_data.clear()
                    return
                if post.status not in {"revisions_requested", "draft"}:
                    await update.message.reply_text("⚠️ Исправления принимаются только для черновиков и постов с запрошенными правками.")
                    context.user_data.clear()
                    return
                context.user_data["client_revision_post_id"] = post_id
                context.user_data["client_approval_state"] = "waiting_revision_content"
                await update.message.reply_text("✏️ Отправьте новую версию текста (целиком):")
            except Exception as e:
                await update.message.reply_text(f"❌ Ошибка: {e}")
                context.user_data.clear()
            return

        # Отправить исправленную версию: шаг 2 — контент
        if state == "waiting_revision_content":
            post_id = context.user_data.get("client_revision_post_id")
            content = text
            try:
                await posts_service.add_revision(post_id, content, author_id=update.effective_user.id, note="client revision")
                await posts_service.update_post(post_id, content=content)  # обновим тело поста на новую версию
                await posts_service.set_status(post_id, "on_review")
                await update.message.reply_text("📤 Исправления отправлены на согласование.", reply_markup=get_approval_menu())
            except Exception as e:
                logger.exception("submit revision failed")
                await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=get_approval_menu())
            finally:
                context.user_data.clear()
            return

# -------------------------
# Экспорт регистрации хендлеров
# -------------------------
def get_project_handlers():
    return [
        CallbackQueryHandler(projects_root, pattern="^menu_projects$"),

        # Публикации
        CallbackQueryHandler(publications_home, pattern="^proj_publications$"),
        CallbackQueryHandler(publications_list_week, pattern="^proj_pub_list_week$"),
        CallbackQueryHandler(start_add_publication, pattern="^proj_pub_add$"),

        # Одобрение/правки
        CallbackQueryHandler(approval_home, pattern="^proj_approval$"),
        CallbackQueryHandler(approval_send_review_prompt, pattern="^proj_send_review$"),
        CallbackQueryHandler(approval_check_status_prompt, pattern="^proj_check_status$"),
        CallbackQueryHandler(approval_submit_revision_prompt, pattern="^proj_submit_revision$"),

        # Архив
        CallbackQueryHandler(archive_home, pattern="^proj_archive$"),
        CallbackQueryHandler(archive_list, pattern="^proj_archive_list$"),

        # Текстовый роутер клиента: block=False — чтобы он точно не блокировал остальные обработчики
        MessageHandler(filters.TEXT & ~filters.COMMAND, client_text_router, block=False),
    ]