# services/help.py
# FAQ сервис для «Фабрика Будущего» с безопасными асинхронными обёртками.
# Полный файл: инициализация БД (SQLite), CRUD для FAQ, run_in_executor, busy_timeout/PRAGMA.

import os
import sqlite3
from contextlib import contextmanager
from typing import List, Optional, Tuple
import asyncio

DB_PATH = os.getenv("DB_PATH", "bot_data.sqlite3")

SQL_CREATE_FAQ_TABLE = """
CREATE TABLE IF NOT EXISTS faq (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer   TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

def _open_conn() -> sqlite3.Connection:
    # Открываем с разумным таймаутом на блокировки и включаем JOURNAL=WAL для устойчивости.
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    # Включим WAL и некоторые pragma один раз на соединение.
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
    except Exception:
        pass
    return conn

@contextmanager
def _get_conn():
    conn = _open_conn()
    try:
        yield conn
    finally:
        conn.close()

def _init_db_sync() -> None:
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            conn.execute(SQL_CREATE_FAQ_TABLE)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _add_faq_sync(question: str, answer: str) -> int:
    if not question or not answer:
        raise ValueError("question/answer must be non-empty")
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "INSERT INTO faq (question, answer) VALUES (?, ?)",
                (question.strip(), answer.strip())
            )
            last_id = cur.lastrowid
            conn.execute("COMMIT")
            return last_id
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _get_faq_sync(limit: Optional[int] = None, offset: int = 0) -> List[Tuple[int, str, str, str]]:
    _init_db_sync()
    sql = "SELECT id, question, answer, created_at FROM faq ORDER BY id DESC"
    params: Tuple = tuple()
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (int(limit), int(offset))
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return rows

def _get_faq_by_id_sync(faq_id: int) -> Optional[Tuple[int, str, str, str]]:
    _init_db_sync()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, question, answer, created_at FROM faq WHERE id = ?",
            (int(faq_id),)
        ).fetchone()
    return row

def _update_faq_sync(faq_id: int, question: Optional[str] = None, answer: Optional[str] = None) -> bool:
    if question is None and answer is None:
        return False
    _init_db_sync()
    sets = []
    params: list = []
    if question is not None:
        sets.append("question = ?")
        params.append(question.strip())
    if answer is not None:
        sets.append("answer = ?")
        params.append(answer.strip())
    params.append(int(faq_id))
    sql = f"UPDATE faq SET {', '.join(sets)} WHERE id = ?"
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(sql, tuple(params))
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _delete_faq_sync(faq_id: int) -> bool:
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute("DELETE FROM faq WHERE id = ?", (int(faq_id),))
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception:
            conn.execute("ROLLBACK")
            raise

# -------------------------
# Публичные асинхронные API
# -------------------------
async def init_db() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _init_db_sync)

async def add_faq(question: str, answer: str) -> int:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _add_faq_sync, question, answer)

async def get_faq(limit: Optional[int] = None, offset: int = 0) -> List[Tuple[int, str, str, str]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_faq_sync, limit, offset)

async def get_faq_by_id(faq_id: int) -> Optional[Tuple[int, str, str, str]]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_faq_by_id_sync, faq_id)

async def update_faq(faq_id: int, question: Optional[str] = None, answer: Optional[str] = None) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _update_faq_sync, faq_id, question, answer)

async def delete_faq(faq_id: int) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _delete_faq_sync, faq_id)