# services/posts.py
# Расширенный сервис постов для «Фабрика Будущего» с workflow согласования и ревизиями.
# Асинхронные обёртки (run_in_executor) поверх sqlite3. Безопасные транзакции и простые миграции.

import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple, Dict, Any
import asyncio
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "bot_data.sqlite3")

# Разрешённые статусы workflow
ALLOWED_STATUSES = {
    "draft",
    "on_review",
    "approved",
    "revisions_requested",
    "scheduled",
    "published",
    "archived",
}

SQL_CREATE_POSTS_TABLE = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    review_comment TEXT,
    reviewer_id INTEGER,
    scheduled_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SQL_CREATE_REVISIONS_TABLE = """
CREATE TABLE IF NOT EXISTS post_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    author_id INTEGER,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(post_id) REFERENCES posts(id) ON DELETE CASCADE
);
"""

SQL_CREATE_TRIGGER_UPDATED_AT = """
CREATE TRIGGER IF NOT EXISTS trg_posts_updated_at
AFTER UPDATE ON posts
FOR EACH ROW
BEGIN
    UPDATE posts SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;
"""

def _open_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=10000;")
        # Включим foreign keys для каскадного удаления ревизий
        conn.execute("PRAGMA foreign_keys=ON;")
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

def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return column in cols

def _init_db_sync() -> None:
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            # Базовые таблицы
            conn.execute(SQL_CREATE_POSTS_TABLE)
            conn.execute(SQL_CREATE_REVISIONS_TABLE)
            conn.execute(SQL_CREATE_TRIGGER_UPDATED_AT)

            # Миграции: добавляем недостающие столбцы, если база существующая
            # review_comment
            if not _column_exists(conn, "posts", "review_comment"):
                conn.execute("ALTER TABLE posts ADD COLUMN review_comment TEXT")
            # reviewer_id
            if not _column_exists(conn, "posts", "reviewer_id"):
                conn.execute("ALTER TABLE posts ADD COLUMN reviewer_id INTEGER")
            # scheduled_at
            if not _column_exists(conn, "posts", "scheduled_at"):
                conn.execute("ALTER TABLE posts ADD COLUMN scheduled_at TIMESTAMP")
            # status (уже был, но если старая база — гарантируем допустимые значения логикой приложения)

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

@dataclass
class Post:
    id: int
    title: str
    content: str
    status: str
    review_comment: Optional[str]
    reviewer_id: Optional[int]
    scheduled_at: Optional[str]
    created_at: str
    updated_at: str

@dataclass
class PostWithRevisions:
    post: Post
    revisions: List[Dict[str, Any]]

# -----------------------------
# СИНХРОННЫЕ (в executor)
# -----------------------------
def _normalize_status(status: Optional[str]) -> str:
    st = (status or "draft").strip().lower()
    if st not in ALLOWED_STATUSES:
        st = "draft"
    return st

def _row_to_post(row: Tuple) -> Post:
    # row: id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at
    return Post(
        id=row[0],
        title=row[1],
        content=row[2],
        status=row[3],
        review_comment=row[4],
        reviewer_id=row[5],
        scheduled_at=row[6],
        created_at=row[7],
        updated_at=row[8],
    )

def _create_post_sync(title: str, content: str, status: str = "draft") -> Post:
    if not title or not content:
        raise ValueError("title/content must be non-empty")
    status = _normalize_status(status)
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "INSERT INTO posts (title, content, status) VALUES (?, ?, ?)",
                (title.strip(), content.strip(), status)
            )
            new_id = cur.lastrowid
            row = conn.execute(
                "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at "
                "FROM posts WHERE id = ?",
                (new_id,)
            ).fetchone()
            conn.execute("COMMIT")
            return _row_to_post(row)
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _get_post_sync(post_id: int) -> Optional[Post]:
    _init_db_sync()
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at "
            "FROM posts WHERE id = ?",
            (int(post_id),)
        ).fetchone()
    return _row_to_post(row) if row else None

def _list_posts_sync(
    status: Optional[str] = None,
    limit: Optional[int] = None,
    offset: int = 0,
    order: str = "DESC"
) -> List[Post]:
    _init_db_sync()
    order = "DESC" if str(order).upper() != "ASC" else "ASC"
    sql = "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at FROM posts"
    params: Tuple = tuple()
    if status:
        sql += " WHERE status = ?"
        params = (status.strip().lower(),)
    sql += f" ORDER BY id {order}"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (*params, int(limit), int(offset))
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_post(r) for r in rows]

def _update_post_sync(
    post_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    status: Optional[str] = None,
    review_comment: Optional[str] = None,
    reviewer_id: Optional[int] = None,
    scheduled_at: Optional[str] = None
) -> Optional[Post]:
    if all(v is None for v in [title, content, status, review_comment, reviewer_id, scheduled_at]):
        return _get_post_sync(post_id)

    _init_db_sync()
    sets = []
    params: list = []
    if title is not None:
        sets.append("title = ?")
        params.append(title.strip())
    if content is not None:
        sets.append("content = ?")
        params.append(content.strip())
    if status is not None:
        sets.append("status = ?")
        params.append(_normalize_status(status))
    if review_comment is not None:
        sets.append("review_comment = ?")
        params.append(review_comment)
    if reviewer_id is not None:
        sets.append("reviewer_id = ?")
        params.append(int(reviewer_id))
    if scheduled_at is not None:
        sets.append("scheduled_at = ?")
        params.append(scheduled_at)  # ожидается ISO-строка или None

    params.append(int(post_id))
    sql = f"UPDATE posts SET {', '.join(sets)} WHERE id = ?"

    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(sql, tuple(params))
            if cur.rowcount == 0:
                conn.execute("COMMIT")
                return None
            row = conn.execute(
                "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at "
                "FROM posts WHERE id = ?",
                (int(post_id),)
            ).fetchone()
            conn.execute("COMMIT")
            return _row_to_post(row) if row else None
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _delete_post_sync(post_id: int) -> bool:
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute("DELETE FROM posts WHERE id = ?", (int(post_id),))
            conn.execute("COMMIT")
            return cur.rowcount > 0
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _get_current_week_posts_sync(limit: Optional[int] = None, offset: int = 0) -> List[Post]:
    _init_db_sync()
    sql = """
        SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at
        FROM posts
        WHERE strftime('%Y', created_at) = strftime('%Y', 'now')
          AND strftime('%W', created_at) = strftime('%W', 'now')
        ORDER BY id DESC
    """
    params: Tuple = tuple()
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (int(limit), int(offset))
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_post(r) for r in rows]

def _search_posts_sync(query: str, limit: Optional[int] = 20, offset: int = 0) -> List[Post]:
    _init_db_sync()
    pattern = f"%{query.strip()}%"
    sql = """
        SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at
        FROM posts
        WHERE title LIKE ? OR content LIKE ?
        ORDER BY id DESC
    """
    params: Tuple = (pattern, pattern)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (*params, int(limit), int(offset))
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_post(r) for r in rows]

def _set_status_sync(post_id: int, status: str, reviewer_id: Optional[int] = None, review_comment: Optional[str] = None) -> Optional[Post]:
    status = _normalize_status(status)
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            params: list = [status]
            sets = ["status = ?"]

            if review_comment is not None:
                sets.append("review_comment = ?")
                params.append(review_comment)

            if reviewer_id is not None:
                sets.append("reviewer_id = ?")
                params.append(int(reviewer_id))

            params.append(int(post_id))
            sql = f"UPDATE posts SET {', '.join(sets)} WHERE id = ?"
            cur = conn.execute(sql, tuple(params))
            if cur.rowcount == 0:
                conn.execute("COMMIT")
                return None
            row = conn.execute(
                "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at "
                "FROM posts WHERE id = ?",
                (int(post_id),)
            ).fetchone()
            conn.execute("COMMIT")
            return _row_to_post(row) if row else None
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _set_schedule_sync(post_id: int, scheduled_at: Optional[str]) -> Optional[Post]:
    # scheduled_at ожидается в ISO-формате, например: "2025-09-06 14:30"
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            cur = conn.execute(
                "UPDATE posts SET scheduled_at = ?, status = CASE WHEN ? IS NULL THEN status ELSE 'scheduled' END WHERE id = ?",
                (scheduled_at, scheduled_at, int(post_id))
            )
            if cur.rowcount == 0:
                conn.execute("COMMIT")
                return None
            row = conn.execute(
                "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at "
                "FROM posts WHERE id = ?",
                (int(post_id),)
            ).fetchone()
            conn.execute("COMMIT")
            return _row_to_post(row) if row else None
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _get_next_revision_number(conn: sqlite3.Connection, post_id: int) -> int:
    row = conn.execute(
        "SELECT MAX(version) FROM post_revisions WHERE post_id = ?",
        (int(post_id),)
    ).fetchone()
    max_ver = row[0] if row and row[0] is not None else 0
    return int(max_ver) + 1

def _add_revision_sync(post_id: int, content: str, author_id: Optional[int], note: Optional[str]) -> Dict[str, Any]:
    if not content:
        raise ValueError("revision content must be non-empty")
    _init_db_sync()
    with _get_conn() as conn:
        conn.execute("BEGIN")
        try:
            # проверим, что пост существует
            exists = conn.execute("SELECT 1 FROM posts WHERE id = ?", (int(post_id),)).fetchone()
            if not exists:
                conn.execute("ROLLBACK")
                return {}

            version = _get_next_revision_number(conn, post_id)
            cur = conn.execute(
                "INSERT INTO post_revisions (post_id, version, content, author_id, note) VALUES (?, ?, ?, ?, ?)",
                (int(post_id), version, content, author_id, note)
            )
            rev_id = cur.lastrowid
            row = conn.execute(
                "SELECT id, post_id, version, content, author_id, note, created_at FROM post_revisions WHERE id = ?",
                (rev_id,)
            ).fetchone()
            conn.execute("COMMIT")
            return {
                "id": row[0],
                "post_id": row[1],
                "version": row[2],
                "content": row[3],
                "author_id": row[4],
                "note": row[5],
                "created_at": row[6],
            }
        except Exception:
            conn.execute("ROLLBACK")
            raise

def _get_post_with_revisions_sync(post_id: int) -> Optional[PostWithRevisions]:
    _init_db_sync()
    with _get_conn() as conn:
        post_row = conn.execute(
            "SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at "
            "FROM posts WHERE id = ?",
            (int(post_id),)
        ).fetchone()
        if not post_row:
            return None
        rev_rows = conn.execute(
            "SELECT id, post_id, version, content, author_id, note, created_at "
            "FROM post_revisions WHERE post_id = ? ORDER BY version DESC",
            (int(post_id),)
        ).fetchall()
    post = _row_to_post(post_row)
    revisions = [
        {
            "id": r[0],
            "post_id": r[1],
            "version": r[2],
            "content": r[3],
            "author_id": r[4],
            "note": r[5],
            "created_at": r[6],
        } for r in rev_rows
    ]
    return PostWithRevisions(post=post, revisions=revisions)

def _list_by_status_sync(status: str, limit: Optional[int] = 20, offset: int = 0) -> List[Post]:
    _init_db_sync()
    st = _normalize_status(status)
    sql = """
        SELECT id, title, content, status, review_comment, reviewer_id, scheduled_at, created_at, updated_at
        FROM posts
        WHERE status = ?
        ORDER BY id DESC
    """
    params: Tuple = (st,)
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = (*params, int(limit), int(offset))
    with _get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_post(r) for r in rows]

# -----------------------------
# ПУБЛИЧНЫЕ АСИНХРОННЫЕ API
# -----------------------------
async def init_db() -> None:
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _init_db_sync)

async def create_post(title: str, content: str, status: str = "draft") -> Post:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _create_post_sync, title, content, status)

async def get_post(post_id: int) -> Optional[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_post_sync, post_id)

async def list_posts(status: Optional[str] = None, limit: Optional[int] = None, offset: int = 0, order: str = "DESC") -> List[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _list_posts_sync, status, limit, offset, order)

async def update_post(
    post_id: int,
    title: Optional[str] = None,
    content: Optional[str] = None,
    status: Optional[str] = None,
    review_comment: Optional[str] = None,
    reviewer_id: Optional[int] = None,
    scheduled_at: Optional[str] = None
) -> Optional[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _update_post_sync, post_id, title, content, status, review_comment, reviewer_id, scheduled_at
    )

async def delete_post(post_id: int) -> bool:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _delete_post_sync, post_id)

async def get_current_week_posts(limit: Optional[int] = None, offset: int = 0) -> List[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_current_week_posts_sync, limit, offset)

async def search_posts(query: str, limit: Optional[int] = 20, offset: int = 0) -> List[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _search_posts_sync, query, limit, offset)

async def set_status(post_id: int, status: str, reviewer_id: Optional[int] = None, review_comment: Optional[str] = None) -> Optional[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_status_sync, post_id, status, reviewer_id, review_comment)

async def set_schedule(post_id: int, scheduled_at: Optional[str]) -> Optional[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_schedule_sync, post_id, scheduled_at)

async def add_revision(post_id: int, content: str, author_id: Optional[int] = None, note: Optional[str] = None) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _add_revision_sync, post_id, content, author_id, note)

async def get_post_with_revisions(post_id: int) -> Optional[PostWithRevisions]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_post_with_revisions_sync, post_id)

async def list_by_status(status: str, limit: Optional[int] = 20, offset: int = 0) -> List[Post]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _list_by_status_sync, status, limit, offset)