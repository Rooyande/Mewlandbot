from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bot_token: str
    admin_telegram_id: int
    allowed_chat_ids: str = ""  # comma-separated

    def allowed_chat_id_set(self) -> set[int]:
        raw = (self.allowed_chat_ids or "").strip()
        if not raw:
            return set()
        out: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            out.add(int(part))
        return out


settings = Settings()
