import json
import random
import time
from dataclasses import dataclass
from typing import List, Optional

from db import open_db

RARITIES = ["Common", "Uncommon", "Rare", "Epic", "Legendary", "Mythic", "Divine"]

DUP_THRESHOLDS = {
    "Common": 25,
    "Uncommon": 15,
    "Rare": 8,
    "Epic": 4,
    "Legendary": 2,
    "Mythic": 1,
    "Divine": 10**9,
}


@dataclass
class CatalogCat:
    cat_id: int
    name: str
    description: str
    rarity: str
    base_passive_rate: float
    media_type: str
    media_file_id: str


def _now() -> int:
    return int(time.time())


async def catalog_list(pool: str) -> List[CatalogCat]:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            """
            SELECT cat_id, name, description, rarity, base_passive_rate, media_type, media_file_id
            FROM cats_catalog
            WHERE active=1
              AND rarity != 'Divine'
              AND (
                available_from IS NULL OR available_from <= ?
              )
              AND (
                available_until IS NULL OR available_until >= ?
              )
              AND (
                ',' || pools_enabled || ',' LIKE '%,' || ? || ',%'
              )
            """,
            (now, now, pool),
        )
        rows = await cur.fetchall()
        return [
            CatalogCat(
                cat_id=int(r["cat_id"]),
                name=str(r["name"]),
                description=str(r["description"]),
                rarity=str(r["rarity"]),
                base_passive_rate=float(r["base_passive_rate"]),
                media_type=str(r["media_type"]),
                media_file_id=str(r["media_file_id"]),
            )
            for r in rows
        ]
    finally:
        await db.close()


def _weighted_choice(items, weights) -> int:
    total = sum(weights)
    r = random.random() * total
    upto = 0.0
    for i, w in enumerate(weights):
        upto += w
        if upto >= r:
            return i
    return len(items) - 1


async def _get_cfg_json(key: str) -> Optional[dict]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
        row = await cur.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row["value"])
        except Exception:
            return None
    finally:
        await db.close()


async def _get_pity(user_id: int, key: str) -> int:
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT value FROM config WHERE key=?",
            (f"pity_{key}_{user_id}",),
        )
        row = await cur.fetchone()
        if row is None:
            return 0
        try:
            return int(row["value"])
        except Exception:
            return 0
    finally:
        await db.close()


async def _set_pity(user_id: int, key: str, v: int) -> None:
    now = _now()
    db = await open_db()
    try:
        await db.execute(
            "INSERT INTO config(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (f"pity_{key}_{user_id}", str(int(v)), now),
        )
        await db.commit()
    finally:
        await db.close()


async def _add_or_dup(user_id: int, cat: CatalogCat) -> dict:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT id, level, dup_counter, status FROM user_cats WHERE user_id=? AND cat_id=? ORDER BY id LIMIT 1",
            (user_id, cat.cat_id),
        )
        owned = await cur.fetchone()

        if owned is None:
            await db.execute(
                """
                INSERT INTO user_cats(user_id, cat_id, level, dup_counter, status, last_feed_at, last_play_at, obtained_at)
                VALUES(?, ?, 1, 0, 'active', ?, ?, ?)
                """,
                (user_id, cat.cat_id, now, now, now),
            )
            await db.commit()
            return {"type": "new", "level_up": False, "level": 1}

        level = int(owned["level"] or 1)
        dup = int(owned["dup_counter"] or 0)
        status = str(owned["status"] or "active")

        if status != "active":
            status = "active"

        if level >= await _max_level():
            # max level => essence later (not implemented here)
            await db.execute(
                "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
                (user_id, "dup_at_max_level", 0, json.dumps({"cat_id": cat.cat_id}), now),
            )
            await db.commit()
            return {"type": "dup_max", "level_up": False, "level": level}

        dup += 1
        th = DUP_THRESHOLDS.get(cat.rarity, 25)
        level_up = False
        if dup >= th:
            level = level + 1
            dup = 0
            level_up = True

        await db.execute(
            "UPDATE user_cats SET level=?, dup_counter=?, status=? WHERE id=?",
            (level, dup, status, int(owned["id"])),
        )
        await db.commit()
        return {"type": "dup", "level_up": level_up, "level": level, "dup": dup, "threshold": th}
    finally:
        await db.close()


async def _max_level() -> int:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key='max_level'")
        row = await cur.fetchone()
        if row is None:
            return 20
        try:
            return int(row["value"])
        except Exception:
            return 20
    finally:
        await db.close()


@dataclass
class BoxResult:
    ok: bool
    reason: str = ""
    cat: Optional[CatalogCat] = None
    outcome: Optional[dict] = None


async def open_standard_box(user_id: int, price: int = 10) -> BoxResult:
    probs = await _get_cfg_json("standard_probs") or {
        "Common": 0.60,
        "Uncommon": 0.22,
        "Rare": 0.13,
        "Epic": 0.05,
    }
    pity_n = int((await _get_cfg_json("standard_pity") or {}).get("n", 30))
    pity_counter = await _get_pity(user_id, "standard")

    cats = await catalog_list("Standard")
    if not cats:
        return BoxResult(False, "empty_pool")

    # build rarity buckets
    buckets = {}
    for c in cats:
        if c.rarity in probs:
            buckets.setdefault(c.rarity, []).append(c)

    # ensure at least one candidate exists for selected rarity
    rarities = list(probs.keys())
    weights = [float(probs[r]) for r in rarities]

    forced_epic = False
    pity_counter += 1
    if pity_counter >= pity_n:
        forced_epic = True

    chosen_rarity = "Epic" if forced_epic else rarities[_weighted_choice(rarities, weights)]
    if chosen_rarity not in buckets:
        # fallback to any available rarity
        chosen_rarity = next(iter(buckets.keys()))

    cat = random.choice(buckets[chosen_rarity])

    # charge MP
    db = await open_db()
    try:
        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (user_id,))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)
        if mp < price:
            return BoxResult(False, "no_mp")
        await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (price, user_id))
        await db.commit()
    finally:
        await db.close()

    outcome = await _add_or_dup(user_id, cat)

    if chosen_rarity == "Epic":
        pity_counter = 0
    await _set_pity(user_id, "standard", pity_counter)

    return BoxResult(True, cat=cat, outcome=outcome)


async def open_premium_box(user_id: int, price: int = 250) -> BoxResult:
    probs = await _get_cfg_json("premium_probs") or {
        "Common": 0.45,
        "Uncommon": 0.23,
        "Rare": 0.15,
        "Epic": 0.10,
        "Legendary": 0.065,
        "Mythic": 0.005,
    }
    pity_n = int((await _get_cfg_json("premium_pity") or {}).get("n", 10))
    pity_counter = await _get_pity(user_id, "premium")

    cats = await catalog_list("Premium")
    if not cats:
        return BoxResult(False, "empty_pool")

    buckets = {}
    for c in cats:
        if c.rarity in probs:
            buckets.setdefault(c.rarity, []).append(c)

    rarities = list(probs.keys())
    weights = [float(probs[r]) for r in rarities]

    pity_counter += 1
    if pity_counter >= pity_n:
        # guarantee at least Epic
        eligible = [r for r in rarities if r in ("Epic", "Legendary", "Mythic")]
        elig_w = [probs[r] for r in eligible]
        chosen_rarity = eligible[_weighted_choice(eligible, elig_w)]
    else:
        chosen_rarity = rarities[_weighted_choice(rarities, weights)]

    if chosen_rarity not in buckets:
        chosen_rarity = next(iter(buckets.keys()))

    cat = random.choice(buckets[chosen_rarity])

    db = await open_db()
    try:
        cur = await db.execute("SELECT mp_balance FROM users WHERE user_id=?", (user_id,))
        u = await cur.fetchone()
        mp = 0 if u is None else int(u["mp_balance"] or 0)
        if mp < price:
            return BoxResult(False, "no_mp")
        await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (price, user_id))
        await db.commit()
    finally:
        await db.close()

    outcome = await _add_or_dup(user_id, cat)

    # pity resets if Epic or above
    if chosen_rarity in ("Epic", "Legendary", "Mythic"):
        pity_counter = 0
    await _set_pity(user_id, "premium", pity_counter)

    return BoxResult(True, cat=cat, outcome=outcome)
