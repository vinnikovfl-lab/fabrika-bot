# services/payments.py
# Платежи и подписки для бота «Фабрика Будущего».
# Полный файл: инициализация БД (SQLite), create_payment, get_payments, get_subscription, cancel_subscription.
# ВАЖНО: Экспортируются асинхронные функции, совместимые с текущими хендлерами (await payments.*).
# Внутри — синхронная логика на sqlite3, обёрнутая в run_in_executor для безопасности.

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import List, Optional, Tuple, Any
from datetime import datetime
import asyncio

# Путь к базе. Можно переопределить через ENV: DB_PATH
DB_PATH = os.getenv("DB_PATH", "bot_data.sqlite3")

# Схема таблиц
SQL_CREATE_PAYMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'RUB',
    description TEXT NOT NULL DEFAULT 'Manual',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SQL_CREATE_SUBSCRIPTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY,
    plan TEXT NOT NULL DEFAULT 'basic',     -- basic | pro (или твои тарифы)
    price REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',  -- active | canceled | paused
    next_charge_at TIMESTAMP,               -- дата следующего списания (NULL если нет)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

# Триггер обновления updated_at (если нужно)
SQL_CREATE_TRIGGER_SUBS_UPDATED_AT = """
CREATE TRIGGER IF NOT EXISTS trg_subscriptions_updated_at
AFTER UPDATE ON subscriptions
FOR EACH ROW
BEGIN
    UPDATE subscriptions SET updated_at = CURRENT_TIMESTAMP WHERE user_id = NEW.user_id;
END;
"""

@contextmanager
def get_conn():
    """Контекстный менеджер безопасного подключения к SQLite (autocommit после блока)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def _init_db_sync() -> None:
    """Синхронная инициализация таблиц."""
    with get_conn() as conn:
        conn.execute(SQL_CREATE_PAYMENTS_TABLE)
        conn.execute(SQL_CREATE_SUBSCRIPTIONS_TABLE)
        conn.execute(SQL_CREATE_TRIGGER_SUBS_UPDATED_AT)

@dataclass
class Payment:
    id: int
    user_id: int
    amount: float
    currency: str
    description: str
    created_at: str  # строка из SQLite (формат 'YYYY-MM-DD HH:MM:SS')

@dataclass
class Subscription:
    user_id: int
    plan: str
    price: float
    status: str
    next_charge_at: Optional[str]  # может быть None/строка 'YYYY-MM-DD HH:MM:SS'
    updated_at: str
    created_at: str

# ----------------------------
# Внутренняя синхронная логика
# ----------------------------
def _create_payment_sync(user_id: int, amount: float, currency: str = "RUB", description: str = "Manual") -> Payment:
    if amount <= 0:
        raise ValueError("amount must be > 0")
    _init_db_sync()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO payments (user_id, amount, currency, description) VALUES (?, ?, ?, ?)",
            (int(user_id), float(amount), currency.strip() or "RUB", description.strip() or "Manual")
        )
        new_id = cur.lastrowid
        row = conn.execute(
            "SELECT id, user_id, amount, currency, description, created_at FROM payments WHERE id = ?",
            (new_id,)
        ).fetchone()
    return Payment(*row)

def _get_payments_sync(user_id: int, limit: Optional[int] = None, offset: int = 0) -> List[Tuple[float, str, str, Any]]:
    """
    Возвращает список кортежей для совместимости с текущими хендлерами:
      (amount, currency, description, created_at_datetime_or_string)
    """
    _init_db_sync()
    sql = """
        SELECT amount, currency, description, created_at
        FROM payments
        WHERE user_id = ?
        ORDER BY id DESC
    """
    params: Tuple = (int(user_id),)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (int(user_id), int(limit), int(offset))

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    out: List[Tuple[float, str, str, Any]] = []
    for amount, currency, description, created_at in rows:
        # Пытаемся вернуть datetime для удобного форматирования в хендлерах
        dt: Any
        try:
            # SQLite CURRENT_TIMESTAMP формата 'YYYY-MM-DD HH:MM:SS'
            dt = datetime.fromisoformat(str(created_at))
        except Exception:
            dt = created_at  # оставляем строку, хендлер подстрахован проверками
        out.append((amount, currency, description, dt))
    return out

def _get_subscription_sync(user_id: int) -> Optional[Tuple[int, str, float, str, Any]]:
    """
    Возвращает кортеж для совместимости с текущими хендлерами:
      (user_id, plan, price, status, next_charge_at_datetime_or_string)
    или None, если подписка не найдена.
    """
    _init_db_sync()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT user_id, plan, price, status, next_charge_at FROM subscriptions WHERE user_id = ?",
            (int(user_id),)
        ).fetchone()
    if not row:
        return None
    uid, plan, price, status, next_charge_at = row
    try:
        dt = datetime.fromisoformat(str(next_charge_at)) if next_charge_at else None
    except Exception:
        dt = next_charge_at
    return (uid, plan, float(price), status, dt)

def _cancel_subscription_sync(user_id: int) -> bool:
    """
    Ставит статус 'canceled' для подписки пользователя. Возвращает True, если обновили запись.
    Если подписки нет — возвращает False.
    """
    _init_db_sync()
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE subscriptions SET status = 'canceled' WHERE user_id = ? AND status != 'canceled'",
            (int(user_id),)
        )
        return cur.rowcount > 0

# Дополнительно: утилита для создания/обновления подписки (на будущее)
def _upsert_subscription_sync(user_id: int, plan: str, price: float, status: str = "active", next_charge_at: Optional[str] = None) -> Subscription:
    _init_db_sync()
    with get_conn() as conn:
        existing = conn.execute("SELECT user_id FROM subscriptions WHERE user_id = ?", (int(user_id),)).fetchone()
        if existing:
            conn.execute(
                "UPDATE subscriptions SET plan = ?, price = ?, status = ?, next_charge_at = ? WHERE user_id = ?",
                (plan.strip(), float(price), status.strip(), next_charge_at, int(user_id))
            )
        else:
            conn.execute(
                "INSERT INTO subscriptions (user_id, plan, price, status, next_charge_at) VALUES (?, ?, ?, ?, ?)",
                (int(user_id), plan.strip(), float(price), status.strip(), next_charge_at)
            )
        row = conn.execute(
            "SELECT user_id, plan, price, status, next_charge_at, updated_at, created_at FROM subscriptions WHERE user_id = ?",
            (int(user_id),)
        ).fetchone()
    return Subscription(*row)

# --------------------------------
# Публичные асинхронные обёртки API
# --------------------------------
async def init_db() -> None:
    """Асинхронная инициализация БД (вызывает синхронную внутри)."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _init_db_sync)

async def create_payment(user_id: int, amount: float, currency: str = "RUB", description: str = "Manual") -> Payment:
    """Создать платёж и вернуть Payment (для хендлеров нужен .id)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _create_payment_sync, user_id, amount, currency, description)

async def get_payments(user_id: int, limit: Optional[int] = None, offset: int = 0) -> List[Tuple[float, str, str, Any]]:
    """
    Получить платежи пользователя (amount, currency, description, created_at_dt_or_str), отсортированные по id DESC.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_payments_sync, user_id, limit, offset)

async def get_subscription(user_id: int) -> Optional[Tuple[int, str, float, str, Any]]:
    """
    Получить подписку пользователя: (user_id, plan, price, status, next_charge_at_dt_or_str) или None.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_subscription_sync, user_id)

async def cancel_subscription(user_id: int) -> bool:
    """Отменить подписку (status = 'canceled'). True, если запись была обновлена."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _cancel_subscription_sync, user_id)

# На будущее: ассинхронная обёртка upsert подписки (если потребуется в оплате)
async def upsert_subscription(user_id: int, plan: str, price: float, status: str = "active", next_charge_at: Optional[str] = None) -> Subscription:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _upsert_subscription_sync, user_id, plan, price, status, next_charge_at)