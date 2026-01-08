from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_telegram_id: int
    database_path: str


def get_settings() -> Settings:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN is not set in environment (.env)")

    admin_id_raw = os.getenv("ADMIN_TELEGRAM_ID", "").strip()
    if not admin_id_raw.isdigit():
        raise RuntimeError("ADMIN_TELEGRAM_ID must be a numeric Telegram user id")

    db_path = os.getenv("DATABASE_PATH", "data/app.sqlite3").strip()

    return Settings(
        bot_token=token,
        admin_telegram_id=int(admin_id_raw),
        database_path=db_path,
    )
