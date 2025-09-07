# config.py
import os
import re
from dataclasses import dataclass
from typing import List, Optional

try:
    from dotenv import load_dotenv  # pip install python-dotenv
    load_dotenv()
except Exception:
    pass

def _split_ints(s: str) -> List[int]:
    if not s:
        return []
    parts = [p for p in re.split(r"[,\s]+", s.strip()) if p]
    out = []
    for p in parts:
        try:
            out.append(int(p))
        except:
            pass
    return out

def _sqlite_path_from_url(url: str) -> Optional[str]:
    # sqlite:///fabrika.db -> fabrika.db
    # sqlite:////absolute/path.db -> /absolute/path.db
    if not url:
        return None
    if not url.startswith("sqlite"):
        return None
    m = re.match(r"sqlite:(?://)?/(.*)", url)
    if not m:
        return None
    path = m.group(1)
    if path.startswith("/"):
        return f"/{path.lstrip('/')}"
    return path

@dataclass(frozen=True)
class Settings:
    telegram_token: str
    default_tz: str
    bot_admin_ids: List[int]
    admin_username: Optional[str]
    database_path: str
    log_level: str
    backup_hour: int
    backup_minute: int
    telegram_api_base: Optional[str]
    telegram_api_read_timeout: int
    telegram_api_connect_timeout: int

def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    default_tz = os.getenv("DEFAULT_TZ", "Europe/Moscow").strip()

    # Суперадмины: поддерживаем ADMIN_IDS и BOT_ADMIN_IDS
    admin_ids_raw = os.getenv("ADMIN_IDS", os.getenv("BOT_ADMIN_IDS", ""))
    bot_admin_ids = _split_ints(admin_ids_raw)

    admin_username = (os.getenv("ADMIN_ID") or "").strip() or None

    # DB: DATABASE_PATH приоритетно, иначе берём из DATABASE_URL_SYNC (sqlite)
    db_path = (os.getenv("DATABASE_PATH") or "").strip()
    if not db_path:
        db_url = os.getenv("DATABASE_URL_SYNC", "").strip()
        db_path = _sqlite_path_from_url(db_url) or "bot.db"
    if not db_path:
        db_path = "bot.db"

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
    backup_hour = int(os.getenv("BACKUP_HOUR", "23"))
    backup_minute = int(os.getenv("BACKUP_MINUTE", "59"))

    telegram_api_base = (os.getenv("TELEGRAM_API_BASE") or "").strip() or None
    read_to = int(os.getenv("TELEGRAM_API_READ_TIMEOUT", "30"))
    conn_to = int(os.getenv("TELEGRAM_API_CONNECT_TIMEOUT", "30"))

    return Settings(
        telegram_token=token,
        default_tz=default_tz,
        bot_admin_ids=bot_admin_ids,
        admin_username=admin_username,
        database_path=db_path,
        log_level=log_level,
        backup_hour=backup_hour,
        backup_minute=backup_minute,
        telegram_api_base=telegram_api_base,
        telegram_api_read_timeout=read_to,
        telegram_api_connect_timeout=conn_to,
    )