import random
from dataclasses import dataclass
from typing import Optional

from db.repo_users import get_user_by_tg, update_user_fields, get_or_create_user
from db.repo_cats import list_user_cats
from domain.constants import RARITY_CONFIG
from utils.time import now_ts


MEW_COOLDOWN_SECONDS = 7 * 60          # 7 minutes
PASSIVE_MIN_INTERVAL_SECONDS = 15 * 60 # 15 minutes


@dataclass(frozen=True)
class MewResult:
    ok: bool
    gained: int
    passive_gained: int
    total: int
    cooldown_left: int


def _cat_mph(cat: dict) -> float:
    rarity = cat.get("rarity", "common")
    base = float(RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"]).get("base_mph", 1.0))
    level = int(cat.get("level", 1))
    level_mult = 1.0 + (level - 1) * 0.1
    return base * level_mult


def apply_passive_income(telegram_id: int, user_db_id: int) -> int:
    """
    هر ۱۵ دقیقه یک بار، درآمد غیرفعال را محاسبه و به کاربر اضافه می‌کند.
    فرمول ساده v1:
      total_mph = sum(cat_mph)
      gained = int(total_mph * hours_elapsed)
    """
    user = get_user_by_tg(telegram_id)
    if not user:
        return 0

    now = now_ts()
    last_passive = int(user.get("last_passive_ts") or user.get("created_at") or now)
    elapsed = max(0, now - last_passive)

    if elapsed < PASSIVE_MIN_INTERVAL_SECONDS:
        return 0

    cats = list_user_cats(user_db_id, include_dead=False)
    if not cats:
        update_user_fields(telegram_id, last_passive_ts=now)
        return 0

    total_mph = 0.0
    for c in cats:
        total_mph += _cat_mph(c)

    hours = elapsed / 3600.0
    gained = int(total_mph * hours)

    if gained > 0:
        current = int(user.get("mew_points") or 0)
        update_user_fields(
            telegram_id,
            mew_points=current + gained,
            last_passive_ts=now,
        )
    else:
        update_user_fields(telegram_id, last_passive_ts=now)

    return gained


def mew_action(telegram_id: int, username: Optional[str]) -> MewResult:
    """
    منطق mew + اعمال passive قبل از پاسخ
    """
    user_db_id = get_or_create_user(telegram_id, username)
    user = get_user_by_tg(telegram_id)
    if not user:
        return MewResult(ok=False, gained=0, passive_gained=0, total=0, cooldown_left=0)

    passive_gained = apply_passive_income(telegram_id, user_db_id)

    # reload after passive
    user = get_user_by_tg(telegram_id) or user

    now = now_ts()
    last_mew = int(user.get("last_mew_ts") or 0)
    diff = now - last_mew

    if diff < MEW_COOLDOWN_SECONDS:
        left = MEW_COOLDOWN_SECONDS - diff
        return MewResult(
            ok=False,
            gained=0,
            passive_gained=passive_gained,
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

    return MewResult(ok=True, gained=gained, passive_gained=passive_gained, total=total, cooldown_left=0)
