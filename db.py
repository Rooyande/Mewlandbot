# db.py
# Supabase REST-based storage for Mewland bot

import os
import time
import logging
import requests
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is not set")

BASE_REST = SUPABASE_URL.rstrip("/") + "/rest/v1"

BASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


# ---------- low-level helpers ----------

def _get(table: str, params: Dict[str, Any]):
    p = dict(params or {})
    if "select" not in p:
        p["select"] = "*"
    r = requests.get(
        f"{BASE_REST}/{table}",
        headers=BASE_HEADERS,
        params=p,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def _insert(table: str, data: Dict[str, Any]):
    headers = dict(BASE_HEADERS)
    headers["Prefer"] = "return=representation"
    r = requests.post(
        f"{BASE_REST}/{table}",
        headers=headers,
        json=data,
        timeout=10,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def _update(table: str, filters: Dict[str, Any], data: Dict[str, Any]):
    if not data:
        return None
    headers = dict(BASE_HEADERS)
    headers["Prefer"] = "return=representation"
    params = dict(filters or {})
    params["select"] = "*"
    r = requests.patch(
        f"{BASE_REST}/{table}",
        headers=headers,
        params=params,
        json=data,
        timeout=10,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


def init_db():
    """Light sanity check that Supabase is responding."""
    try:
        _get("users", {"select": "id", "limit": 1})
        logger.info("DB init OK (Supabase REST).")
    except Exception as e:
        logger.exception("DB init failed: %s", e)
        raise


# ---------- USERS ----------

def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    rows = _get("users", {"telegram_id": f"eq.{telegram_id}"})
    return rows[0] if rows else None


def get_or_create_user(telegram_id: int, username: Optional[str]) -> int:
    u = get_user(telegram_id)
    if u:
        return u["id"]

    now = int(time.time())
    data = {
        "telegram_id": telegram_id,
        "username": username,
        "mew_points": 0,
        "last_mew_ts": None,
        "last_passive_ts": now,
        "created_at": now,
    }
    row = _insert("users", data)
    return row["id"]


def update_user_mew(
    telegram_id: int,
    mew_points: Optional[int] = None,
    last_mew_ts: Optional[int] = None,
    last_passive_ts: Optional[int] = None,
):
    data: Dict[str, Any] = {}
    if mew_points is not None:
        data["mew_points"] = mew_points
    if last_mew_ts is not None:
        data["last_mew_ts"] = last_mew_ts
    if last_passive_ts is not None:
        data["last_passive_ts"] = last_passive_ts

    if not data:
        return

    _update("users", {"telegram_id": f"eq.{telegram_id}"}, data)


def get_all_users():
    return _get("users", {})


# ---------- USER_GROUPS (optional but handy) ----------

def register_user_group(user_id: int, chat_id: int):
    rows = _get(
        "user_groups",
        {
            "user_id": f"eq.{user_id}",
            "chat_id": f"eq.{chat_id}",
        },
    )
    if rows:
        return
    data = {
        "user_id": user_id,
        "chat_id": chat_id,
    }
    _insert("user_groups", data)


def get_group_users(chat_id: int):
    ugs = _get("user_groups", {"chat_id": f"eq.{chat_id}"})
    users = []
    for ug in ugs:
        uid = ug["user_id"]
        rows = _get("users", {"id": f"eq.{uid}"})
        if rows:
            users.append(rows[0])
    return users


# ---------- CATS ----------

def get_user_cats(owner_id: int):
    return _get("cats", {"owner_id": f"eq.{owner_id}"})


def add_cat(
    owner_id: int,
    name: str,
    rarity: str,
    personality: str,
    element: str,
    trait: str,
    description: str,
) -> int:
    now = int(time.time())
    data = {
        "owner_id": owner_id,
        "name": name,
        "rarity": rarity,
        "personality": personality,
        "element": element,
        "trait": trait,
        "description": description,
        "level": 1,
        "xp": 0,
        "hunger": 80,
        "happiness": 80,
        "stat_power": 1,
        "stat_agility": 1,
        "stat_luck": 1,
        "gear": "",
        "created_at": now,
        "last_tick_ts": now,
    }
    row = _insert("cats", data)
    return row["id"]


def get_cat(cat_id: int, owner_id: Optional[int] = None):
    params: Dict[str, Any] = {"id": f"eq.{cat_id}"}
    if owner_id is not None:
        params["owner_id"] = f"eq.{owner_id}"
    rows = _get("cats", params)
    return rows[0] if rows else None


def update_cat_stats(
    cat_id: int,
    owner_id: int,
    hunger: Optional[int] = None,
    happiness: Optional[int] = None,
    xp: Optional[int] = None,
    level: Optional[int] = None,
    last_tick_ts: Optional[int] = None,
    description: Optional[str] = None,
    gear: Optional[str] = None,
    stat_power: Optional[int] = None,
    stat_agility: Optional[int] = None,
    stat_luck: Optional[int] = None,
):
    data: Dict[str, Any] = {}
    if hunger is not None:
        data["hunger"] = hunger
    if happiness is not None:
        data["happiness"] = happiness
    if xp is not None:
        data["xp"] = xp
    if level is not None:
        data["level"] = level
    if last_tick_ts is not None:
        data["last_tick_ts"] = last_tick_ts
    if description is not None:
        data["description"] = description
    if gear is not None:
        data["gear"] = gear
    if stat_power is not None:
        data["stat_power"] = stat_power
    if stat_agility is not None:
        data["stat_agility"] = stat_agility
    if stat_luck is not None:
        data["stat_luck"] = stat_luck

    if not data:
        return

    _update(
        "cats",
        {
            "id": f"eq.{cat_id}",
            "owner_id": f"eq.{owner_id}",
        },
        data,
    )


def rename_cat(owner_id: int, cat_id: int, new_name: str):
    return _update(
        "cats",
        {
            "id": f"eq.{cat_id}",
            "owner_id": f"eq.{owner_id}",
        },
        {"name": new_name},
    )


def set_cat_owner(cat_id: int, new_owner_id: int):
    return _update(
        "cats",
        {"id": f"eq.{cat_id}"},
        {"owner_id": new_owner_id},
    )


# ---------- LEADERBOARD ----------

def get_leaderboard(limit: int = 10):
    params = {
        "select": "telegram_id,username,mew_points",
        "order": "mew_points.desc",
        "limit": limit,
    }
    rows = _get("users", params)
    return rows or []
