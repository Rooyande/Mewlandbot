import random
from dataclasses import dataclass
from typing import Optional

from db.repo_users import get_user_by_tg, update_user_fields, get_or_create_user
from utils.time import now_ts


MEW_COOLDOWN_SECONDS = 7 * 60  # 7 minutes


@dataclass(frozen=True)
class MewResult:
    ok: bool
    gained: int
    total: int
    cooldown_left: int


def mew_action(telegram_id: int, username: Optional[str]) -> MewResult:
    """
    منطق اصلی mew:
    - اگر کاربر وجود نداشت ساخته می‌شود
    - کول‌داون ۷ دقیقه
    - پاداش تصادفی ۱ تا ۵
    """
    get_or_create_user(telegram_id, username)
    user = get_user_by_tg(telegram_id)
    if not user:
        # حالت بسیار نادر: اگر DB مشکل داشت
        return MewResult(ok=False, gained=0, total=0, cooldown_left=0)

    now = now_ts()
    last_mew = int(user.get("last_mew_ts") or 0)
    diff = now - last_mew

    if diff < MEW_COOLDOWN_SECONDS:
        left = MEW_COOLDOWN_SECONDS - diff
        return MewResult(
            ok=False,
            gained=0,
            total=int(user.get("mew_points") or 0),
            cooldown_left=left,
        )

    gained = random.randint(1, 5)
    total = int(user.get("mew_points") or 0) + gained

    update_user_fields(
        telegram_id,
        mew_points=total,
        last_mew_ts=now,
    )

    return MewResult(ok=True, gained=gained, total=total, cooldown_left=0)

