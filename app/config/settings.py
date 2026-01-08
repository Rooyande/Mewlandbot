from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_telegram_id: int

    # گروه‌های مجاز (قابل تنظیم از env)
    allowed_chat_ids: str = ""  # comma-separated

    # Database
    db_host: str
    db_port: int = 5432
    db_name: str
    db_user: str
    db_password: str
    DB_ECHO: bool = False
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    def allowed_chat_id_set(self) -> set[int]:
        out: set[int] = set()

        # 1) از env
        raw = (self.allowed_chat_ids or "").strip()
        if raw:
            for part in raw.split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    out.add(int(part))
                except ValueError:
                    continue

        # 2) از فایل allowlist (ادمین پنل)
        allowlist_file = Path("allowed_chats.txt")
        if allowlist_file.exists():
            for line in allowlist_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    out.add(int(line))
                except ValueError:
                    continue

        return out


settings = Settings()
