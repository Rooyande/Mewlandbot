import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    db_path: str
    parse_mode: str = "HTML"


def _must_get(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise RuntimeError(f"{name} is not set")
    return v


def load_settings() -> Settings:
    return Settings(
        bot_token=_must_get("BOT_TOKEN"),
        admin_id=int(os.getenv("ADMIN_ID", "8423995337")),
        db_path=os.getenv("DB_PATH", os.getenv("DATABASE_URL", "mewland.db")),
        parse_mode=os.getenv("PARSE_MODE", "HTML"),
    )

