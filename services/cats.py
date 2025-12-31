# services/cats.py
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from services.achievements import award_achievement

from db import repo_users, repo_cats


# =========================
#  Fallback-safe Game Config
# =========================
# اگر فایل‌های config جدا ساخته‌ای، این importها کار می‌کنند.
# اگر هنوز نداری، همین مقادیر پیش‌فرض استفاده می‌شوند.
try:
    from core.game_config import (  # type: ignore
        RARITY_CONFIG,
        RARITY_WEIGHTS,
        ELEMENTS,
        TRAITS,
        GEAR_ITEMS,
        HUNGER_DECAY_PER_HOUR,
        HAPPINESS_DECAY_PER_HOUR,
        CAT_DEATH_TIMEOUT,
        BASE_XP_PER_LEVEL,
        XP_MULTIPLIER,
    )
except Exception:
    RARITY_CONFIG: Dict[str, Dict[str, Any]] = {
        "common": {"price": 200, "base_mph": 1.0, "emoji": "⚪️", "breeding_cost": 100},
        "rare": {"price": 800, "base_mph": 3.0, "emoji": "🟦", "breeding_cost": 300},
        "epic": {"price": 2500, "base_mph": 7.0, "emoji": "🟪", "breeding_cost": 1000},
        "legendary": {"price": 7000, "base_mph": 15.0, "emoji": "🟨", "breeding_cost": 3000},
        "mythic": {"price": 15000, "base_mph": 30.0, "emoji": "🟥", "breeding_cost": 7000},
        "special": {"price": 50000, "base_mph": 50.0, "emoji": "🌟", "breeding_cost": 15000},
    }

    RARITY_WEIGHTS: List[Tuple[str, int]] = [
        ("common", 50),
        ("rare", 23),
        ("epic", 12),
        ("legendary", 8),
        ("mythic", 5),
        ("special", 2),
    ]

    ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light", "ice", "candy"]
    TRAITS = ["lazy", "hyper", "greedy", "cuddly", "brave", "shy", "noisy", "sleepy", "generous"]

    GEAR_ITEMS: Dict[str, Dict[str, Any]] = {
        "scarf": {
            "name": "🧣 شال گرم",
            "price": 500,
            "mph_bonus": 2.0,
            "power_bonus": 1,
            "agility_bonus": 0,
            "luck_bonus": 0,
            "min_level": 1,
        },
        "bell": {
            "name": "🔔 گردنبند زنگوله‌ای",
            "price": 800,
            "mph_bonus": 3.0,
            "power_bonus": 0,
            "agility_bonus": 1,
            "luck_bonus": 1,
            "min_level": 3,
        },
        "boots": {
            "name": "🥾 چکمه تریپ‌دار",
            "price": 1200,
            "mph_bonus": 1.0,
            "power_bonus": 0,
            "agility_bonus": 3,
            "luck_bonus": 0,
            "min_level": 5,
        },
        "crown": {
            "name": "👑 تاج سلطنتی",
            "price": 3000,
            "mph_bonus": 5.0,
            "power_bonus": 2,
            "agility_bonus": 1,
            "luck_bonus": 2,
            "min_level": 10,
        },
    }

    HUNGER_DECAY_PER_HOUR = 8
    HAPPINESS_DECAY_PER_HOUR = 5
    CAT_DEATH_TIMEOUT = 129600  # 36h
    BASE_XP_PER_LEVEL = 100
    XP_MULTIPLIER = 1.5


# =========================
# Exceptions (Service Layer)
# =========================
class ServiceError(Exception):
    pass


class ValidationError(ServiceError):
    pass


class NotEnoughPoints(ServiceError):
    pass


class NotFound(ServiceError):
    pass


class CatDead(ServiceError):
    pass


# =========================
# Helpers
# =========================
def rarity_emoji(rarity: str) -> str:
    return str(RARITY_CONFIG.get(rarity, {}).get("emoji", "⚪️"))


def choose_rarity() -> str:
    roll = random.randint(1, 100)
    cur = 0
    for rarity, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return rarity
    return "common"


def xp_required_for_level(level: int) -> int:
    if level <= 1:
        return int(BASE_XP_PER_LEVEL)
    return int(BASE_XP_PER_LEVEL * (XP_MULTIPLIER ** (level - 1)))


def parse_gear_codes(gear_field: Any) -> List[str]:
    if not gear_field:
        return []
    if isinstance(gear_field, list):
        return [str(x) for x in gear_field]
    return [g.strip() for g in str(gear_field).split(",") if g.strip()]


def compute_cat_effective_stats(cat: Dict[str, Any]) -> Dict[str, int]:
    power = int(cat.get("stat_power", 1))
    agility = int(cat.get("stat_agility", 1))
    luck = int(cat.get("stat_luck", 1))

    gear_codes = parse_gear_codes(cat.get("gear", ""))
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if not item:
            continue
        power += int(item.get("power_bonus", 0))
        agility += int(item.get("agility_bonus", 0))
        luck += int(item.get("luck_bonus", 0))

    return {"power": power, "agility": agility, "luck": luck}


def compute_cat_mph(cat: Dict[str, Any]) -> float:
    rarity = str(cat.get("rarity", "common"))
    conf = RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"])
    base = float(conf.get("base_mph", 1.0))

    level = int(cat.get("level", 1))
    level_mult = 1.0 + (max(1, level) - 1) * 0.1  # 10% per level

    gear_bonus = 0.0
    gear_codes = parse_gear_codes(cat.get("gear", ""))
    for code in gear_codes:
        item = GEAR_ITEMS.get(code)
        if item:
            gear_bonus += float(item.get("mph_bonus", 0.0))

    stats = compute_cat_effective_stats(cat)
    stat_bonus = (stats["power"] + stats["agility"] + stats["luck"]) * 0.02

    return base * level_mult + gear_bonus + stat_bonus


def apply_cat_tick(cat: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    # مرگ: فقط وقتی گرسنگی صفر باشد و مدت زیادی گذشته باشد
    if hunger <= 0 and elapsed > CAT_DEATH_TIMEOUT:
        return None

    cat["hunger"] = hunger
    cat["happiness"] = happiness
    cat["last_tick_ts"] = now
    return cat


# =========================
# DB Access (Repo Layer)
# =========================
@dataclass
class CatsService:
    """
    Handlerها فقط I/O تلگرام. این سرویس قوانین را اجرا می‌کند و دیتا را فقط از Repo می‌گیرد/می‌نویسد.
    """

    # -------- Users ----------
    def get_user_by_tg(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        return repo_users.get_user_by_tg(int(telegram_id))

    def get_or_create_user_id(self, telegram_id: int, username: Optional[str]) -> int:
        return int(repo_users.get_or_create_user(int(telegram_id), username))

    def update_user_points(self, telegram_id: int, new_points: int) -> None:
        repo_users.update_user_fields(int(telegram_id), mew_points=int(new_points))

    # -------- Cats ----------
    def get_user_cats(self, owner_id: int, include_dead: bool = False) -> List[Dict[str, Any]]:
        return repo_cats.list_user_cats(int(owner_id), include_dead=include_dead)

    def get_cat(self, cat_id: int, owner_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if owner_id is None:
            return repo_cats.get_cat(int(cat_id), None)
        return repo_cats.get_cat(int(cat_id), int(owner_id))

    def update_cat(self, cat_id: int, owner_id: Optional[int] = None, **fields: Any) -> None:
        if owner_id is None:
            repo_cats.update_cat_fields(int(cat_id), None, **fields)
        else:
            repo_cats.update_cat_fields(int(cat_id), int(owner_id), **fields)

    def kill_cat(self, cat_id: int, owner_id: Optional[int] = None) -> None:
        repo_cats.kill_cat(int(cat_id), int(owner_id) if owner_id is not None else None)

    def add_cat(
        self,
        owner_id: int,
        name: str,
        rarity: str,
        element: str,
        trait: str,
        description: str,
    ) -> int:
        return int(repo_cats.add_cat(int(owner_id), name, rarity, element, trait, description))

    # =========================
    # Business Use-Cases
    # =========================
    def adopt_cat(self, telegram_id: int, username: Optional[str], rarity: Optional[str] = None) -> Dict[str, Any]:
        user_id = self.get_or_create_user_id(telegram_id, username)
        user = self.get_user_by_tg(telegram_id)
        if not user:
            raise ServiceError("user load failed")

        if rarity is None:
            rarity = choose_rarity()
        rarity = rarity.strip().lower()

        if rarity not in RARITY_CONFIG:
            raise ValidationError("rarity_invalid")

        price = int(RARITY_CONFIG[rarity]["price"])
        points = int(user.get("mew_points", 0))

        if points < price:
            raise NotEnoughPoints(f"need={price},have={points}")

        element = random.choice(ELEMENTS)
        trait = random.choice(TRAITS)
        name = f"گربهٔ {rarity}"
        description = f"یک گربه‌ی {rarity} با عنصر {element} و خوی {trait}"

        cat_id = self.add_cat(user_id, name, rarity, element, trait, description)
        self.update_user_points(telegram_id, points - price)

        # ---- Achievements (first_cat) ----
        try:
            award_achievement(telegram_id, username, "first_cat")
        except Exception:
            pass

        return {
            "cat_id": cat_id,
            "rarity": rarity,
            "price": price,
            "element": element,
            "trait": trait,
            "new_points": points - price,
        }

    def list_cats_and_tick(self, owner_id: int) -> Dict[str, Any]:
        cats = self.get_user_cats(owner_id, include_dead=True)

        alive: List[Dict[str, Any]] = []
        dead_count = 0
        total_mph = 0.0

        for cat in cats:
            if int(cat.get("alive", 1)) != 1:
                continue

            updated = apply_cat_tick(cat)
            if not updated:
                self.kill_cat(int(cat["id"]), owner_id)
                dead_count += 1
                continue

            # persist tick
            self.update_cat(
                int(updated["id"]),
                owner_id,
                hunger=int(updated.get("hunger", 100)),
                happiness=int(updated.get("happiness", 100)),
                last_tick_ts=int(updated.get("last_tick_ts", int(time.time()))),
            )

            updated["mph"] = compute_cat_mph(updated)
            updated["eff_stats"] = compute_cat_effective_stats(updated)
            alive.append(updated)
            total_mph += float(updated["mph"])

        return {"cats": alive, "dead_count": dead_count, "total_mph": total_mph}

    def feed_cat(self, telegram_id: int, owner_id: int, cat_id: int, amount: int) -> Dict[str, Any]:
        if amount <= 0 or amount > 100:
            raise ValidationError("amount_invalid")

        user = self.get_user_by_tg(telegram_id)
        if not user:
            raise ServiceError("user load failed")

        points = int(user.get("mew_points", 0))
        cost = int(amount) * 2
        if points < cost:
            raise NotEnoughPoints(f"need={cost},have={points}")

        cat = self.get_cat(cat_id, owner_id)
        if not cat:
            raise NotFound("cat_not_found")

        updated = apply_cat_tick(cat)
        if not updated:
            self.kill_cat(cat_id, owner_id)
            raise CatDead("cat_dead")

        new_hunger = min(100, int(updated.get("hunger", 0)) + int(amount))
        new_happiness = min(100, int(updated.get("happiness", 0)) + (int(amount) // 3))

        self.update_cat(
            cat_id,
            owner_id,
            hunger=new_hunger,
            happiness=new_happiness,
            last_tick_ts=int(updated.get("last_tick_ts", int(time.time()))),
        )
        self.update_user_points(telegram_id, points - cost)

        return {
            "cat_name": updated.get("name", "گربه"),
            "old_hunger": int(updated.get("hunger", 0)),
            "new_hunger": new_hunger,
            "old_happiness": int(updated.get("happiness", 0)),
            "new_happiness": new_happiness,
            "cost": cost,
            "new_points": points - cost,
        }

    def play_cat(self, owner_id: int, cat_id: int) -> Dict[str, Any]:
        cat = self.get_cat(cat_id, owner_id)
        if not cat:
            raise NotFound("cat_not_found")

        updated = apply_cat_tick(cat)
        if not updated:
            self.kill_cat(cat_id, owner_id)
            raise CatDead("cat_dead")

        happiness_gain = 15
        hunger_loss = 5
        xp_gain = 25

        new_happiness = min(100, int(updated.get("happiness", 0)) + happiness_gain)
        new_hunger = max(0, int(updated.get("hunger", 0)) - hunger_loss)

        cur_xp = int(updated.get("xp", 0))
        cur_level = int(updated.get("level", 1))
        new_xp = cur_xp + xp_gain
        new_level = cur_level
        leveled_up = False

        while new_xp >= xp_required_for_level(new_level):
            new_xp -= xp_required_for_level(new_level)
            new_level += 1
            leveled_up = True

        self.update_cat(
            cat_id,
            owner_id,
            hunger=new_hunger,
            happiness=new_happiness,
            xp=new_xp,
            level=new_level,
            last_tick_ts=int(updated.get("last_tick_ts", int(time.time()))),
        )

        return {
            "cat_name": updated.get("name", "گربه"),
            "old_hunger": int(updated.get("hunger", 0)),
            "new_hunger": new_hunger,
            "old_happiness": int(updated.get("happiness", 0)),
            "new_happiness": new_happiness,
            "xp_gain": xp_gain,
            "new_xp": new_xp,
            "old_level": cur_level,
            "new_level": new_level,
            "leveled_up": leveled_up,
        }

    def train_cat(self, telegram_id: int, owner_id: int, cat_id: int, stat: str) -> Dict[str, Any]:
        stat = stat.strip().lower()
        if stat not in {"power", "agility", "luck"}:
            raise ValidationError("stat_invalid")

        user = self.get_user_by_tg(telegram_id)
        if not user:
            raise ServiceError("user load failed")
        points = int(user.get("mew_points", 0))

        cat = self.get_cat(cat_id, owner_id)
        if not cat:
            raise NotFound("cat_not_found")

        updated = apply_cat_tick(cat)
        if not updated:
            self.kill_cat(cat_id, owner_id)
            raise CatDead("cat_dead")

        field = f"stat_{stat}"
        current_stat = int(updated.get(field, 1))
        cost = current_stat * 100
        if points < cost:
            raise NotEnoughPoints(f"need={cost},have={points}")

        new_stat = current_stat + 1
        self.update_cat(cat_id, owner_id, **{field: new_stat})
        self.update_user_points(telegram_id, points - cost)

        return {
            "cat_name": updated.get("name", "گربه"),
            "stat": stat,
            "old_value": current_stat,
            "new_value": new_stat,
            "cost": cost,
            "new_points": points - cost,
        }

    def rename_cat(self, owner_id: int, cat_id: int, new_name: str) -> Dict[str, Any]:
        new_name = (new_name or "").strip()
        if not new_name or len(new_name) > 32:
            raise ValidationError("name_invalid")

        cat = self.get_cat(cat_id, owner_id)
        if not cat:
            raise NotFound("cat_not_found")

        updated = apply_cat_tick(cat)
        if not updated:
            self.kill_cat(cat_id, owner_id)
            raise CatDead("cat_dead")

        old_name = str(updated.get("name", "گربه"))
        self.update_cat(cat_id, owner_id, name=new_name)
        return {"old_name": old_name, "new_name": new_name}

    def buy_gear(self, telegram_id: int, owner_id: int, cat_id: int, gear_code: str) -> Dict[str, Any]:
        gear_code = gear_code.strip().lower()
        item = GEAR_ITEMS.get(gear_code)
        if not item:
            raise ValidationError("gear_invalid")

        user = self.get_user_by_tg(telegram_id)
        if not user:
            raise ServiceError("user load failed")
        points = int(user.get("mew_points", 0))

        cat = self.get_cat(cat_id, owner_id)
        if not cat:
            raise NotFound("cat_not_found")

        updated = apply_cat_tick(cat)
        if not updated:
            self.kill_cat(cat_id, owner_id)
            raise CatDead("cat_dead")

        if int(updated.get("level", 1)) < int(item.get("min_level", 1)):
            raise ValidationError("level_too_low")

        price = int(item.get("price", 0))
        if points < price:
            raise NotEnoughPoints(f"need={price},have={points}")

        gear_codes = parse_gear_codes(updated.get("gear", ""))
        if gear_code in gear_codes:
            raise ValidationError("gear_already_equipped")

        gear_codes.append(gear_code)
        new_gear_str = ",".join(gear_codes)

        self.update_cat(cat_id, owner_id, gear=new_gear_str)
        self.update_user_points(telegram_id, points - price)

        refreshed = dict(updated)
        refreshed["gear"] = new_gear_str
        mph = compute_cat_mph(refreshed)

        return {
            "cat_name": updated.get("name", "گربه"),
            "gear_code": gear_code,
            "gear_name": str(item.get("name", gear_code)),
            "price": price,
            "new_points": points - price,
            "new_mph": mph,
        }


# Singleton (برای اینکه handlerها راحت import کنند)
cats_service = CatsService()
