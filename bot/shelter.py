import json
import math
import time
from dataclasses import dataclass
from typing import Optional

from db import open_db


def _now() -> int:
    return int(time.time())


async def _cfg_int(db, key: str, default: int) -> int:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return int(default)
    try:
        return int(float(row["value"]))
    except Exception:
        return int(default)


async def _cfg_float(db, key: str, default: float) -> float:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return float(default)
    try:
        return float(row["value"])
    except Exception:
        return float(default)


@dataclass
class ShelterEffects:
    max_cats: int
    item_slots: int
    passive_cap_hours: int


@dataclass
class ShelterState:
    level: int
    effects: ShelterEffects


@dataclass
class UpgradeCost:
    mp: int
    essence: int


@dataclass
class UpgradeResult:
    ok: bool
    reason: str = ""
    old_level: int = 0
    new_level: int = 0
    cost: UpgradeCost | None = None
    effects: ShelterEffects | None = None


async def _ensure_user_rows(db, user_id: int) -> None:
    now = _now()
    await db.execute(
        "INSERT OR IGNORE INTO users(user_id, mp_balance, last_passive_ts, shelter_level, created_at) "
        "VALUES(?, 0, ?, 1, ?)",
        (int(user_id), int(now), int(now)),
    )
    await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?, 0)", (int(user_id),))


async def _max_level(db) -> int:
    v = await _cfg_int(db, "shelter_max_level", 20)
    return max(1, int(v))


async def _compute_effects(db, level: int) -> ShelterEffects:
    level = max(1, int(level))

    base_max_cats = await _cfg_int(db, "shelter_base_max_cats", 10)
    max_cats_per_level = await _cfg_int(db, "shelter_max_cats_per_level", 2)

    base_item_slots = await _cfg_int(db, "shelter_base_item_slots", 1)
    item_slots_every = await _cfg_int(db, "shelter_item_slots_every_levels", 5)

    base_cap = await _cfg_int(db, "shelter_base_passive_cap_hours", 24)
    cap_per_level = await _cfg_int(db, "shelter_passive_cap_hours_per_level", 2)
    cap_max = await _cfg_int(db, "shelter_passive_cap_hours_max", 72)

    max_cats = int(base_max_cats) + (level - 1) * int(max_cats_per_level)
    if max_cats < 1:
        max_cats = 1

    if item_slots_every <= 0:
        item_slots = int(base_item_slots)
    else:
        item_slots = int(base_item_slots) + (level - 1) // int(item_slots_every)
    if item_slots < 1:
        item_slots = 1

    passive_cap_hours = int(base_cap) + (level - 1) * int(cap_per_level)
    if cap_max > 0:
        passive_cap_hours = min(int(cap_max), passive_cap_hours)
    if passive_cap_hours < 1:
        passive_cap_hours = 1

    return ShelterEffects(max_cats=max_cats, item_slots=item_slots, passive_cap_hours=passive_cap_hours)


async def get_shelter_state(user_id: int) -> Optional[ShelterState]:
    db = await open_db()
    try:
        await _ensure_user_rows(db, user_id)

        cur = await db.execute("SELECT shelter_level FROM users WHERE user_id=?", (int(user_id),))
        r = await cur.fetchone()
        lvl = 1 if r is None else int(r["shelter_level"] or 1)

        effects = await _compute_effects(db, lvl)
        return ShelterState(level=lvl, effects=effects)
    finally:
        await db.close()


async def _upgrade_cost(db, current_level: int) -> UpgradeCost:
    """
    هزینه آپگرید از level=L به L+1
    """
    mp_base = await _cfg_int(db, "shelter_upgrade_mp_base", 500)
    mp_mult = await _cfg_float(db, "shelter_upgrade_mp_mult", 1.35)

    es_base = await _cfg_int(db, "shelter_upgrade_essence_base", 10)
    es_mult = await _cfg_float(db, "shelter_upgrade_essence_mult", 1.25)

    exp = max(0, int(current_level) - 1)

    mp = int(round(float(mp_base) * (float(mp_mult) ** exp)))
    ess = int(round(float(es_base) * (float(es_mult) ** exp)))

    if mp < 0:
        mp = 0
    if ess < 0:
        ess = 0

    return UpgradeCost(mp=mp, essence=ess)


async def get_next_upgrade_cost(user_id: int) -> Optional[UpgradeCost]:
    db = await open_db()
    try:
        await _ensure_user_rows(db, user_id)

        cur = await db.execute("SELECT shelter_level FROM users WHERE user_id=?", (int(user_id),))
        r = await cur.fetchone()
        lvl = 1 if r is None else int(r["shelter_level"] or 1)

        max_lvl = await _max_level(db)
        if lvl >= max_lvl:
            return UpgradeCost(mp=0, essence=0)

        return await _upgrade_cost(db, lvl)
    finally:
        await db.close()


async def upgrade_shelter(user_id: int) -> UpgradeResult:
    ts = _now()
    db = await open_db()
    try:
        await _ensure_user_rows(db, user_id)

        cur = await db.execute("SELECT shelter_level, mp_balance FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        if u is None:
            return UpgradeResult(False, "not_found")

        lvl = int(u["shelter_level"] or 1)
        mp = int(u["mp_balance"] or 0)

        max_lvl = await _max_level(db)
        if lvl >= max_lvl:
            return UpgradeResult(False, "max_level", old_level=lvl, new_level=lvl)

        cost = await _upgrade_cost(db, lvl)

        cur = await db.execute("SELECT essence FROM resources WHERE user_id=?", (int(user_id),))
        rr = await cur.fetchone()
        ess = 0 if rr is None else int(rr["essence"] or 0)

        if mp < cost.mp:
            return UpgradeResult(False, "no_mp", old_level=lvl, new_level=lvl, cost=cost)

        if ess < cost.essence:
            return UpgradeResult(False, "no_essence", old_level=lvl, new_level=lvl, cost=cost)

        new_level = lvl + 1
        effects = await _compute_effects(db, new_level)

        await db.execute("UPDATE users SET mp_balance = mp_balance - ? WHERE user_id=?", (int(cost.mp), int(user_id)))
        await db.execute("UPDATE resources SET essence = essence - ? WHERE user_id=?", (int(cost.essence), int(user_id)))
        await db.execute(
            "UPDATE users SET shelter_level=?, passive_cap_hours=? WHERE user_id=?",
            (int(new_level), int(effects.passive_cap_hours), int(user_id)),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                int(user_id),
                "shelter_upgrade",
                -int(cost.mp),
                json.dumps(
                    {
                        "old_level": int(lvl),
                        "new_level": int(new_level),
                        "essence_spent": int(cost.essence),
                        "effects": {
                            "max_cats": int(effects.max_cats),
                            "item_slots": int(effects.item_slots),
                            "passive_cap_hours": int(effects.passive_cap_hours),
                        },
                    },
                    ensure_ascii=False,
                ),
                int(ts),
            ),
        )

        await db.commit()
        return UpgradeResult(
            True,
            old_level=lvl,
            new_level=new_level,
            cost=cost,
            effects=effects,
        )
    finally:
        await db.close()
