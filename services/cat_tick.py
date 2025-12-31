import time
from typing import Dict, Any, Optional

from db.repo_cats import update_cat_fields


HUNGER_DECAY_PER_HOUR = 8
HAPPINESS_DECAY_PER_HOUR = 5
CAT_DEATH_TIMEOUT_SECONDS = 36 * 3600  # 36 hours


def apply_cat_tick(cat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    بر اساس زمان سپری‌شده از last_tick_ts:
    - گرسنگی و خوشحالی کاهش می‌یابد
    - اگر گرسنگی صفر بماند و زمان زیاد باشد => مرگ
    خروجی: cat آپدیت‌شده یا None اگر مرده
    """
    now = int(time.time())
    last_ts = int(cat.get("last_tick_ts") or cat.get("created_at") or now)
    elapsed = max(0, now - last_ts)

    if elapsed < 60:
        return cat

    hours = elapsed / 3600.0
    hunger = int(cat.get("hunger", 100) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = int(cat.get("happiness", 100) - HAPPINESS_DECAY_PER_HOUR * hours)

    hunger = max(0, min(100, hunger))
    happiness = max(0, min(100, happiness))

    if hunger <= 0 and elapsed > CAT_DEATH_TIMEOUT_SECONDS:
        return None

    cat2 = dict(cat)
    cat2["hunger"] = hunger
    cat2["happiness"] = happiness
    cat2["last_tick_ts"] = now
    return cat2


def persist_tick(owner_id: int, cat: Dict[str, Any]) -> None:
    update_cat_fields(
        cat_id=int(cat["id"]),
        owner_id=owner_id,
        hunger=int(cat.get("hunger", 100)),
        happiness=int(cat.get("happiness", 100)),
        last_tick_ts=int(cat.get("last_tick_ts", int(time.time()))),
    )
