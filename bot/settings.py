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


def _coerce(settings: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(DEFAULT_SETTINGS)
    try:
        out["notify"] = 1 if int(settings.get("notify", out["notify"])) else 0
    except Exception:
        out["notify"] = DEFAULT_SETTINGS["notify"]

    try:
        out["public_profile"] = 1 if int(settings.get("public_profile", out["public_profile"])) else 0
    except Exception:
        out["public_profile"] = DEFAULT_SETTINGS["public_profile"]

    lang = str(settings.get("lang", out["lang"]) or "fa").lower()
    out["lang"] = "en" if lang == "en" else "fa"
    return out


async def get_user_settings(user_id: int) -> Dict[str, Any]:
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (_key(user_id),))
        row = await cur.fetchone()
        if row is None:
            return dict(DEFAULT_SETTINGS)
        try:
            obj = json.loads(str(row["value"] or "{}"))
            if isinstance(obj, dict):
                return _coerce(obj)
        except Exception:
            pass
        return dict(DEFAULT_SETTINGS)
    finally:
        await db.close()


async def set_user_settings(user_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    ts = _now()
    db = await open_db()
    try:
        cur = await db.execute("SELECT value FROM config WHERE key=?", (_key(user_id),))
        row = await cur.fetchone()

        current = dict(DEFAULT_SETTINGS)
        if row is not None:
            try:
                obj = json.loads(str(row["value"] or "{}"))
                if isinstance(obj, dict):
                    current = _coerce(obj)
            except Exception:
                current = dict(DEFAULT_SETTINGS)

        merged = dict(current)
        merged.update(updates or {})
        merged = _coerce(merged)

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
    cur = await get_user_settings(user_id)
    return await set_user_settings(user_id, {"notify": 0 if int(cur["notify"]) else 1})


async def toggle_public_profile(user_id: int) -> Dict[str, Any]:
    cur = await get_user_settings(user_id)
    return await set_user_settings(user_id, {"public_profile": 0 if int(cur["public_profile"]) else 1})


async def cycle_lang(user_id: int) -> Dict[str, Any]:
    cur = await get_user_settings(user_id)
    return await set_user_settings(user_id, {"lang": "en" if cur.get("lang") == "fa" else "fa"})
