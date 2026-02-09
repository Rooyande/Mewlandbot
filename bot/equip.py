import json
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

from db import open_db

DEFAULT_ITEM_SLOTS = 1


def _now() -> int:
    return int(time.time())


async def _cfg_int(db, key: str, default: int) -> int:
    cur = await db.execute("SELECT value FROM config WHERE key=?", (key,))
    row = await cur.fetchone()
    if row is None:
        return default
    try:
        return int(row["value"])
    except Exception:
        return default


async def _get_user_item_slots(db, user_id: int) -> int:
    # فعلاً از config می‌گیرد؛ بعداً با Shelter هماهنگ می‌شود
    slots = await _cfg_int(db, "item_slots_default", DEFAULT_ITEM_SLOTS)
    if slots <= 0:
        slots = 1
    return slots


def _parse_equipped(s: Optional[str]) -> Dict[str, Any]:
    if not s:
        return {"slots": []}
    try:
        obj = json.loads(s)
        if isinstance(obj, dict) and isinstance(obj.get("slots"), list):
            return obj
        if isinstance(obj, list):
            return {"slots": obj}
        return {"slots": []}
    except Exception:
        return {"slots": []}


def _dump_equipped(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False)


@dataclass
class EquipResult:
    ok: bool
    reason: str = ""
    equipped: Dict[str, Any] | None = None


async def get_user_cat_equipped(user_id: int, user_cat_id: int) -> Optional[Dict[str, Any]]:
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT equipped_items_json FROM user_cats WHERE user_id=? AND id=?",
            (user_id, user_cat_id),
        )
        r = await cur.fetchone()
        if r is None:
            return None
        return _parse_equipped(r["equipped_items_json"])
    finally:
        await db.close()


async def equip_item(user_id: int, user_cat_id: int, item_id: int) -> EquipResult:
    now = _now()
    db = await open_db()
    try:
        # validate cat ownership
        cur = await db.execute(
            "SELECT equipped_items_json, status FROM user_cats WHERE user_id=? AND id=?",
            (user_id, user_cat_id),
        )
        uc = await cur.fetchone()
        if uc is None:
            return EquipResult(False, "cat_not_found")
        if str(uc["status"] or "active") != "active":
            return EquipResult(False, "cat_not_active")

        # validate item exists + active
        cur = await db.execute(
            "SELECT item_id, name, type FROM items_catalog WHERE item_id=? AND COALESCE(active,1)=1",
            (item_id,),
        )
        it = await cur.fetchone()
        if it is None:
            return EquipResult(False, "item_not_found")

        # validate user has item qty
        cur = await db.execute(
            "SELECT qty FROM user_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
        ui = await cur.fetchone()
        qty = 0 if ui is None else int(ui["qty"] or 0)
        if qty <= 0:
            return EquipResult(False, "no_item")

        slots_cap = await _get_user_item_slots(db, user_id)
        equipped = _parse_equipped(uc["equipped_items_json"])
        slots: List[dict] = list(equipped.get("slots", []))

        # prevent duplicates (same item twice)
        for s in slots:
            if int(s.get("item_id", 0)) == int(item_id):
                return EquipResult(False, "already_equipped")

        if len(slots) >= slots_cap:
            return EquipResult(False, "no_slot")

        slots.append({"item_id": int(item_id), "equipped_at": now})
        equipped["slots"] = slots

        await db.execute(
            "UPDATE user_cats SET equipped_items_json=? WHERE user_id=? AND id=?",
            (_dump_equipped(equipped), user_id, user_cat_id),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                user_id,
                "equip_item",
                0,
                json.dumps({"user_cat_id": int(user_cat_id), "item_id": int(item_id)}, ensure_ascii=False),
                now,
            ),
        )

        await db.commit()
        return EquipResult(True, equipped=equipped)
    finally:
        await db.close()


async def unequip_item(user_id: int, user_cat_id: int, item_id: int) -> EquipResult:
    now = _now()
    db = await open_db()
    try:
        cur = await db.execute(
            "SELECT equipped_items_json FROM user_cats WHERE user_id=? AND id=?",
            (user_id, user_cat_id),
        )
        uc = await cur.fetchone()
        if uc is None:
            return EquipResult(False, "cat_not_found")

        equipped = _parse_equipped(uc["equipped_items_json"])
        slots: List[dict] = list(equipped.get("slots", []))

        before = len(slots)
        slots = [s for s in slots if int(s.get("item_id", 0)) != int(item_id)]
        if len(slots) == before:
            return EquipResult(False, "not_equipped")

        equipped["slots"] = slots

        await db.execute(
            "UPDATE user_cats SET equipped_items_json=? WHERE user_id=? AND id=?",
            (_dump_equipped(equipped), user_id, user_cat_id),
        )

        await db.execute(
            "INSERT INTO economy_logs(user_id, action, amount, meta_json, ts) VALUES(?,?,?,?,?)",
            (
                user_id,
                "unequip_item",
                0,
                json.dumps({"user_cat_id": int(user_cat_id), "item_id": int(item_id)}, ensure_ascii=False),
                now,
            ),
        )

        await db.commit()
        return EquipResult(True, equipped=equipped)
    finally:
        await db.close()

