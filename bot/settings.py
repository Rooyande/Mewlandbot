import json
import time
from typing import Any, Dict

from db import open_db

DEFAULT_SETTINGS: Dict[str, Any] = {
    "notify": 1,          # 1/0
    "public_profile": 1,  # 1/0
    "lang": "fa",         # "fa" | "en"
}


def _now() -> int:
    return int(time.time())


def _key(user_id: int) -> str:
    return f"user_settings:{int(user_id)}"


def _normalize(d: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)

    try:
        out["notify"] = 1 if int(d.get("notify", out["notify"])) else 0
    except Exception:
        out["notify"] = DEFAULT_SETTINGS["notify"]

    try:
        out["public_profile"] = 1 if int(d.get("public_profile", out["public_profile"])) else 0
    except Exception:
        out["public_profile"] = DEFAULT_SETTINGS["public_profile"]

    lang = str(d.get("lang", out["lang"]) or "fa").lower().strip()
    out["lang"] = "en" if lang == "en" else "fa"

    return out


def _loads(value: str | None) -> Dict[str, Any]:
    if not value:
        return dict(DEFAULT_SETTINGS)
    try:
        obj = json.loads(value)
        if isinstance(obj, dict):
            return _normalize(obj)
    except Exception:
        pass
    return dict(DEFAULT_SETTINGS)


async def get_user_settings(user_id: int) -> Dict[str, Any]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (_key(user_id),))
        row = await cur.fetchone()
        if row is None:
            return dict(DEFAULT_SETTINGS)
        return _loads(str(row["value"] or ""))
    finally:
        await db.close()


async def set_user_settings(user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    ts = _now()
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (_key(user_id),))
        row = await cur.fetchone()
        current = _loads("" if row is None else str(row["value"] or ""))

        merged = dict(current)
        merged.update(updates or {})
        merged = _normalize(merged)

        await db.execute(
            "INSERT INTO config(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (_key(user_id), json.dumps(merged, ensure_ascii=False), ts),
        )
        await db.commit()
        return merged
    finally:
        await db.close()


async def toggle_notify(user_id: int) -> Dict[str, Any]:
    s = await get_user_settings(user_id)
    return await set_user_settings(user_id, {"notify": 0 if int(s.get("notify", 1)) else 1})


async def toggle_public_profile(user_id: int) -> Dict[str, Any]:
    s = await get_user_settings(user_id)
    return await set_user_settings(user_id, {"public_profile": 0 if int(s.get("public_profile", 1)) else 1})


async def cycle_lang(user_id: int) -> Dict[str, Any]:
    s = await get_user_settings(user_id)
    return await set_user_settings(user_id, {"lang": "en" if s.get("lang") == "fa" else "fa"})
