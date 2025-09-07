# bot.py
# GPT-5: Multi-tenant, multi-project Telegram CMS bot with numeric Project ID activation
# Конфиг через .env / config.py. Совместимо с PTB 20.x без tzinfo в run_daily.
#
# Функционал:
# - Тенанты и проекты (multi-tenant, multi-project), числовой Project ID
# - /activate <ID> и меню активации по ID
# - Привязка канала: @username (публичный) или пересланное сообщение (приватный)
# - Проверка прав: бот в админах и может постить; тест-пост с авто-удалением
# - Неделя: генерить 7 черновиков, сводка, approve, планирование публикаций
# - Публикация по расписанию, ручная публикация, retry при ошибках
# - Ежедневный бэкап (JSON) владельцу проекта (owner) или первому админу
#
# Требования:
#   python >= 3.10
#   python-telegram-bot == 20.7
#   python-dotenv == 1.0.1
#
# Запуск:
#   1) создайте .env (см. .env.example)
#   2) pip install -r requirements.txt
#   3) python bot.py

import os
import json
import sqlite3
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatMemberAdministrator,
    ChatMemberOwner,
    Message,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

from config import get_settings

SETTINGS = get_settings()

APP_NAME = "Multi-Project CMS Bot"
DB_PATH = SETTINGS.database_path
TELEGRAM_BOT_TOKEN = SETTINGS.telegram_token
DEFAULT_TZ = SETTINGS.default_tz

# ------------- DB Helpers -------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        c = conn.cursor()
        # users
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_user_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            created_at TEXT NOT NULL
        )""")
        # tenants
        c.execute("""
        CREATE TABLE IF NOT EXISTS tenants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL
        )""")
        # memberships
        c.execute("""
        CREATE TABLE IF NOT EXISTS memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,           -- owner | admin
            status TEXT NOT NULL DEFAULT 'active',
            UNIQUE(tenant_id, user_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )""")
        # projects
        c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,   -- internal pk
            tenant_id INTEGER NOT NULL,
            project_id INTEGER UNIQUE NOT NULL,     -- numeric external ID
            name TEXT NOT NULL,
            tz TEXT NOT NULL,
            channel_id TEXT,                        -- chat_id или @username
            allow_id_join INTEGER NOT NULL DEFAULT 1,
            owner_user_id INTEGER,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (tenant_id) REFERENCES tenants(id)
        )""")
        # weeks
        c.execute("""
        CREATE TABLE IF NOT EXISTS weeks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,        -- projects.id (internal)
            week_label TEXT NOT NULL,
            start_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft',   -- draft|review|approved|published
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id, project_id, week_label),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )""")
        # posts
        c.execute("""
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            week_label TEXT NOT NULL,
            post_no INTEGER NOT NULL,            -- 1..7
            status TEXT NOT NULL DEFAULT 'draft',
            title TEXT,
            lead TEXT,
            body TEXT,
            cta_text TEXT,
            cta_url TEXT,
            tags TEXT,
            cover_url TEXT,
            publish_at TEXT,                     -- UTC ISO
            message_id INTEGER,
            error_note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(tenant_id, project_id, week_label, post_no),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )""")
        # publish_log
        c.execute("""
        CREATE TABLE IF NOT EXISTS publish_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            post_id INTEGER NOT NULL,
            ts TEXT NOT NULL,
            platform TEXT NOT NULL,
            result TEXT NOT NULL,
            message_id INTEGER,
            error_note TEXT
        )""")
        # settings (per user context)
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_ctx (
            user_id INTEGER PRIMARY KEY,     -- users.id
            current_tenant_id INTEGER,
            current_project_pk INTEGER,      -- projects.id
            current_week_label TEXT
        )""")
        conn.commit()

def now_iso():
    return datetime.utcnow().replace(microsecond=0).isoformat()

# ------------- Users / Tenants / Memberships -------------

def get_or_create_user(tg_user_id: int, username: str, first_name: str, last_name: str) -> sqlite3.Row:
    with db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE tg_user_id=?", (tg_user_id,))
        row = c.fetchone()
        if row:
            return row
        c.execute("""INSERT INTO users(tg_user_id,username,first_name,last_name,created_at)
                     VALUES(?,?,?,?,?)""",
                  (tg_user_id, username, first_name, last_name, now_iso()))
        conn.commit()
        c.execute("SELECT * FROM users WHERE tg_user_id=?", (tg_user_id,))
        return c.fetchone()

def ensure_user_ctx(user_id: int):
    with db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO user_ctx(user_id) VALUES(?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        conn.commit()

def set_user_ctx(user_id: int, tenant_id: Optional[int]=None, project_pk: Optional[int]=None, week_label: Optional[str]=None):
    ensure_user_ctx(user_id)
    with db() as conn:
        c = conn.cursor()
        row = c.execute("SELECT * FROM user_ctx WHERE user_id=?", (user_id,)).fetchone()
        new_tenant = tenant_id if tenant_id is not None else row["current_tenant_id"]
        new_project = project_pk if project_pk is not None else row["current_project_pk"]
        new_week = week_label if week_label is not None else row["current_week_label"]
        c.execute("""UPDATE user_ctx SET current_tenant_id=?, current_project_pk=?, current_week_label=? WHERE user_id=?""",
                  (new_tenant, new_project, new_week, user_id))
        conn.commit()

def get_user_ctx(user_id: int) -> sqlite3.Row:
    ensure_user_ctx(user_id)
    with db() as conn:
        c = conn.cursor()
        return c.execute("SELECT * FROM user_ctx WHERE user_id=?", (user_id,)).fetchone()

def create_tenant(name: str) -> int:
    with db() as conn:
        c = conn.cursor()
        c.execute("INSERT INTO tenants(name,status,created_at) VALUES(?,?,?)", (name, "active", now_iso()))
        conn.commit()
        return c.lastrowid

def add_membership(tenant_id: int, user_id: int, role: str):
    with db() as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO memberships(tenant_id,user_id,role,status)
                     VALUES(?,?,?,?)
                     ON CONFLICT(tenant_id,user_id) DO UPDATE SET role=excluded.role, status='active'""",
                  (tenant_id, user_id, role, "active"))
        conn.commit()

def has_role(user_id: int, tenant_id: int, roles: List[str]) -> bool:
    with db() as conn:
        c = conn.cursor()
        row = c.execute("""SELECT role FROM memberships
                           WHERE tenant_id=? AND user_id=? AND status='active'""",
                        (tenant_id, user_id)).fetchone()
        return bool(row and row["role"] in roles)

# ------------- Projects -------------

def create_project(tenant_id: int, name: str, tz: str) -> sqlite3.Row:
    with db() as conn:
        c = conn.cursor()
        # numeric project_id: auto-increment sequence (max+1), стартуем от 100000
        curr = c.execute("SELECT COALESCE(MAX(project_id), 100000) as m FROM projects").fetchone()["m"]
        new_pid = curr + 1
        now = now_iso()
        c.execute("""INSERT INTO projects(tenant_id,project_id,name,tz,allow_id_join,status,created_at,updated_at)
                     VALUES(?,?,?,?,?,?,?,?)""",
                  (tenant_id, new_pid, name, tz, 1, "active", now, now))
        conn.commit()
        return c.execute("SELECT * FROM projects WHERE project_id=?", (new_pid,)).fetchone()

def find_project_by_pid(project_id: int) -> Optional[sqlite3.Row]:
    with db() as conn:
        c = conn.cursor()
        return c.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()

def list_user_projects(user_id: int) -> List[sqlite3.Row]:
    with db() as conn:
        c = conn.cursor()
        return c.execute("""
        SELECT p.* FROM projects p
        JOIN memberships m ON m.tenant_id = p.tenant_id
        WHERE m.user_id=? AND m.status='active' AND p.status='active'
        ORDER BY p.created_at DESC
        """, (user_id,)).fetchall()

def set_project_channel(project_pk: int, channel_id: str):
    with db() as conn:
        c = conn.cursor()
        c.execute("UPDATE projects SET channel_id=?, updated_at=? WHERE id=?", (channel_id, now_iso(), project_pk))
        conn.commit()

def set_project_owner(project_pk: int, owner_user_id: int):
    with db() as conn:
        c = conn.cursor()
        c.execute("UPDATE projects SET owner_user_id=?, updated_at=? WHERE id=?", (owner_user_id, now_iso(), project_pk))
        conn.commit()

def toggle_allow_id_join(project_pk: int, value: bool):
    with db() as conn:
        c = conn.cursor()
        c.execute("UPDATE projects SET allow_id_join=?, updated_at=? WHERE id=?", (1 if value else 0, now_iso(), project_pk))
        conn.commit()

# ------------- Weeks / Posts -------------

def week_label_from_date(d: date) -> str:
    isoy, wno, _ = d.isocalendar()
    return f"W{wno:02d}-{isoy}"

def upsert_week(tenant_id: int, project_pk: int, start_date: date) -> sqlite3.Row:
    wl = week_label_from_date(start_date)
    with db() as conn:
        c = conn.cursor()
        row = c.execute("""SELECT * FROM weeks WHERE tenant_id=? AND project_id=? AND week_label=?""",
                        (tenant_id, project_pk, wl)).fetchone()
        now = now_iso()
        if not row:
            c.execute("""INSERT INTO weeks(tenant_id,project_id,week_label,start_date,status,created_at,updated_at)
                         VALUES(?,?,?,?,?,?,?)""",
                      (tenant_id, project_pk, wl, start_date.isoformat(), "draft", now, now))
            conn.commit()
            row = c.execute("""SELECT * FROM weeks WHERE tenant_id=? AND project_id=? AND week_label=?""",
                            (tenant_id, project_pk, wl)).fetchone()
        return row

def make_default_schedule(local_start: date, tz: str) -> List[datetime]:
    tzinfo = ZoneInfo(tz)
    base = datetime.combine(local_start, time(10,0), tzinfo=tzinfo)
    out = []
    for i in range(7):
        local_dt = base + timedelta(days=i)
        out.append(local_dt.astimezone(ZoneInfo("UTC")))
    return out

def generate_week_drafts(tenant_id: int, project_pk: int, week_label: str, tz: str, start_date: date):
    sched = make_default_schedule(start_date, tz)
    now = now_iso()
    with db() as conn:
        c = conn.cursor()
        cnt = c.execute("""SELECT COUNT(*) as n FROM posts
                           WHERE tenant_id=? AND project_id=? AND week_label=?""",
                        (tenant_id, project_pk, week_label)).fetchone()["n"]
        if cnt == 0:
            for i in range(7):
                title = f"Цифровая безопасность #{i+1}"
                lead = "Короткий лид: чем полезен этот пост."
                body = ("1) Что это и зачем\n"
                        "2) Простое объяснение\n"
                        "3) Практическая польза за 3 минуты")
                tags = "#security #privacy #digital"
                c.execute("""INSERT INTO posts(tenant_id,project_id,week_label,post_no,status,title,lead,body,tags,cover_url,publish_at,created_at,updated_at)
                             VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                          (tenant_id, project_pk, week_label, i+1, "draft", title, lead, body, tags, "", sched[i].isoformat(), now, now))
            conn.commit()

def fetch_posts(tenant_id: int, project_pk: int, week_label: str) -> List[sqlite3.Row]:
    with db() as conn:
        c = conn.cursor()
        return c.execute("""SELECT * FROM posts
                            WHERE tenant_id=? AND project_id=? AND week_label=?
                            ORDER BY post_no""",
                         (tenant_id, project_pk, week_label)).fetchall()

def validate_post(p: Dict[str, Any]) -> List[str]:
    issues = []
    if not p.get("title") or len(p["title"]) > 60: issues.append("Заголовок пустой или длиннее 60")
    if not p.get("lead") or len(p["lead"]) > 140: issues.append("Лид пустой или длиннее 140")
    if not p.get("body"): issues.append("Нет основного текста")
    if p.get("cta_text") and not p.get("cta_url"): issues.append("Есть CTA-текст, но нет ссылки")
    tags = (p.get("tags") or "").strip()
    if tags and len(tags.split()) > 10: issues.append("Слишком много хэштегов (>10)")
    if not p.get("cover_url"): issues.append("Нет обложки")
    if not p.get("publish_at"): issues.append("Не задано время публикации")
    return issues

def assemble_text(p: Dict[str, Any]) -> str:
    parts = []
    if p.get("title"): parts.append(p["title"].strip())
    if p.get("lead"):
        parts.append("")
        parts.append(p["lead"].strip())
    if p.get("body"):
        parts.append("")
        parts.append(p["body"].strip())
    if p.get("cta_text") and p.get("cta_url"):
        parts.append("")
        parts.append(f"{p['cta_text']} — {p['cta_url']}")
    if p.get("tags"):
        parts.append("")
        parts.append(p["tags"].strip())
    return "\n".join(parts)

# ------------- Auth / Context Guards -------------

async def get_context_user(update: Update) -> sqlite3.Row:
    u = update.effective_user
    return get_or_create_user(
        tg_user_id=u.id,
        username=u.username or "",
        first_name=u.first_name or "",
        last_name=u.last_name or "",
    )

def user_has_access_to_project(user_id: int, tenant_id: int) -> bool:
    return has_role(user_id, tenant_id, ["owner", "admin"])

# ------------- Keyboards -------------

def root_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Проекты", callback_data="menu:projects"),
         InlineKeyboardButton("Неделя", callback_data="menu:week")],
        [InlineKeyboardButton("Посты", callback_data="menu:posts"),
         InlineKeyboardButton("Публикации", callback_data="menu:pub")],
        [InlineKeyboardButton("Экспорт/Бэкап", callback_data="menu:export"),
         InlineKeyboardButton("Настройки", callback_data="menu:settings")],
    ])

def projects_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Мои проекты", callback_data="prj:list")],
        [InlineKeyboardButton("Активировать по ID", callback_data="prj:activate")],
        [InlineKeyboardButton("Создать проект", callback_data="prj:create")],
        [InlineKeyboardButton("Назад", callback_data="menu:root")],
    ])

def project_card_kb(project):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Выбрать проект", callback_data=f"prj:select:{project['id']}")],
        [InlineKeyboardButton("Подключить канал", callback_data=f"prj:bind:{project['id']}"),
         InlineKeyboardButton("Проверить доступ", callback_data=f"prj:check:{project['id']}")],
        [InlineKeyboardButton(f"Разрешать подключение по ID: {'ON' if project['allow_id_join'] else 'OFF'}",
                              callback_data=f"prj:toggle_join:{project['id']}")],
        [InlineKeyboardButton("Назад к проектам", callback_data="prj:list")]
    ])

def week_menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Создать неделю", callback_data="week:create"),
         InlineKeyboardButton("Сводка", callback_data="week:summary")],
        [InlineKeyboardButton("Сгенерировать 7 черновиков", callback_data="week:gen")],
        [InlineKeyboardButton("Approve неделю", callback_data="week:approve"),
         InlineKeyboardButton("Сдвиг +1 день", callback_data="week:shift_day")],
        [InlineKeyboardButton("Назад", callback_data="menu:root")]
    ])

def posts_menu_kb(week_label):
    row1 = [InlineKeyboardButton(f"Пост {i}", callback_data=f"post:open:{week_label}:{i}") for i in range(1,5)]
    row2 = [InlineKeyboardButton(f"Пост {i}", callback_data=f"post:open:{week_label}:{i}") for i in range(5,8)]
    return InlineKeyboardMarkup([row1, row2, [InlineKeyboardButton("Назад", callback_data="menu:root")]])

def post_actions_kb(week_label, post_no):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Предпросмотр", callback_data=f"post:preview:{week_label}:{post_no}")],
        [InlineKeyboardButton("Заголовок", callback_data=f"post:edit_title:{week_label}:{post_no}"),
         InlineKeyboardButton("Лид", callback_data=f"post:edit_lead:{week_label}:{post_no}")],
        [InlineKeyboardButton("Текст", callback_data=f"post:edit_body:{week_label}:{post_no}")],
        [InlineKeyboardButton("Теги", callback_data=f"post:edit_tags:{week_label}:{post_no}"),
         InlineKeyboardButton("CTA", callback_data=f"post:edit_cta:{week_label}:{post_no}")],
        [InlineKeyboardButton("Обложка URL", callback_data=f"post:edit_cover:{week_label}:{post_no}")],
        [InlineKeyboardButton("Дата/время", callback_data=f"post:edit_dt:{week_label}:{post_no}")],
        [InlineKeyboardButton("Статус: Draft", callback_data=f"post:set_status:{week_label}:{post_no}:draft"),
         InlineKeyboardButton("Review", callback_data=f"post:set_status:{week_label}:{post_no}:review"),
         InlineKeyboardButton("Approved", callback_data=f"post:set_status:{week_label}:{post_no}:approved")],
        [InlineKeyboardButton("Опубликовать сейчас", callback_data=f"post:publish_now:{week_label}:{post_no}")],
        [InlineKeyboardButton("Назад к постам", callback_data=f"posts:list:{week_label}")]
    ])

# ------------- Conversations -------------

ASK_PROJECT_ID, ASK_NEW_PROJECT_NAME, ASK_BIND_INSTRUCTION, ASK_CHANNEL_USERNAME, ASK_FORWARD_FROM_CHANNEL, EDIT_STATE = range(6)

PFLD = {
    "title": "Введите новый заголовок (≤ 60 символов).",
    "lead": "Введите лид (≤ 140 символов).",
    "body": "Введите основной текст (3–6 коротких абзацев).",
    "tags": "Введите хэштеги одной строкой, например: #security #privacy #vpn",
    "cta": "Введите CTA двумя строками: сначала текст кнопки, затем ссылка (URL).",
    "cover": "Пришлите URL обложки (картинка).",
    "dt": "Введите локальное время публикации двумя строками: дата YYYY-MM-DD и время HH:MM (24-часовой формат)."
}

# ------------- Handlers -------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await get_context_user(update)
    set_user_ctx(u["id"])  # ensure record exists
    await update.effective_chat.send_message(
        f"{APP_NAME}\nУправление проектами и публикациями.",
        reply_markup=root_menu_kb()
    )

# /activate <project_id>
async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = await get_context_user(update)
    args = context.args
    if not args:
        await update.effective_chat.send_message("Использование: /activate <PROJECT_ID> (число)")
        return
    try:
        pid = int(args[0])
    except:
        await update.effective_chat.send_message("PROJECT_ID должен быть числом.")
        return
    await activate_by_id_flow(update, context, u, pid)

async def activate_by_id_flow(update: Update, context: ContextTypes.DEFAULT_TYPE, u: sqlite3.Row, numeric_pid: int):
    prj = find_project_by_pid(numeric_pid)
    if not prj or prj["status"] != "active":
        await update.effective_chat.send_message("Проект с таким ID не найден или неактивен.")
        return
    tenant_id = prj["tenant_id"]
    if prj["owner_user_id"] is None:
        add_membership(tenant_id, u["id"], "owner")
        set_project_owner(prj["id"], u["id"])
        role_assigned = "owner"
    else:
        if prj["allow_id_join"]:
            add_membership(tenant_id, u["id"], "admin")
            role_assigned = "admin"
        else:
            await update.effective_chat.send_message("Подключение по ID отключено владельцем. Попросите владельца добавить вас.")
            return
    set_user_ctx(u["id"], tenant_id=tenant_id, project_pk=prj["id"], week_label=None)
    await update.effective_chat.send_message(
        f"Проект активирован.\nProject ID: {prj['project_id']}\nРоль: {role_assigned}\nИмя: {prj['name']}\nTZ: {prj['tz']}",
        reply_markup=projects_menu_kb()
    )

async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    if data == "menu:root":
        await q.edit_message_reply_markup(reply_markup=root_menu_kb())
    elif data == "menu:projects":
        await q.edit_message_text("Проекты:", reply_markup=projects_menu_kb())
    elif data == "menu:week":
        u = await get_context_user(update)
        ctx = get_user_ctx(u["id"])
        if not ctx["current_project_pk"]:
            await q.edit_message_text("Сначала выберите или активируйте проект.", reply_markup=projects_menu_kb())
            return
        wl = ctx["current_week_label"] or "(не выбрана)"
        await q.edit_message_text(f"Неделя: {wl}", reply_markup=week_menu_kb())
    elif data == "menu:posts":
        u = await get_context_user(update)
        ctx = get_user_ctx(u["id"])
        if not ctx["current_project_pk"]:
            await q.edit_message_text("Сначала выберите проект.", reply_markup=projects_menu_kb()); return
        wl = ctx["current_week_label"]
        if not wl:
            await q.edit_message_text("Сначала создайте/выберите неделю.", reply_markup=week_menu_kb()); return
        await q.edit_message_text(f"Посты недели {wl}", reply_markup=posts_menu_kb(wl))
    elif data == "menu:pub":
        await q.edit_message_text("Публикации: планировщик работает автоматически. Публиковать вручную можно из карточки поста.", reply_markup=root_menu_kb())
    elif data == "menu:export":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("Экспорт недели (JSON)", callback_data="export:week_json")],
            [InlineKeyboardButton("Вкл/Выкл автобэкап", callback_data="export:toggle_backup")],
            [InlineKeyboardButton("Назад", callback_data="menu:root")]
        ])
        await q.edit_message_text("Экспорт и бэкап", reply_markup=kb)
    elif data == "menu:settings":
        await q.edit_message_text("Настройки проекта/аккаунта.", reply_markup=root_menu_kb())

# ----- Projects section -----

async def prj_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data
    u = await get_context_user(update)
    if data == "prj:list":
        projects = list_user_projects(u["id"])
        if not projects:
            await q.edit_message_text("У вас пока нет проектов. Активируйте по ID или создайте.", reply_markup=projects_menu_kb()); return
        lines = [f"- {p['name']} (ID {p['project_id']}, TZ {p['tz']})" for p in projects]
        kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton(f"{p['name']} · ID {p['project_id']}", callback_data=f"prj:select:{p['id']}")] for p in projects] +
            [[InlineKeyboardButton("Назад", callback_data="menu:projects")]]
        )
        await q.edit_message_text("Мои проекты:\n" + "\n".join(lines), reply_markup=kb)
    elif data == "prj:activate":
        await q.edit_message_text("Введите числовой Project ID ответным сообщением.")
        context.user_data["awaiting_project_id"] = True
        return ASK_PROJECT_ID
    elif data == "prj:create":
        await q.edit_message_text("Введите имя нового проекта (будет создан новый клиент/тенант).")
        context.user_data["awaiting_new_project_name"] = True
        return ASK_NEW_PROJECT_NAME
    elif data.startswith("prj:select:"):
        _, _, pk = data.split(":")
        pk = int(pk)
        with db() as conn:
            c = conn.cursor()
            prj = c.execute("SELECT * FROM projects WHERE id=?", (pk,)).fetchone()
            if not prj:
                await q.edit_message_text("Проект не найден.", reply_markup=projects_menu_kb()); return
            if not user_has_access_to_project(u["id"], prj["tenant_id"]):
                await q.edit_message_text("Нет доступа к этому проекту.", reply_markup=projects_menu_kb()); return
        set_user_ctx(u["id"], tenant_id=prj["tenant_id"], project_pk=prj["id"])
        text = (f"Проект выбран: {prj['name']} (ID {prj['project_id']})\n"
                f"Канал: {prj['channel_id'] or 'не подключён'}\n"
                f"TZ: {prj['tz']}\n"
                f"Подключение по ID: {'ON' if prj['allow_id_join'] else 'OFF'}")
        await q.edit_message_text(text, reply_markup=project_card_kb(prj))
    elif data.startswith("prj:bind:"):
        _, _, pk = data.split(":"); pk = int(pk)
        with db() as conn:
            c = conn.cursor()
            prj = c.execute("SELECT * FROM projects WHERE id=?", (pk,)).fetchone()
        if not prj or not user_has_access_to_project(u["id"], prj["tenant_id"]):
            await q.edit_message_text("Нет доступа.", reply_markup=projects_menu_kb()); return
        context.user_data["bind_project_pk"] = pk
        await q.edit_message_text(
            "Шаги привязки канала:\n"
            "1) Добавьте этого бота админом в ваш канал.\n"
            "2) Для публичного канала пришлите @username.\n"
            "3) Для приватного — просто перешлите из канала любое сообщение сюда.\n"
            "После этого нажмите “Проверить доступ”.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Проверить доступ", callback_data=f"prj:check:{pk}")],
                [InlineKeyboardButton("Назад к проекту", callback_data=f"prj:select:{pk}")]
            ])
        )
        return ASK_BIND_INSTRUCTION
    elif data.startswith("prj:check:"):
        _, _, pk = data.split(":"); pk = int(pk)
        await check_channel_permissions(update, context, pk)
    elif data.startswith("prj:toggle_join:"):
        _, _, pk = data.split(":"); pk = int(pk)
        with db() as conn:
            c = conn.cursor()
            prj = c.execute("SELECT * FROM projects WHERE id=?", (pk,)).fetchone()
        if not prj or not user_has_access_to_project(u["id"], prj["tenant_id"]):
            await q.edit_message_text("Нет доступа.", reply_markup=projects_menu_kb()); return
        new_val = 0 if prj["allow_id_join"] else 1
        toggle_allow_id_join(pk, bool(new_val))
        with db() as conn:
            c = conn.cursor()
            prj2 = c.execute("SELECT * FROM projects WHERE id=?", (pk,)).fetchone()
        await q.edit_message_text("Настройка обновлена.", reply_markup=project_card_kb(prj2))

# Input handlers (conversations)
async def on_project_id_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_project_id"):
        return ConversationHandler.END
    text = (update.effective_message.text or "").strip()
    try:
        pid = int(text)
    except:
        await update.effective_chat.send_message("Project ID должен быть числом. Попробуйте снова.")
        return ConversationHandler.END
    u = await get_context_user(update)
    await activate_by_id_flow(update, context, u, pid)
    context.user_data["awaiting_project_id"] = False
    return ConversationHandler.END

async def on_new_project_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_new_project_name"):
        return ConversationHandler.END
    name = (update.effective_message.text or "").strip()
    if not name:
        await update.effective_chat.send_message("Имя проекта не может быть пустым.")
        return ConversationHandler.END
    u = await get_context_user(update)
    tenant_id = create_tenant(name=name)
    add_membership(tenant_id, u["id"], "owner")
    prj = create_project(tenant_id, name=name, tz=DEFAULT_TZ)
    set_project_owner(prj["id"], u["id"])
    set_user_ctx(u["id"], tenant_id=tenant_id, project_pk=prj["id"], week_label=None)
    await update.effective_chat.send_message(
        f"Создан новый проект:\n"
        f"- Название: {prj['name']}\n- Project ID: {prj['project_id']}\n- TZ: {prj['tz']}\n\nСохраните ID: его вводят клиенты для активации.",
        reply_markup=project_card_kb(prj)
    )
    context.user_data["awaiting_new_project_name"] = False
    return ConversationHandler.END

async def on_bind_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pk = context.user_data.get("bind_project_pk")
    if not pk:
        return ConversationHandler.END
    msg: Message = update.effective_message
    if msg.forward_from_chat and msg.forward_from_chat.id:
        channel_id = str(msg.forward_from_chat.id)
        set_project_channel(pk, channel_id)
        await update.effective_chat.send_message(f"Канал привязан по chat_id: {channel_id}.\nНажмите “Проверить доступ”.")
        return ConversationHandler.END
    if msg.text and msg.text.strip().startswith("@"):
        set_project_channel(pk, msg.text.strip())
        await update.effective_chat.send_message(f"Канал записан как {msg.text.strip()}.\nНажмите “Проверить доступ”.")
        return ConversationHandler.END
    await update.effective_chat.send_message("Пришлите @username публичного канала или перешлите сообщение из приватного канала.")

# ----- Week flows -----

async def week_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = await get_context_user(update)
    ctx = get_user_ctx(u["id"])
    if not ctx["current_project_pk"]:
        await q.edit_message_text("Сначала выберите проект.", reply_markup=projects_menu_kb()); return
    with db() as conn:
        c = conn.cursor()
        prj = c.execute("SELECT * FROM projects WHERE id=?", (ctx["current_project_pk"],)).fetchone()
    tzinfo = ZoneInfo(prj["tz"])
    today = datetime.now(tzinfo).date()
    w = upsert_week(prj["tenant_id"], prj["id"], today)
    set_user_ctx(u["id"], week_label=w["week_label"])
    await q.edit_message_text(f"Неделя создана/выбрана: {w['week_label']}", reply_markup=week_menu_kb())

async def week_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = await get_context_user(update)
    ctx = get_user_ctx(u["id"])
    if not (ctx["current_project_pk"] and ctx["current_week_label"]):
        await q.edit_message_text("Сначала создайте/выберите неделю.", reply_markup=week_menu_kb()); return
    with db() as conn:
        c = conn.cursor()
        posts = c.execute("""SELECT post_no,title,status,publish_at FROM posts
                             WHERE tenant_id=(SELECT tenant_id FROM projects WHERE id=?)
                               AND project_id=? AND week_label=?
                             ORDER BY post_no""",
                          (ctx["current_project_pk"], ctx["current_project_pk"], ctx["current_week_label"])).fetchall()
    if not posts:
        await q.edit_message_text(f"Неделя {ctx['current_week_label']}: постов пока нет.", reply_markup=week_menu_kb()); return
    lines = [f"{p['post_no']}. {p['title'] or 'Без заголовка'} | {p['status']} | {p['publish_at'] or '—'}" for p in posts]
    await q.edit_message_text("Сводка:\n" + "\n".join(lines), reply_markup=week_menu_kb())

async def week_gen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    if not (ctx["current_project_pk"] and ctx["current_week_label"]):
        await q.edit_message_text("Сначала создайте неделю.", reply_markup=week_menu_kb()); return
    with db() as conn:
        c = conn.cursor()
        prj = c.execute("SELECT * FROM projects WHERE id=?", (ctx["current_project_pk"],)).fetchone()
        wk = c.execute("""SELECT * FROM weeks WHERE tenant_id=? AND project_id=? AND week_label=?""",
                       (prj["tenant_id"], prj["id"], ctx["current_week_label"])).fetchone()
    from datetime import date as dt_date
    generate_week_drafts(prj["tenant_id"], prj["id"], ctx["current_week_label"], prj["tz"], dt_date.fromisoformat(wk["start_date"]))
    await q.edit_message_text(f"Созданы/обновлены черновики 7 постов для {ctx['current_week_label']}.", reply_markup=week_menu_kb())

async def week_shift_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    if not (ctx["current_project_pk"] and ctx["current_week_label"]):
        await q.edit_message_text("Сначала создайте неделю.", reply_markup=week_menu_kb()); return
    with db() as conn:
        c = conn.cursor()
        rows = c.execute("""SELECT id,publish_at FROM posts
                            WHERE project_id=? AND week_label=?""",
                         (ctx["current_project_pk"], ctx["current_week_label"])).fetchall()
        for r in rows:
            if not r["publish_at"]: continue
            dt = datetime.fromisoformat(r["publish_at"]).replace(tzinfo=ZoneInfo("UTC"))
            nd = dt + timedelta(days=1)
            c.execute("UPDATE posts SET publish_at=?, updated_at=? WHERE id=?", (nd.isoformat(), now_iso(), r["id"]))
        conn.commit()
    await q.edit_message_text("Расписание всей недели сдвинуто на +1 день.", reply_markup=week_menu_kb())

async def week_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    if not (ctx["current_project_pk"] and ctx["current_week_label"]):
        await q.edit_message_text("Сначала создайте неделю.", reply_markup=week_menu_kb()); return
    with db() as conn:
        c = conn.cursor()
        posts = [dict(r) for r in c.execute("""SELECT * FROM posts
                                               WHERE project_id=? AND week_label=?
                                               ORDER BY post_no""",
                                             (ctx["current_project_pk"], ctx["current_week_label"])).fetchall()]
    if len(posts) < 7:
        await q.edit_message_text("В неделе меньше 7 постов. Сгенерируйте черновики.", reply_markup=week_menu_kб()); return
    problems = {}
    for p in posts:
        issues = validate_post(dict(p))
        if issues: problems[p["post_no"]] = issues
    if problems:
        lines = ["Нужно исправить перед Approve:"]
        for no, issues in problems.items():
            lines.append(f"Пост {no}: " + "; ".join(issues))
        await q.edit_message_text("\n".join(lines), reply_markup=week_menu_kb())
        return
    with db() as conn:
        c = conn.cursor()
        c.execute("""UPDATE posts SET status='approved', updated_at=? WHERE project_id=? AND week_label=?""",
                  (now_iso(), ctx["current_project_pk"], ctx["current_week_label"]))
        conn.commit()
    await schedule_week_posts(context, ctx["current_project_pk"], ctx["current_week_label"])
    await q.edit_message_text(f"Неделя {ctx['current_week_label']} одобрена. Посты запланированы.", reply_markup=week_menu_kb())

async def schedule_week_posts(context: ContextTypes.DEFAULT_TYPE, project_pk: int, week_label: str):
    with db() as conn:
        c = conn.cursor()
        posts = [dict(r) for r in c.execute("""SELECT p.*, prj.tenant_id
                                               FROM posts p
                                               JOIN projects prj ON prj.id = p.project_id
                                               WHERE p.project_id=? AND p.week_label=?
                                               ORDER BY p.post_no""",
                                             (project_pk, week_label)).fetchall()]
    for p in posts:
        if p["status"] != "approved" or not p.get("publish_at"):
            continue
        when_utc = datetime.fromisoformat(p["publish_at"]).replace(tzinfo=ZoneInfo("UTC"))
        await schedule_post_job(context, p["tenant_id"], project_pk, p["id"], when_utc)

async def schedule_post_job(context: ContextTypes.DEFAULT_TYPE, tenant_id: int, project_pk: int, post_id: int, when_utc: datetime):
    job_name = f"{tenant_id}-{project_pk}-pub-{post_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    context.job_queue.run_once(publish_job, when=when_utc, name=job_name, data={"tenant_id": tenant_id, "project_pk": project_pk, "post_id": post_id})

# ----- Posts UI -----

def posts_list_text(project_pk: int, week_label: str) -> str:
    with db() as conn:
        c = conn.cursor()
        rows = c.execute("""SELECT post_no,title,status FROM posts
                            WHERE project_id=? AND week_label=?
                            ORDER BY post_no""", (project_pk, week_label)).fetchall()
    lines = [f"{r['post_no']}. {r['title'] or 'Без заголовка'} — {r['status']}" for r in rows]
    return "\n".join(lines) if lines else "Постов нет."

async def post_open(update: Update, context: ContextTypes.DEFAULT_TYPE, week_label: str, post_no: int):
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    if not ctx["current_project_pk"]:
        await update.callback_query.edit_message_text("Проект не выбран.", reply_markup=projects_menu_kb()); return
    with db() as conn:
        c = conn.cursor()
        p = c.execute("""SELECT * FROM posts WHERE project_id=? AND week_label=? AND post_no=?""",
                      (ctx["current_project_pk"], week_label, post_no)).fetchone()
    if not p:
        await update.callback_query.edit_message_text("Пост не найден.", reply_markup=posts_menu_kb(week_label)); return
    txt = f"Пост {post_no} ({p['status']})\nЗаголовок: {p['title'] or '—'}\nДата/время (UTC): {p['publish_at'] or '—'}\nProject ID: {get_project_pid_by_pk(ctx['current_project_pk'])}"
    await update.callback_query.edit_message_text(txt, reply_markup=post_actions_kb(week_label, post_no))

def get_project_pid_by_pk(project_pk: int) -> int:
    with db() as conn:
        c = conn.cursor()
        row = c.execute("SELECT project_id FROM projects WHERE id=?", (project_pk,)).fetchone()
        return row["project_id"] if row else 0

async def post_preview(update: Update, context: ContextTypes.DEFAULT_TYPE, week_label: str, post_no: int):
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    with db() as conn:
        c = conn.cursor()
        p = dict(c.execute("""SELECT * FROM posts WHERE project_id=? AND week_label=? AND post_no=?""",
                           (ctx["current_project_pk"], week_label, post_no)).fetchone())
    text = assemble_text(p)
    if p.get("cover_url"):
        await update.callback_query.message.reply_photo(photo=p["cover_url"], caption=text)
    else:
        await update.callback_query.message.reply_text(text)
    await update.callback_query.answer("Предпросмотр отправлен ниже.")

async def set_post_status(update: Update, context: ContextTypes.DEFAULT_TYPE, week_label: str, post_no: int, status: str):
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    with db() as conn:
        c = conn.cursor()
        c.execute("""UPDATE posts SET status=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                  (status, now_iso(), ctx["current_project_pk"], week_label, post_no))
        conn.commit()
    await update.callback_query.answer(f"Статус: {status}")
    await post_open(update, context, week_label, post_no)

async def publish_now(update: Update, context: ContextTypes.DEFAULT_TYPE, week_label: str, post_no: int):
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    with db() as conn:
        c = conn.cursor()
        p = dict(c.execute("""SELECT p.*, prj.tenant_id, prj.channel_id
                              FROM posts p JOIN projects prj ON prj.id=p.project_id
                              WHERE p.project_id=? AND p.week_label=? AND p.post_no=?""",
                           (ctx["current_project_pk"], week_label, post_no)).fetchone())
    await do_publish_post(context, p["tenant_id"], p["project_id"], p["id"])

# ----- Edit fields conversation -----

async def start_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE, week_label: str, post_no: int, field: str):
    context.user_data["edit_ctx"] = {"week_label": week_label, "post_no": post_no, "field": field}
    await update.callback_query.message.reply_text(PFLD[field])
    await update.callback_query.answer()
    return EDIT_STATE

def parse_time_hhmm(s: str):
    hh, mm = s.split(":")
    return time(int(hh), int(mm))

async def on_edit_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ctx_u = context.user_data.get("edit_ctx", {})
    if not ctx_u:
        await update.effective_chat.send_message("Контекст редактирования утерян. Откройте пост заново.")
        return ConversationHandler.END
    u = await get_context_user(update); uctx = get_user_ctx(u["id"])
    week_label, post_no, field = ctx_u["week_label"], ctx_u["post_no"], ctx_u["field"]
    text = update.effective_message.text or ""
    with db() as conn:
        c = conn.cursor()
        now = now_iso()
        if field == "title":
            c.execute("""UPDATE posts SET title=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (text.strip()[:200], now, uctx["current_project_pk"], week_label, post_no))
        elif field == "lead":
            c.execute("""UPDATE posts SET lead=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (text.strip()[:400], now, uctx["current_project_pk"], week_label, post_no))
        elif field == "body":
            c.execute("""UPDATE posts SET body=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (text.strip(), now, uctx["current_project_pk"], week_label, post_no))
        elif field == "tags":
            tags = " ".join(text.strip().split())
            c.execute("""UPDATE posts SET tags=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (tags, now, uctx["current_project_pk"], week_label, post_no))
        elif field == "cta":
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            cta_text = lines[0] if lines else ""
            cta_url = lines[1] if len(lines) > 1 else ""
            c.execute("""UPDATE posts SET cta_text=?, cta_url=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (cta_text, cta_url, now, uctx["current_project_pk"], week_label, post_no))
        elif field == "cover":
            c.execute("""UPDATE posts SET cover_url=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (text.strip(), now, uctx["current_project_pk"], week_label, post_no))
        elif field == "dt":
            lines = [l.strip() for l in text.splitlines() if l.strip()]
            if len(lines) < 2:
                await update.effective_chat.send_message("Нужно две строки: дата и время. Пример:\n2025-09-10\n10:00")
                return ConversationHandler.END
            d = date.fromisoformat(lines[0])
            t = parse_time_hhmm(lines[1])
            with db() as conn2:
                cc = conn2.cursor()
                prj = cc.execute("SELECT tz FROM projects WHERE id=?", (uctx["current_project_pk"],)).fetchone()
            tzinfo = ZoneInfo(prj["tz"])
            local_dt = datetime.combine(d, t, tzinfo=tzinfo)
            utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
            c.execute("""UPDATE posts SET publish_at=?, updated_at=? WHERE project_id=? AND week_label=? AND post_no=?""",
                      (utc_dt.isoformat(), now, uctx["current_project_pk"], week_label, post_no))
        conn.commit()
    await update.effective_chat.send_message("Сохранено.")
    await post_open(update, context, week_label, post_no)
    return ConversationHandler.END

# ----- Publishing -----

async def publish_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    await do_publish_post(context, data["tenant_id"], data["project_pk"], data["post_id"])

async def do_publish_post(context: ContextTypes.DEFAULT_TYPE, tenant_id: int, project_pk: int, post_id: int):
    with db() as conn:
        c = conn.cursor()
        p = c.execute("""SELECT p.*, prj.channel_id FROM posts p
                         JOIN projects prj ON prj.id=p.project_id
                         WHERE p.id=?""", (post_id,)).fetchone()
        if not p:
            return
        channel_id = p["channel_id"]
        if not channel_id:
            return
        text = assemble_text(dict(p))
    msg = None
    try:
        if p["cover_url"]:
            msg = await context.bot.send_photo(chat_id=channel_id, photo=p["cover_url"], caption=text)
        else:
            msg = await context.bot.send_message(chat_id=channel_id, text=text)
        with db() as conn:
            c = conn.cursor()
            c.execute("""UPDATE posts SET status='published', message_id=?, updated_at=? WHERE id=?""",
                      (msg.message_id, now_iso(), post_id))
            c.execute("""INSERT INTO publish_log(tenant_id,project_id,post_id,ts,platform,result,message_id)
                         VALUES(?,?,?,?,?,?,?)""",
                      (tenant_id, project_pk, post_id, now_iso(), "telegram", "OK", msg.message_id))
            conn.commit()
    except Exception as e:
        err = str(e)[:500]
        with db() as conn:
            c = conn.cursor()
            c.execute("""UPDATE posts SET status='failed', error_note=?, updated_at=? WHERE id=?""",
                      (err, now_iso(), post_id))
            c.execute("""INSERT INTO publish_log(tenant_id,project_id,post_id,ts,platform,result,error_note)
                         VALUES(?,?,?,?,?,?,?)""",
                      (tenant_id, project_pk, post_id, now_iso(), "telegram", "FAILED", err))
            conn.commit()
        context.job_queue.run_once(publish_job, when=timedelta(minutes=3), data={"tenant_id": tenant_id, "project_pk": project_pk, "post_id": post_id}, name=f"{tenant_id}-{project_pk}-retry-{post_id}")

# ----- Export / Backup -----

def export_week_json(project_pk: int, week_label: str) -> dict:
    with db() as conn:
        c = conn.cursor()
        w = c.execute("""SELECT * FROM weeks WHERE project_id=? AND week_label=?""", (project_pk, week_label)).fetchone()
        posts = [dict(r) for r in c.execute("""SELECT * FROM posts WHERE project_id=? AND week_label=? ORDER BY post_no""",
                                            (project_pk, week_label)).fetchall()]
    return {
        "project_pk": project_pk,
        "week": dict(w) if w else {"week_label": week_label},
        "posts": posts
    }

async def export_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    data = q.data
    u = await get_context_user(update); ctx = get_user_ctx(u["id"])
    if data == "export:week_json":
        if not (ctx["current_project_pk"] and ctx["current_week_label"]):
            await q.edit_message_text("Неделя не выбрана.", reply_markup=week_menu_kb()); return
        payload = json.dumps(export_week_json(ctx["current_project_pk"], ctx["current_week_label"]), ensure_ascii=False, indent=2)
        await q.message.reply_document(document=("week_export.json", payload.encode("utf-8")))
        await q.edit_message_text("Экспорт отправлен файлом.", reply_markup=root_menu_kb())
    elif data == "export:toggle_backup":
        await q.edit_message_text("Автобэкап включён по умолчанию (владелец проекта получит ежедневный JSON).", reply_markup=root_menu_kb())

async def daily_backup_job(context: ContextTypes.DEFAULT_TYPE):
    with db() as conn:
        c = conn.cursor()
        projects = c.execute("""SELECT p.*, u.tg_user_id AS owner_tg
                                FROM projects p
                                LEFT JOIN users u ON u.id = p.owner_user_id
                                WHERE p.status='active'""").fetchall()
    for prj in projects:
        with db() as conn:
            c = conn.cursor()
            w = c.execute("""SELECT * FROM weeks WHERE project_id=? ORDER BY created_at DESC LIMIT 1""", (prj["id"],)).fetchone()
        if not w:
            continue
        data = export_week_json(prj["id"], w["week_label"])
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        target_tg = prj["owner_tg"]
        if not target_tg:
            with db() as conn:
                c = conn.cursor()
                admin = c.execute("""SELECT u.tg_user_id FROM memberships m
                                     JOIN users u ON u.id=m.user_id
                                     WHERE m.tenant_id=? AND m.role IN ('owner','admin') AND m.status='active'
                                     ORDER BY CASE WHEN m.role='owner' THEN 0 ELSE 1 END
                                     LIMIT 1""", (prj["tenant_id"],)).fetchone()
            if admin:
                target_tg = admin["tg_user_id"]
        if target_tg:
            try:
                await context.bot.send_document(chat_id=target_tg, document=("week_backup.json", payload), caption=f"Бэкап проекта {prj['name']} (ID {prj['project_id']}) — неделя {w['week_label']}")
            except:
                pass

# ----- Channel binding checks -----

async def check_channel_permissions(update: Update, context: ContextTypes.DEFAULT_TYPE, project_pk: int):
    q = update.callback_query
    with db() as conn:
        c = conn.cursor()
        prj = c.execute("SELECT * FROM projects WHERE id=?", (project_pk,)).fetchone()
    if not prj:
        await q.edit_message_text("Проект не найден.", reply_markup=projects_menu_kb()); return
    channel_id = prj["channel_id"]
    if not channel_id:
        await q.edit_message_text("Канал не указан. Пришлите @username или перешлите сообщение из канала в чат с ботом.", reply_markup=project_card_kb(prj)); return
    ok = False
    can_post = False
    try:
        chat = await context.bot.get_chat(channel_id)
        admins = await context.bot.get_chat_administrators(chat.id)
        bot_id = (await context.bot.get_me()).id
        for mem in admins:
            if getattr(mem.user, "id", None) == bot_id:
                ok = True
                if isinstance(mem, (ChatMemberAdministrator, ChatMemberOwner)) or mem.status in ("administrator", "creator"):
                    can_post = True
                break
        if ok and can_post:
            m = await context.bot.send_message(chat_id=chat.id, text="Тест: бот подключен и может публиковать. Сообщение будет удалено.")
            try:
                await context.bot.delete_message(chat_id=chat.id, message_id=m.message_id)
            except:
                pass
    except Exception as e:
        await q.edit_message_text(f"Ошибка проверки: {e}", reply_markup=project_card_kb(prj))
        return
    if ok and can_post:
        await q.edit_message_text(f"Канал подключён, права ок. Project ID: {prj['project_id']}\nКанал: {prj['channel_id']}", reply_markup=project_card_kb(prj))
    else:
        await q.edit_message_text("Бот не найден среди админов или нет прав на публикацию. Добавьте бота админом в канал и повторите проверку.", reply_markup=project_card_kb(prj))

# ----- Callback router -----

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    if data.startswith("menu:"):
        await menu_router(update, context); return
    if data.startswith("prj:"):
        res = await prj_router(update, context)
        if isinstance(res, int):
            return res
        return
    if data.startswith("week:"):
        action = data.split(":")[1]
        if action == "create":
            await week_create(update, context)
        elif action == "summary":
            await week_summary(update, context)
        elif action == "gen":
            await week_gen(update, context)
        elif action == "approve":
            await week_approve(update, context)
        elif action == "shift_day":
            await week_shift_day(update, context)
        return
    if data.startswith("posts:list:"):
        _, _, wl = data.split(":")
        u = await get_context_user(update); ctx = get_user_ctx(u["id"])
        txt = posts_list_text(ctx["current_project_pk"], wl)
        await q.edit_message_text(f"Посты недели {wl}:\n{txt}", reply_markup=posts_menu_kb(wl))
        return
    if data.startswith("post:open:"):
        _, _, wl, no = data.split(":")
        await post_open(update, context, wl, int(no)); return
    if data.startswith("post:preview:"):
        _, _, wl, no = data.split(":")
        await post_preview(update, context, wl, int(no)); return
    if data.startswith("post:set_status:"):
        _, _, wl, no, st = data.split(":")
        await set_post_status(update, context, wl, int(no), st); return
    if data.startswith("post:publish_now:"):
        _, _, wl, no = data.split(":")
        await publish_now(update, context, wl, int(no)); return
    for key in ["edit_title","edit_lead","edit_body","edit_tags","edit_cta","edit_cover","edit_dt"]:
        if data.startswith(f"post:{key}:"):
            _, _, wl, no = data.split(":")
            field = key.replace("edit_","")
            return await start_edit_field(update, context, wl, int(no), field)

# ----- Conversations object -----

def build_conversations():
    return ConversationHandler(
        entry_points=[],
        states={
            ASK_PROJECT_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_project_id_received)],
            ASK_NEW_PROJECT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_new_project_name)],
            ASK_BIND_INSTRUCTION: [MessageHandler(filters.ALL, on_bind_input)],
            EDIT_STATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, on_edit_value)],
        },
        fallbacks=[],
        per_chat=True,
        per_user=True,
    )

# ----- Daily backup scheduling -----

def setup_jobs(app: Application):
    # Планируем бэкап по локальному времени DEFAULT_TZ без tzinfo в run_daily
    try:
        local_tz = ZoneInfo(DEFAULT_TZ)
    except Exception:
        local_tz = ZoneInfo("UTC")

    now_local = datetime.now(local_tz)
    backup_local = now_local.replace(
        hour=SETTINGS.backup_hour,
        minute=SETTINGS.backup_minute,
        second=0, microsecond=0
    )
    if backup_local <= now_local:
        backup_local = backup_local + timedelta(days=1)

    backup_utc = backup_local.astimezone(ZoneInfo("UTC"))
    delay = (backup_utc - datetime.now(ZoneInfo("UTC"))).total_seconds()

    app.job_queue.run_once(daily_backup_job, when=delay, name="daily-backup-initial")
    app.job_queue.run_repeating(daily_backup_job, interval=timedelta(days=1), first=timedelta(days=1), name="daily-backup")

# ----- Utilities -----

def ensure_initial_state():
    # Optional: можно предзаполнить демо-данные, если нужно.
    pass

# ----- Main -----

def build_app() -> Application:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан.")
    init_db()
    ensure_initial_state()

    builder = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN)
    # Опционально: базовый URL/таймауты из .env
    if SETTINGS.telegram_api_base:
        builder = builder.base_url(SETTINGS.telegram_api_base)
    builder = builder.read_timeout(SETTINGS.telegram_api_read_timeout).connect_timeout(SETTINGS.telegram_api_connect_timeout)

    app = builder.build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate_cmd))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(build_conversations())
    setup_jobs(app)
    return app

def main():
    app = build_app()
    print(f"{APP_NAME} запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()