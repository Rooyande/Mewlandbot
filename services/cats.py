# services/cats.py
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# تلاش می‌کنیم تنظیمات را از core.config بگیریم؛ اگر نبود، فایل همچنان import می‌شود.
try:
    from core import config
except Exception:  # pragma: no cover
    config = None  # type: ignore


# ====== DB Repos (اختیاری/قابل جایگزینی) ======
# اگر ساختار repoها در پروژه‌ات متفاوت است، فقط همین importها را هم‌نام کن.
try:
    from db import repo_users, repo_cats
except Exception:  # pragma: no cover
    repo_users = None  # type: ignore
    repo_cats = None  # type: ignore

try:
    from db import repo_achievements
except Exception:  # pragma: no cover
    repo_achievements = None  # type: ignore


# =========================
# Exceptions (Service-level)
# =========================

class ServiceError(Exception):
    pass


class NotFound(ServiceError):
    pass


class NotEnoughPoints(ServiceError):
    pass


class InvalidInput(ServiceError):
    pass


class CooldownActive(ServiceError):
    pass


class Forbidden(ServiceError):
    pass


# =========================
# Config Helpers / Defaults
# =========================

def _cfg(name: str, default: Any) -> Any:
    if config is None:
        return default
    return getattr(config, name, default)


RARITY_CONFIG: Dict[str, Dict[str, Any]] = _cfg("RARITY_CONFIG", {
    "common": {"price": 200, "base_mph": 1.0, "emoji": "⚪️", "breeding_cost": 100},
    "rare": {"price": 800, "base_mph": 3.0, "emoji": "🟦", "breeding_cost": 300},
    "epic": {"price": 2500, "base_mph": 7.0, "emoji": "🟪", "breeding_cost": 1000},
    "legendary": {"price": 7000, "base_mph": 15.0, "emoji": "🟨", "breeding_cost": 3000},
    "mythic": {"price": 15000, "base_mph": 30.0, "emoji": "🟥", "breeding_cost": 7000},
    "special": {"price": 50000, "base_mph": 50.0, "emoji": "🌟", "breeding_cost": 15000},
})

RARITY_WEIGHTS: List[Tuple[str, int]] = _cfg("RARITY_WEIGHTS", [
    ("common", 50),
    ("rare", 23),
    ("epic", 12),
    ("legendary", 8),
    ("mythic", 5),
    ("special", 2),
])

GEAR_ITEMS: Dict[str, Dict[str, Any]] = _cfg("GEAR_ITEMS", {})

ELEMENTS: List[str] = _cfg("ELEMENTS", ["fire", "water", "earth", "air", "shadow", "light", "ice", "candy"])
TRAITS: List[str] = _cfg("TRAITS", ["lazy", "hyper", "greedy", "cuddly", "brave", "shy", "noisy", "sleepy"])

BASE_XP_PER_LEVEL: int = int(_cfg("BASE_XP_PER_LEVEL", 100))
XP_MULTIPLIER: float = float(_cfg("XP_MULTIPLIER", 1.5))

HUNGER_DECAY_PER_HOUR: int = int(_cfg("HUNGER_DECAY_PER_HOUR", 8))
HAPPINESS_DECAY_PER_HOUR: int = int(_cfg("HAPPINESS_DECAY_PER_HOUR", 5))
CAT_DEATH_TIMEOUT: int = int(_cfg("CAT_DEATH_TIMEOUT", 129600))  # 36h

MARKET_FEE_PERCENT: int = int(_cfg("MARKET_FEE_PERCENT", 5))

# رویداد/فصل‌ها (اگر در config داری، همین‌ها را آنجا ست کن)
CHRISTMAS_EVENT_ACTIVE: bool = bool(_cfg("CHRISTMAS_EVENT_ACTIVE", False))
CHRISTMAS_EVENT_START: str = str(_cfg("CHRISTMAS_EVENT_START", "2024-12-01"))
CHRISTMAS_EVENT_END: str = str(_cfg("CHRISTMAS_EVENT_END", "2024-12-31"))
CHRISTMAS_REWARDS_MULTIPLIER: float = float(_cfg("CHRISTMAS_REWARDS_MULTIPLIER", 1.5))


# =========================
# DTOs
# =========================

@dataclass(frozen=True)
class TickOutcome:
    alive: bool
    cat: Optional[Dict[str, Any]]
    died_reason: Optional[str] = None


# =========================
# Pure Helpers
# =========================

def is_christmas_season(now_ts: Optional[int] = None) -> bool:
    if not CHRISTMAS_EVENT_ACTIVE:
        return False
    try:
        now_dt = datetime.fromtimestamp(now_ts or int(time.time()))
        start_date = datetime.strptime(CHRISTMAS_EVENT_START, "%Y-%m-%d").date()
        end_date = datetime.strptime(CHRISTMAS_EVENT_END, "%Y-%m-%d").date()
        return start_date <= now_dt.date() <= end_date
    except Exception:
        return False


def rarity_emoji(rarity: str) -> str:
    return RARITY_CONFIG.get(rarity, {}).get("emoji", "⚪️")


def choose_rarity() -> str:
    roll = random.randint(1, 100)
    cur = 0
    for r, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return r
    return "common"


def xp_required_for_level(level: int) -> int:
    # level=1 => 100, level=2 => 150, ...
    if level <= 1:
        return BASE_XP_PER_LEVEL
    return int(BASE_XP_PER_LEVEL * (XP_MULTIPLIER ** (level - 1)))


def parse_gear_codes(gear_field: Any) -> List[str]:
    if not gear_field:
        return []
    if isinstance(gear_field, list):
        return [str(x) for x in gear_field]
    return [g.strip() for g in str(gear_field).split(",") if g.strip()]


def compute_effective_stats(cat: Dict[str, Any]) -> Dict[str, int]:
    power = int(cat.get("stat_power", 1))
    agility = int(cat.get("stat_agility", 1))
    luck = int(cat.get("stat_luck", 1))

    for code in parse_gear_codes(cat.get("gear", "")):
        item = GEAR_ITEMS.get(code)
        if not item:
            continue
        power += int(item.get("power_bonus", 0))
        agility += int(item.get("agility_bonus", 0))
        luck += int(item.get("luck_bonus", 0))

    return {"power": power, "agility": agility, "luck": luck}


def compute_mph(cat: Dict[str, Any]) -> float:
    rarity = str(cat.get("rarity", "common"))
    conf = RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"])
    base = float(conf.get("base_mph", 1.0))

    level = int(cat.get("level", 1))
    level_mult = 1.0 + max(0, level - 1) * 0.1

    gear_bonus = 0.0
    for code in parse_gear_codes(cat.get("gear", "")):
        item = GEAR_ITEMS.get(code)
        if item:
            gear_bonus += float(item.get("mph_bonus", 0.0))

    stats = compute_effective_stats(cat)
    stat_bonus = (stats["power"] + stats["agility"] + stats["luck"]) * 0.02

    return base * level_mult + gear_bonus + stat_bonus


def apply_cat_tick(cat: Dict[str, Any], now_ts: Optional[int] = None) -> TickOutcome:
    now = int(now_ts or time.time())
    last_ts = int(cat.get("last_tick_ts") or cat.get("created_at") or now)
    elapsed = max(0, now - last_ts)

    # کمتر از ۱ دقیقه: بی‌خیال (نوسان نده)
    if elapsed < 60:
        return TickOutcome(alive=True, cat=cat)

    hours = elapsed / 3600.0
    hunger = int(cat.get("hunger", 100) - HUNGER_DECAY_PER_HOUR * hours)
    happiness = int(cat.get("happiness", 100) - HAPPINESS_DECAY_PER_HOUR * hours)

    hunger = max(0, min(100, hunger))
    happiness = max(0, min(100, happiness))

    # مرگ: اگر خیلی وقت گرسنه=۰ بوده
    if hunger <= 0 and elapsed > CAT_DEATH_TIMEOUT:
        return TickOutcome(alive=False, cat=None, died_reason="hunger_timeout")

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    return TickOutcome(alive=True, cat=cat)


# =========================
# Achievement hook (safe)
# =========================

def _award_achievement(user_db_id: int, achievement_id: str) -> None:
    """
    این تابع عمداً silent است.
    اگر repo_achievements هنوز آماده نباشد، هیچ اتفاقی نمی‌افتد.
    """
    if repo_achievements is None:
        return
    try:
        repo_achievements.add_achievement(user_db_id, achievement_id)
    except Exception:
        return


# =========================
# Service API (Cats)
# =========================

def adopt_cat(
    telegram_id: int,
    username: Optional[str],
    rarity: Optional[str] = None,
) -> Dict[str, Any]:
    """
    خرید گربه.
    خروجی: {cat_id, price, rarity, element, trait, name, points_after, christmas_discount_applied}
    """
    if repo_users is None or repo_cats is None:
        raise ServiceError("DB repos are not wired (repo_users/repo_cats).")

    user_db_id = repo_users.get_or_create_user(telegram_id, username)
    if not user_db_id:
        raise ServiceError("cannot create user")

    user = repo_users.get_user_by_telegram_id(telegram_id)
    if not user:
        raise ServiceError("user not found after create")

    # تعیین rarity
    if rarity:
        rarity = rarity.strip().lower()
        if rarity not in RARITY_CONFIG:
            raise InvalidInput("invalid rarity")
    else:
        rarity = choose_rarity()

    price = int(RARITY_CONFIG[rarity]["price"])
    christmas_discount = False
    if is_christmas_season():
        # مثال: ۱۰٪ تخفیف
        price = int(price * 0.9)
        christmas_discount = True

    points = int(user.get("mew_points", 0))
    if points < price:
        raise NotEnoughPoints(f"need={price}, have={points}")

    element = random.choice(ELEMENTS)
    trait = random.choice(TRAITS)
    name = f"گربهٔ {rarity}"

    cat_id = repo_cats.add_cat(
        owner_id=user_db_id,
        name=name,
        rarity=rarity,
        element=element,
        trait=trait,
        description=f"یک گربه‌ی {rarity} با عنصر {element} و خوی {trait}",
    )
    if not cat_id:
        raise ServiceError("failed to add cat")

    # کم کردن امتیاز
    repo_users.update_user_by_telegram_id(telegram_id, mew_points=points - price)

    # دستاوردها (هسته‌ای)
    try:
        cats = repo_cats.get_user_cats(user_db_id, include_dead=True)
        if len(cats) == 1:
            _award_achievement(user_db_id, "first_cat")
    except Exception:
        pass

    # دستاورد کریسمس نمونه
    if is_christmas_season():
        _award_achievement(user_db_id, "christmas_adopter")

    return {
        "user_db_id": user_db_id,
        "cat_id": cat_id,
        "price": price,
        "rarity": rarity,
        "element": element,
        "trait": trait,
        "name": name,
        "points_after": points - price,
        "christmas_discount_applied": christmas_discount,
    }


def list_user_cats(user_db_id: int) -> Dict[str, Any]:
    """
    خروجی: {alive: [...], dead_count: int}
    هر cat در لیست alive شامل mph و stats است.
    """
    if repo_cats is None:
        raise ServiceError("DB repos are not wired (repo_cats).")

    cats = repo_cats.get_user_cats(user_db_id, include_dead=True)

    alive: List[Dict[str, Any]] = []
    dead_count = 0

    for c in cats:
        # اگر alive=0 از DB، dead حساب کن
        if int(c.get("alive", 1)) != 1:
            dead_count += 1
            continue

        outcome = apply_cat_tick(c)
        if not outcome.alive or not outcome.cat:
            # مرگ
            try:
                repo_cats.kill_cat(c["id"], owner_id=user_db_id)
            except Exception:
                pass
            dead_count += 1
            continue

        updated = outcome.cat
        # ذخیره tick
        try:
            repo_cats.update_cat_stats(
                cat_id=int(updated["id"]),
                owner_id=user_db_id,
                hunger=int(updated.get("hunger", 100)),
                happiness=int(updated.get("happiness", 100)),
                last_tick_ts=int(updated.get("last_tick_ts", int(time.time()))),
            )
        except Exception:
            pass

        stats = compute_effective_stats(updated)
        mph = compute_mph(updated)
        updated_view = dict(updated)
        updated_view["effective_stats"] = stats
        updated_view["mph"] = mph
        updated_view["gear_codes"] = parse_gear_codes(updated.get("gear", ""))
        alive.append(updated_view)

    return {"alive": alive, "dead_count": dead_count}


def feed_cat(user_db_id: int, telegram_id: int, cat_id: int, amount: int) -> Dict[str, Any]:
    """
    amount: 1..100
    cost: amount*2
    خوشحالی: + amount//3
    """
    if repo_users is None or repo_cats is None:
        raise ServiceError("DB repos are not wired.")

    if amount <= 0 or amount > 100:
        raise InvalidInput("amount must be 1..100")

    user = repo_users.get_user_by_telegram_id(telegram_id)
    if not user:
        raise NotFound("user")

    cat = repo_cats.get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        raise NotFound("cat")

    outcome = apply_cat_tick(cat)
    if not outcome.alive or not outcome.cat:
        repo_cats.kill_cat(cat_id, owner_id=user_db_id)
        raise Forbidden("cat is dead")

    cost = amount * 2
    points = int(user.get("mew_points", 0))
    if points < cost:
        raise NotEnoughPoints(f"need={cost}, have={points}")

    updated = outcome.cat
    new_hunger = min(100, int(updated.get("hunger", 0)) + amount)
    new_happiness = min(100, int(updated.get("happiness", 0)) + (amount // 3))

    repo_cats.update_cat_stats(
        cat_id=cat_id,
        owner_id=user_db_id,
        hunger=new_hunger,
        happiness=new_happiness,
        last_tick_ts=int(updated.get("last_tick_ts", int(time.time()))),
    )
    repo_users.update_user_by_telegram_id(telegram_id, mew_points=points - cost)

    return {
        "cat_id": cat_id,
        "name": updated.get("name"),
        "hunger_before": int(updated.get("hunger", 0)),
        "hunger_after": new_hunger,
        "happiness_before": int(updated.get("happiness", 0)),
        "happiness_after": new_happiness,
        "cost": cost,
        "points_after": points - cost,
    }


def play_with_cat(user_db_id: int, cat_id: int) -> Dict[str, Any]:
    """
    happiness +15, hunger -5, xp +25
    """
    if repo_cats is None:
        raise ServiceError("DB repos are not wired (repo_cats).")

    cat = repo_cats.get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        raise NotFound("cat")

    outcome = apply_cat_tick(cat)
    if not outcome.alive or not outcome.cat:
        repo_cats.kill_cat(cat_id, owner_id=user_db_id)
        raise Forbidden("cat is dead")

    updated = outcome.cat
    happiness_before = int(updated.get("happiness", 0))
    hunger_before = int(updated.get("hunger", 0))
    xp_before = int(updated.get("xp", 0))
    level_before = int(updated.get("level", 1))

    happiness_after = min(100, happiness_before + 15)
    hunger_after = max(0, hunger_before - 5)
    xp_after = xp_before + 25
    level_after = level_before

    leveled_up = False
    while xp_after >= xp_required_for_level(level_after):
        xp_after -= xp_required_for_level(level_after)
        level_after += 1
        leveled_up = True

    repo_cats.update_cat_stats(
        cat_id=cat_id,
        owner_id=user_db_id,
        hunger=hunger_after,
        happiness=happiness_after,
        xp=xp_after,
        level=level_after,
        last_tick_ts=int(updated.get("last_tick_ts", int(time.time()))),
    )

    return {
        "cat_id": cat_id,
        "name": updated.get("name"),
        "happiness_before": happiness_before,
        "happiness_after": happiness_after,
        "hunger_before": hunger_before,
        "hunger_after": hunger_after,
        "xp_before": xp_before,
        "xp_after": xp_after,
        "level_before": level_before,
        "level_after": level_after,
        "leveled_up": leveled_up,
    }


def train_cat(user_db_id: int, telegram_id: int, cat_id: int, stat: str) -> Dict[str, Any]:
    """
    stat: power/agility/luck
    cost: current_stat*100
    """
    if repo_users is None or repo_cats is None:
        raise ServiceError("DB repos are not wired.")

    stat = stat.strip().lower()
    if stat not in ("power", "agility", "luck"):
        raise InvalidInput("stat must be power/agility/luck")

    user = repo_users.get_user_by_telegram_id(telegram_id)
    if not user:
        raise NotFound("user")

    cat = repo_cats.get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        raise NotFound("cat")

    outcome = apply_cat_tick(cat)
    if not outcome.alive or not outcome.cat:
        repo_cats.kill_cat(cat_id, owner_id=user_db_id)
        raise Forbidden("cat is dead")

    current = int(cat.get(f"stat_{stat}", 1))
    cost = current * 100
    points = int(user.get("mew_points", 0))
    if points < cost:
        raise NotEnoughPoints(f"need={cost}, have={points}")

    new_val = current + 1
    repo_cats.update_cat_stats(cat_id=cat_id, owner_id=user_db_id, **{f"stat_{stat}": new_val})
    repo_users.update_user_by_telegram_id(telegram_id, mew_points=points - cost)

    return {
        "cat_id": cat_id,
        "name": cat.get("name"),
        "stat": stat,
        "before": current,
        "after": new_val,
        "cost": cost,
        "points_after": points - cost,
    }


def buy_gear(user_db_id: int, telegram_id: int, cat_id: int, gear_code: str) -> Dict[str, Any]:
    """
    خرید تجهیزات برای گربه.
    """
    if repo_users is None or repo_cats is None:
        raise ServiceError("DB repos are not wired.")
    gear_code = gear_code.strip().lower()

    if gear_code not in GEAR_ITEMS:
        raise InvalidInput("invalid gear code")

    item = GEAR_ITEMS[gear_code]

    user = repo_users.get_user_by_telegram_id(telegram_id)
    if not user:
        raise NotFound("user")

    cat = repo_cats.get_cat(cat_id, owner_id=user_db_id)
    if not cat:
        raise NotFound("cat")

    # شرط لول
    min_level = int(item.get("min_level", 1))
    if int(cat.get("level", 1)) < min_level:
        raise Forbidden("level too low")

    outcome = apply_cat_tick(cat)
    if not outcome.alive or not outcome.cat:
        repo_cats.kill_cat(cat_id, owner_id=user_db_id)
        raise Forbidden("cat is dead")

    points = int(user.get("mew_points", 0))
    price = int(item.get("price", 0))

    # تخفیف فصلی (نمونه)
    discount_applied = False
    if is_christmas_season() and bool(item.get("seasonal", False)):
        price = int(price * 0.8)
        discount_applied = True

    if points < price:
        raise NotEnoughPoints(f"need={price}, have={points}")

    gear_codes = parse_gear_codes(cat.get("gear", ""))
    if gear_code in gear_codes:
        raise InvalidInput("already equipped")

    gear_codes.append(gear_code)
    new_gear_str = ",".join(gear_codes)

    repo_cats.update_cat_stats(cat_id=cat_id, owner_id=user_db_id, gear=new_gear_str)
    repo_users.update_user_by_telegram_id(telegram_id, mew_points=points - price)

    updated_cat = dict(cat)
    updated_cat["gear"] = new_gear_str
    mph_after = compute_mph(updated_cat)

    return {
        "cat_id": cat_id,
        "cat_name": cat.get("name"),
        "gear_code": gear_code,
        "gear_name": item.get("name"),
        "price": price,
        "discount_applied": discount_applied,
        "points_after": points - price,
        "mph_after": mph_after,
    }


def fight(my_owner_db_id: int, my_cat_id: int, enemy_cat_id: int) -> Dict[str, Any]:
    """
    3 راند. نیاز به لول >= 9 برای هر دو.
    جایزه: برد => xp+50 و points+100 (اگر کریسمس: *multiplier)
    """
    if repo_cats is None or repo_users is None:
        raise ServiceError("DB repos are not wired.")

    my_cat = repo_cats.get_cat(my_cat_id, owner_id=my_owner_db_id)
    if not my_cat:
        raise NotFound("my_cat")

    enemy_cat = repo_cats.get_cat(enemy_cat_id, owner_id=None)
    if not enemy_cat:
        raise NotFound("enemy_cat")

    if int(my_cat.get("level", 1)) < 9 or int(enemy_cat.get("level", 1)) < 9:
        raise Forbidden("both cats must be level >= 9")

    my_stats = compute_effective_stats(my_cat)
    enemy_stats = compute_effective_stats(enemy_cat)

    my_score = 0
    enemy_score = 0
    rounds: List[Dict[str, Any]] = []

    for r in range(1, 4):
        my_roll = (
            my_stats["power"] * random.uniform(0.8, 1.2)
            + my_stats["agility"] * random.uniform(0.5, 1.0)
            + my_stats["luck"] * random.uniform(0.0, 0.5)
        )
        enemy_roll = (
            enemy_stats["power"] * random.uniform(0.8, 1.2)
            + enemy_stats["agility"] * random.uniform(0.5, 1.0)
            + enemy_stats["luck"] * random.uniform(0.0, 0.5)
        )

        if my_roll > enemy_roll:
            my_score += 1
            outcome = "win"
        elif enemy_roll > my_roll:
            enemy_score += 1
            outcome = "lose"
        else:
            outcome = "draw"

        rounds.append({"round": r, "my_roll": my_roll, "enemy_roll": enemy_roll, "outcome": outcome})

    result: str
    xp_gain = 0
    points_gain = 0
    leveled_up = False

    if my_score > enemy_score:
        result = "win"
        xp_gain = 50
        points_gain = 100

        if is_christmas_season():
            xp_gain = int(xp_gain * CHRISTMAS_REWARDS_MULTIPLIER)
            points_gain = int(points_gain * CHRISTMAS_REWARDS_MULTIPLIER)

        # XP/Level update
        new_xp = int(my_cat.get("xp", 0)) + xp_gain
        new_level = int(my_cat.get("level", 1))
        while new_xp >= xp_required_for_level(new_level):
            new_xp -= xp_required_for_level(new_level)
            new_level += 1
            leveled_up = True

        repo_cats.update_cat_stats(
            cat_id=my_cat_id,
            owner_id=my_owner_db_id,
            xp=new_xp,
            level=new_level,
            happiness=min(100, int(my_cat.get("happiness", 100)) + 20),
        )

        # points update
        owner = repo_users.get_user_by_db_id(my_owner_db_id)
        if owner:
            repo_users.update_user_by_db_id(my_owner_db_id, mew_points=int(owner.get("mew_points", 0)) + points_gain)

        _award_achievement(my_owner_db_id, "warrior")

    elif enemy_score > my_score:
        result = "lose"
        repo_cats.update_cat_stats(
            cat_id=my_cat_id,
            owner_id=my_owner_db_id,
            happiness=max(0, int(my_cat.get("happiness", 100)) - 10),
        )
    else:
        result = "draw"
        repo_cats.update_cat_stats(
            cat_id=my_cat_id,
            owner_id=my_owner_db_id,
            xp=int(my_cat.get("xp", 0)) + 10,
        )

    return {
        "result": result,
        "my_score": my_score,
        "enemy_score": enemy_score,
        "rounds": rounds,
        "xp_gain": xp_gain,
        "points_gain": points_gain,
        "leveled_up": leveled_up,
        "my_cat": {"id": my_cat_id, "name": my_cat.get("name")},
        "enemy_cat": {"id": enemy_cat_id, "name": enemy_cat.get("name")},
    }


def transfer_cat(from_owner_db_id: int, cat_id: int, target_user_db_id: int) -> Dict[str, Any]:
    """
    انتقال مالکیت گربه.
    """
    if repo_cats is None:
        raise ServiceError("DB repos are not wired (repo_cats).")

    cat = repo_cats.get_cat(cat_id, owner_id=from_owner_db_id)
    if not cat:
        raise NotFound("cat not owned")

    outcome = apply_cat_tick(cat)
    if not outcome.alive or not outcome.cat:
        repo_cats.kill_cat(cat_id, owner_id=from_owner_db_id)
        raise Forbidden("cat is dead")

    ok = repo_cats.set_cat_owner(cat_id, target_user_db_id)
    if not ok:
        raise ServiceError("transfer failed")

    if is_christmas_season():
        _award_achievement(from_owner_db_id, "gift_giver")

    return {
        "cat_id": cat_id,
        "cat_name": cat.get("name"),
        "from_owner_db_id": from_owner_db_id,
        "to_owner_db_id": target_user_db_id,
    }
