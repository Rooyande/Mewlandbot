import os
import time
import requests
from typing import Dict, Any, Optional, List
from requests.exceptions import HTTPError, RequestException
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

def _format_filter(key: str, value: Any) -> str:
    """Format filter values for Supabase query."""
    if key in ['telegram_id', 'id', 'owner_id', 'user_id', 'chat_id']:
        return f"eq.{value}"
    return str(value)

def _get(table: str, params: Dict[str, Any] = None) -> List[Dict]:
    """
    A helper function to send GET requests to Supabase API.
    """
    if params is None:
        params = {}
    
    # Ensure the 'select' key is added for querying
    if "select" not in params:
        params["select"] = "*"

    # Format parameters for Supabase
    formatted_params = {}
    for key, value in params.items():
        if isinstance(value, (int, str)):
            formatted_params[key] = _format_filter(key, value)
        else:
            formatted_params[key] = value

    try:
        response = requests.get(
            f"{BASE_REST}/{table}",
            headers=BASE_HEADERS,
            params=formatted_params,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()
    except HTTPError as err:
        logger.error(f"Error during GET request to {table}: {err}")
        return []
    except Exception as e:
        logger.error(f"Unexpected error in _get: {e}")
        return []

def _insert(table: str, data: Dict[str, Any]) -> Optional[Dict]:
    """
    Insert data into the Supabase table.
    """
    try:
        response = requests.post(
            f"{BASE_REST}/{table}",
            headers=BASE_HEADERS,
            json=data,
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        return result[0] if isinstance(result, list) and result else result
    except HTTPError as err:
        logger.error(f"Error during POST request to {table}: {err}")
        if response.status_code == 409:
            logger.warning(f"Duplicate entry for {data}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in _insert: {e}")
        return None

def _update(table: str, filters: Dict[str, Any], data: Dict[str, Any]) -> Optional[Dict]:
    """
    Perform an update on the given table and return the updated row(s).
    """
    headers = dict(BASE_HEADERS)
    headers["Prefer"] = "return=representation"
    
    # Format filters for Supabase
    formatted_filters = {}
    for key, value in filters.items():
        formatted_filters[key] = _format_filter(key, value)
    
    try:
        logger.debug(f"PATCH {table} with filters={formatted_filters}, data={data}")
        r = requests.patch(
            f"{BASE_REST}/{table}",
            headers=headers,
            params=formatted_filters,
            json=data,
            timeout=30,
        )
        r.raise_for_status()

        if not r.text.strip():
            return None

        result = r.json()
        return result[0] if isinstance(result, list) and result else result
    except RequestException as e:
        logger.error(f"Request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in _update: {e}")
        return None

def _delete(table: str, filters: Dict[str, Any]) -> bool:
    """Delete rows from table."""
    try:
        formatted_filters = {}
        for key, value in filters.items():
            formatted_filters[key] = _format_filter(key, value)
            
        response = requests.delete(
            f"{BASE_REST}/{table}",
            headers=BASE_HEADERS,
            params=formatted_filters,
            timeout=30,
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Error deleting from {table}: {e}")
        return False

def init_db():
    """Initialize database connection."""
    logger.info("Database initialized")

# ---------- Users Functions ----------

def get_user(telegram_id: int) -> Optional[Dict]:
    """Get a user by their telegram_id."""
    rows = _get("users", {"telegram_id": telegram_id})
    return rows[0] if rows else None

def get_or_create_user(telegram_id: int, username: str = None) -> Optional[int]:
    """
    Get or create a user based on telegram_id and username.
    Returns user database ID or None.
    """
    user = get_user(telegram_id)
    if user:
        return user.get("id")
    
    # If the user doesn't exist, create them
    data = {
        "telegram_id": telegram_id,
        "username": username,
        "mew_points": 100,  # Starting points for new users
        "last_mew_ts": None,
        "last_passive_ts": int(time.time()),
        "created_at": int(time.time()),
    }
    
    result = _insert("users", data)
    return result.get("id") if result else None

def update_user_mew(telegram_id: int, mew_points: int = None, 
                    last_mew_ts: int = None, last_passive_ts: int = None) -> bool:
    """Update user mew points and timestamps."""
    data = {}
    if mew_points is not None:
        data["mew_points"] = mew_points
    if last_mew_ts is not None:
        data["last_mew_ts"] = last_mew_ts
    if last_passive_ts is not None:
        data["last_passive_ts"] = last_passive_ts

    if data:
        result = _update("users", {"telegram_id": telegram_id}, data)
        return result is not None
    return False

# ---------- Cats Functions ----------

def get_user_cats(owner_id: int, include_dead: bool = False) -> List[Dict]:
    """Get all cats for a user by owner_id."""
    params = {"owner_id": owner_id}
    if not include_dead:
        params["is_alive"] = "eq.true"
    return _get("cats", params)

def get_cat(cat_id: int, owner_id: int = None) -> Optional[Dict]:
    """Get a cat by its ID and optionally filter by owner."""
    params = {"id": cat_id}
    if owner_id is not None:
        params["owner_id"] = owner_id
    rows = _get("cats", params)
    return rows[0] if rows else None

def add_cat(owner_id: int, name: str, rarity: str, element: str, 
            trait: str, description: str) -> Optional[int]:
    """Add a new cat for a user."""
    data = {
        "owner_id": owner_id,
        "name": name,
        "rarity": rarity,
        "element": element,
        "trait": trait,
        "description": description,
        "level": 1,
        "xp": 0,
        "hunger": 100,
        "happiness": 100,
        "stat_power": 1,
        "stat_agility": 1,
        "stat_luck": 1,
        "gear": "",
        "is_alive": True,
        "created_at": int(time.time()),
        "last_tick_ts": int(time.time()),
    }
    result = _insert("cats", data)
    return result.get("id") if result else None

def update_cat_stats(cat_id: int, owner_id: int, **kwargs) -> bool:
    """
    Update stats for a cat.
    Accepts: hunger, happiness, xp, level, gear, stat_power, 
             stat_agility, stat_luck, last_tick_ts, is_alive, description
    """
    if not kwargs:
        return False
    
    # Remove None values
    data = {k: v for k, v in kwargs.items() if v is not None}
    
    if data:
        result = _update("cats", {"id": cat_id, "owner_id": owner_id}, data)
        return result is not None
    return False

def kill_cat(cat_id: int, owner_id: int) -> bool:
    """Mark a cat as dead."""
    data = {
        "is_alive": False,
        "death_ts": int(time.time()),
        "hunger": 0,
        "happiness": 0,
    }
    return update_cat_stats(cat_id, owner_id, **data)

def get_all_users(limit: int = 1000) -> List[Dict]:
    """Retrieve all users from the users table."""
    return _get("users", {"limit": limit, "order": "id.desc"})

def rename_cat(owner_id: int, cat_id: int, new_name: str) -> bool:
    """Rename a cat."""
    return update_cat_stats(cat_id, owner_id, name=new_name)

def set_cat_owner(cat_id: int, new_owner_id: int) -> bool:
    """Set a new owner for a cat."""
    data = {"owner_id": new_owner_id}
    result = _update("cats", {"id": cat_id}, data)
    return result is not None

def get_leaderboard(limit: int = 10) -> List[Dict]:
    """Get the leaderboard based on mew_points."""
    return _get("users", {
        "select": "telegram_id,username,mew_points",
        "order": "mew_points.desc",
        "limit": limit
    })

def register_user_group(user_id: int, chat_id: int) -> bool:
    """Register a user's chat group."""
    rows = _get("user_groups", {"user_id": user_id, "chat_id": chat_id})
    if not rows:
        data = {"user_id": user_id, "chat_id": chat_id}
        result = _insert("user_groups", data)
        return result is not None
    return True

def get_daily_event_count(chat_id: int, date_str: str) -> int:
    """Get daily event count for a chat."""
    # This is a simplified in-memory version; for production, store in DB
    return 0

def update_daily_event_count(chat_id: int, date_str: str, count: int) -> bool:
    """Update daily event count for a chat."""
    # For production, implement database storage
    return True
