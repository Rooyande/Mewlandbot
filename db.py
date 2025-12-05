import os
import time
import requests
from typing import Dict, Any
from requests.exceptions import HTTPError
import logging

# Set up logger
logger = logging.getLogger(__name__)

# Get the Supabase environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("SUPABASE_URL or SUPABASE_KEY is not set.")

BASE_REST = SUPABASE_URL.rstrip("/") + "/rest/v1"
BASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Accept": "application/json",
}

# ---------- Helper functions ----------

def _get(table: str, params: Dict[str, Any]):
    """
    A helper function to send GET requests to Supabase API.
    Args:
        table: Table name.
        params: Parameters to filter the query.
    """
    # Ensure the 'select' key is added for querying
    if "select" not in params:
        params["select"] = "*"

    # Format telegram_id properly
    if 'telegram_id' in params:
        params["telegram_id"] = f"eq.{params['telegram_id']}"

    try:
        response = requests.get(
            f"{BASE_REST}/{table}",
            headers=BASE_HEADERS,
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except HTTPError as err:
        logger.error(f"Error during GET request to {table}: {err}")
        return []

def _insert(table: str, data: Dict[str, Any]):
    """
    Insert data into the Supabase table.
    Args:
        table: Table name.
        data: Data to insert.
    """
    try:
        response = requests.post(
            f"{BASE_REST}/{table}",
            headers=BASE_HEADERS,
            json=data,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()[0]  # Return the first row from response
    except HTTPError as err:
        logger.error(f"Error during POST request to {table}: {err}")
        return None

def _update(table: str, filters: Dict[str, Any], data: Dict[str, Any]):
    """
    Update data in the Supabase table.
    Args:
        table: Table name.
        filters: Filter for which rows to update.
        data: Data to update.
    """
    if not data:
        return None
    try:
        params = {"select": "*", **filters}
        response = requests.patch(
            f"{BASE_REST}/{table}",
            headers=BASE_HEADERS,
            params=params,
            json=data,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()[0]  # Return the first row after update
    except HTTPError as err:
        logger.error(f"Error during PATCH request to {table}: {err}")
        return None

def init_db():
    """
    Initialize the database (not necessary if everything is created above)
    """
    # No specific code needed here, as the tables are created directly in the SQL Editor
    pass

# ---------- Users Functions ----------

def get_user(telegram_id: int):
    """
    Get a user by their telegram_id
    Args:
        telegram_id: Telegram ID of the user.
    """
    rows = _get("users", {"telegram_id": telegram_id})
    return rows[0] if rows else None

def get_or_create_user(telegram_id: int, username: str | None):
    """
    Get or create a user based on telegram_id and username.
    Args:
        telegram_id: User's Telegram ID.
        username: User's Telegram username.
    """
    user = get_user(telegram_id)
    if user:
        return user["id"]

    # If the user doesn't exist, create them
    data = {
        "telegram_id": telegram_id,
        "username": username,
        "mew_points": 0,
        "last_mew_ts": None,
        "created_at": int(time.time()),
    }
    return _insert("users", data)["id"]

def update_user_mew(telegram_id: int, mew_points: int | None = None, last_mew_ts: int | None = None):
    """
    Update mew points and last_mew_ts for a user.
    Args:
        telegram_id: User's Telegram ID.
        mew_points: New mew points value (optional).
        last_mew_ts: Last mew timestamp (optional).
    """
    data = {}
    if mew_points is not None:
        data["mew_points"] = mew_points
    if last_mew_ts is not None:
        data["last_mew_ts"] = last_mew_ts
    _update("users", {"telegram_id": f"eq.{telegram_id}"}, data)

# ---------- Cats Functions ----------

def get_user_cats(owner_id: int):
    """
    Get all cats for a user by owner_id.
    Args:
        owner_id: User's database ID.
    """
    return _get("cats", {"owner_id": f"eq.{owner_id}"})

def get_cat(cat_id: int, owner_id: int | None = None):
    """
    Get a cat by its ID and optionally filter by owner.
    Args:
        cat_id: Cat's ID.
        owner_id: Owner's database ID (optional).
    """
    params = {"id": f"eq.{cat_id}"}
    if owner_id is not None:
        params["owner_id"] = f"eq.{owner_id}"
    rows = _get("cats", params)
    return rows[0] if rows else None

def add_cat(owner_id: int, name: str, rarity: str, element: str, trait: str, description: str) -> int:
    """
    Add a new cat for a user.
    Args:
        owner_id: Owner's database ID.
        name: Name of the cat.
        rarity: Rarity of the cat.
        element: Element of the cat.
        trait: Trait of the cat.
        description: Description of the cat.
    """
    data = {
        "owner_id": owner_id,
        "name": name,
        "rarity": rarity,
        "element": element,
        "trait": trait,
        "description": description,
        "level": 1,
        "xp": 0,
        "hunger": 60,
        "happiness": 60,
        "created_at": int(time.time()),
        "last_tick_ts": int(time.time()),
    }
    return _insert("cats", data)["id"]

def update_cat_stats(cat_id: int, owner_id: int, hunger: int, happiness: int, xp: int, level: int, last_tick_ts: int):
    """
    Update stats for a cat.
    Args:
        cat_id: ID of the cat.
        owner_id: Owner's database ID.
        hunger: Hunger stat.
        happiness: Happiness stat.
        xp: XP stat.
        level: Level of the cat.
        last_tick_ts: Last tick timestamp.
    """
    data = {
        "hunger": hunger,
        "happiness": happiness,
        "xp": xp,
        "level": level,
        "last_tick_ts": last_tick_ts,
    }
    _update("cats", {"id": f"eq.{cat_id}", "owner_id": f"eq.{owner_id}"}, data)

def rename_cat(owner_id: int, cat_id: int, new_name: str):
    """
    Rename a cat.
    Args:
        owner_id: Owner's database ID.
        cat_id: ID of the cat.
        new_name: New name for the cat.
    """
    return _update("cats", {"id": f"eq.{cat_id}", "owner_id": f"eq.{owner_id}"}, {"name": new_name})

def set_cat_owner(cat_id: int, new_owner_id: int):
    """
    Set a new owner for a cat.
    Args:
        cat_id: ID of the cat.
        new_owner_id: ID of the new owner.
    """
    data = {"owner_id": new_owner_id}
    return _update("cats", {"id": f"eq.{cat_id}"}, data)

def get_leaderboard(limit: int = 10):
    """
    Get the leaderboard based on mew_points from the users table.
    Args:
        limit: Number of top users to fetch.
    """
    rows = _get("users", {"select": "telegram_id, username, mew_points", "order": "mew_points.desc", "limit": limit})
    return rows



def register_user_group(user_id: int, chat_id: int):
    """
    Register a user's chat group.
    Args:
        user_id: User's ID.
        chat_id: Chat's ID.
    """
    rows = _get("user_groups", {"user_id": f"eq.{user_id}", "chat_id": f"eq.{chat_id}"})
    if not rows:
        data = {
            "user_id": user_id,
            "chat_id": chat_id
        }
        _insert("user_groups", data)
