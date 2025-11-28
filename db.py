# db.py
# استفاده از Supabase REST API به‌جای اتصال مستقیم Postgres

import os
import requests

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL یا SUPABASE_KEY تنظیم نشده است.")

BASE_REST = SUPABASE_URL.rstrip("/") + "/rest/v1"

BASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}


def _get(table, params):
    p = dict(params)
    if "select" not in p:
        p["select"] = "*"
    r = requests.get(f"{BASE_REST}/{table}", headers=BASE_HEADERS, params=p, timeout=10)
    r.raise_for_status()
    return r.json()


def _insert(table, data):
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


def _update(table, filters, data):
    headers = dict(BASE_HEADERS)
    headers["Prefer"] = "return=representation"
    params = dict(filters)
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


# ---------- init_db (اینجا کاری خاص نمی‌کنیم) ----------
def init_db():
    # برای Postgres مستقیم نیاز بود، اینجا فقط می‌تونست چک سلامت بکند.
    return


# ---------- USERS ----------
def get_user(telegram_id: int):
    rows = _get("users", {"telegram_id": f"eq.{telegram_id}"})
    return rows[0] if rows else None


def get_or_create_user(telegram_id: int, username: str | None):
    u = get_user(telegram_id)
    if u:
        return u["id"]

    data = {
        "telegram_id": telegram_id,
        "username": username,
        "mew_points": 0,
        "last_mew_ts": None,
    }
    row = _insert("users", data)
    return row["id"]


def update_user_mew(telegram_id: int, mew_points: int, last_mew_ts: int | None):
    data = {
        "mew_points": mew_points,
        "last_mew_ts": last_mew_ts,
    }
    _update("users", {"telegram_id": f"eq.{telegram_id}"}, data)


def get_all_users():
    return _get("users", {})


# ---------- USER_GROUPS ----------
def register_user_group(user_id: int, chat_id: int):
    # اول چک می‌کنیم وجود داره یا نه
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
    # user_groups رو می‌گیریم بعد یوزرها رو جدا جدا
    ugs = _get("user_groups", {"chat_id": f"eq.{chat_id}"})
    users = []
    for ug in ugs:
        uid = ug["user_id"]
        rows = _get("users", {"id": f"eq.{uid}"})
        if rows:
            users.append(rows[0])
    return users


# ---------- CATS ----------
def get_user_cats(user_id: int):
    return _get("cats", {"owner_id": f"eq.{user_id}"})


def add_cat(owner_id: int, name: str, rarity: str, element: str, trait: str, description: str) -> int:
    import time

    now = int(time.time())
    data = {
        "owner_id": owner_id,
        "name": name,
        "rarity": rarity,
        "element": element,
        "trait": trait,
        "description": description,
        "level": 1,
        "xp": 0,
        "hunger": 50,
        "happiness": 50,
        "created_at": now,
        "last_tick_ts": now,
    }
    row = _insert("cats", data)
    return row["id"]


def get_cat(cat_id: int, owner_id: int):
    rows = _get(
        "cats",
        {
            "id": f"eq.{cat_id}",
            "owner_id": f"eq.{owner_id}",
        },
    )
    return rows[0] if rows else None


def update_cat_stats(cat_id: int, owner_id: int, hunger: int, happiness: int, xp: int, level: int, last_tick_ts: int):
    data = {
        "hunger": hunger,
        "happiness": happiness,
        "xp": xp,
        "level": level,
        "last_tick_ts": last_tick_ts,
    }
    _update(
        "cats",
        {
            "id": f"eq.{cat_id}",
            "owner_id": f"eq.{owner_id}",
        },
        data,
    )
