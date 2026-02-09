import json
import math
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, Tuple

from db import open_db


def _now() -> int:
    return int(time.time())


async def _cfg_int(db, key: str, default: int) -> int:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return int(float(row["value"]))
    except Exception:
        return default


async def _cfg_float(db, key: str, default: float) -> float:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return float(row["value"])
    except Exception:
        return default


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
class ShelterUpgradeResult:
    ok: bool
    reason: str = ""
    old_level: int | None = None
    new_level: int | None = None
    cost: UpgradeCost | None = None
    effects: ShelterEffects | None = None


async def _get_effects_for_level(db, level: int) -> ShelterEffects:
    max_cats_base = await _cfg_int(db, "shelter_max_cats_base", 5)
    max_cats_per_level = await _cfg_int(db, "shelter_max_cats_per_level", 1)

    item_slots_base = await _cfg_int(db, "shelter_item_slots_base", 1)
    item_slots_every = await _cfg_int(db, "shelter_item_slots_every", 5)

    cap_base = await _cfg_int(db, "shelter_passive_cap_base_hours", 24)
    cap_add = await _cfg_int(db, "shelter_passive_cap_add_hours", 2)
    cap_max = await _cfg_int(db, "shelter_passive_cap_max_hours", 72)

    lvl = max(1, int(level))

    max_cats = max(1, int(max_cats_base + (lvl - 1) * max_cats_per_level))

    every = max(1, int(item_slots_every))
    item_slots = max(1, int(item_slots_base + (lvl - 1) // every))

    passive_cap = int(cap_base + (lvl - 1) * cap_add)
    passive_cap = max(1, passive_cap)
    passive_cap = min(passive_cap, max(1, int(cap_max)))

    return ShelterEffects(max_cats=max_cats, item_slots=item_slots, passive_cap_hours=passive_cap)


async def _calc_upgrade_cost(db, current_level: int) -> UpgradeCost:
    mp_base = await _cfg_int(db, "shelter_upgrade_mp_base", 500)
    mp_mult = await _cfg_float(db, "shelter_upgrade_mp_mult", 1.6)

    es_base = await _cfg_int(db, "shelter_upgrade_essence_base", 5)
    es_mult = await _cfg_float(db, "shelter_upgrade_essence_mult", 1.5)

    next_level = int(current_level) + 1
    step = max(1, next_level - 1)

    mp_cost = int(math.ceil(float(mp_base) * (float(mp_mult) ** (step - 1))))
    mp_cost = max(0, mp_cost)

    es_cost = int(math.ceil(float(es_base) * (float(es_mult) ** (step - 1))))
    es_cost = max(0, es_cost)

    return UpgradeCost(mp=mp_cost, essence=es_cost)


async def get_shelter_state(user_id: int) -> Optional[ShelterState]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT shelter_level FROM users WHERE user_id=?", (int(user_id),))
        row = await cur.fetchone()
        if row is None:
            return None
        lvl = int(row["shelter_level"] or 1)
        eff = await _get_effects_for_level(db, lvl)
        return ShelterState(level=lvl, effects=eff)
    finally:
        await db.close()


async def get_next_upgrade_cost(user_id: int) -> Optional[UpgradeCost]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT shelter_level FROM users WHERE user_id=?", (int(user_id),))
        row = await cur.fetchone()
        if row is None:
            return None
        lvl = int(row["shelter_level"] or 1)
        return await _calc_upgrade_cost(db, lvl)
    finally:
        await db.close()


async def upgrade_shelter(user_id: int) -> ShelterUpgradeResult:
    ts = _now()
    db = await open_db()
    try:
        await db.execute("BEGIN IMMEDIATE")

        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, mp_balance, last_passive_ts, shelter_level, created_at) "
            "VALUES(?, 0, ?, 1, ?)",
            (int(user_id), ts, ts),
        )
        await db.execute("INSERT OR IGNORE INTO resources(user_id, essence) VALUES(?, 0)", (int(user_id),))

        cur = await db.execute("SELECT mp_balance, shelter_level FROM users WHERE user_id=?", (int(user_id),))
        u = await cur.fetchone()
        if u is None:
            await db.execute("ROLLBACK")
            return ShelterUpgradeResult(False, "user_not_found")

        mp = int(u["mp_balance"] or 0)
        cur_level = int(u["shelter_level"] or 1)

        max_level = await _cfg_int(db, "shelter_max_level", 20)
        if cur_level >= max(1, int(max_level)):
            await db.execute("ROLLBACK")
            return ShelterUpgradeResult(False, "max_level", old_level=cur_level, new_level=cur_level)

        cur2 = await db.execute("SELECT essence FROM resources WHERE user_id=?", (int(user_id),))
        r = await cur2.fetchone()
        essence = 0 if r is None else int(r["essence"] or 0)

        cost = await _calc_upgrade_cost(db, cur_level)
        if mp < cost.mp:
            await db.execute("ROLLBACK")
            return ShelterUpgradeResult(False, "no_mp", old_level=cur_level, cost=cost)
        if essence < cost.essence:
            await db.execute("ROLLBACK")
            return ShelterUpgradeResult(False, "no_essence", old_level=cur_level, cost=cost)

        new_level = cur_level + 1
        eff = await _get_effects_for_level(db, new_level)

        await db.execute(
            "UPDATE users SET mp_balance = mp_balance - ?, shelter_level = ?, passive_cap_hours = ? WHERE user_id=?",
            (int(cost.mp), int(new_level), int(eff.passive_cap_hours), int(user_id)),
        )
        await db.execute(
            "UPDATE resources SET essence = essence - ? WHERE user_id=?",
            (int(cost.essence), int(user_id)),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                int(user_id),
                "shelter_upgrade",
                -int(cost.mp),
                json.dumps(
                    {
                        "old_level": int(cur_level),
                        "new_level": int(new_level),
                        "mp_cost": int(cost.mp),
                        "essence_cost": int(cost.essence),
                        "effects": {
                            "max_cats": int(eff.max_cats),
                            "item_slots": int(eff.item_slots),
                            "passive_cap_hours": int(eff.passive_cap_hours),
                        },
                    },
                    ensure_ascii=False,
                ),
                ts,
            ),
        )

        await db.commit()
        return ShelterUpgradeResult(
            True,
            old_level=cur_level,
            new_level=new_level,
            cost=cost,
            effects=eff,
        )
    except Exception:
        try:
            await db.execute("ROLLBACK")
        except Exception:
            pass
        return ShelterUpgradeResult(False, "error")
    finally:
        await db.close()
