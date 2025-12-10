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

# Constants for new features
CLAN_MAX_MEMBERS = 50
MARKET_FEE_PERCENT = 5
MARKET_LISTING_DURATION = 7 * 24 * 3600

# ---------- Helper functions ----------

def _format_filter(key: str, value: Any) -> str:
    """Format filter values for Supabase query."""
    if key in ['telegram_id', 'id', 'owner_id', 'user_id', 'chat_id', 'cat_id', 'clan_id', 'seller_id']:
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
    
    # Create tables if they don't exist (Supabase handles this via dashboard)
    # For production, create tables via Supabase SQL editor:
    """
    -- Users table
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        telegram_id BIGINT UNIQUE NOT NULL,
        username TEXT,
        mew_points INTEGER DEFAULT 100,
        last_mew_ts INTEGER,
        last_passive_ts INTEGER DEFAULT EXTRACT(EPOCH FROM NOW()),
        created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())
    );
    
    -- Cats table
    CREATE TABLE IF NOT EXISTS cats (
        id SERIAL PRIMARY KEY,
        owner_id INTEGER REFERENCES users(id),
        name TEXT NOT NULL,
        rarity TEXT NOT NULL,
        element TEXT NOT NULL,
        trait TEXT NOT NULL,
        description TEXT,
        level INTEGER DEFAULT 1,
        xp INTEGER DEFAULT 0,
        hunger INTEGER DEFAULT 100,
        happiness INTEGER DEFAULT 100,
        stat_power INTEGER DEFAULT 1,
        stat_agility INTEGER DEFAULT 1,
        stat_luck INTEGER DEFAULT 1,
        gear TEXT DEFAULT '',
        is_alive BOOLEAN DEFAULT TRUE,
        is_special BOOLEAN DEFAULT FALSE,
        special_ability TEXT,
        last_breed_ts INTEGER DEFAULT 0,
        created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW()),
        last_tick_ts INTEGER DEFAULT EXTRACT(EPOCH FROM NOW()),
        death_ts INTEGER
    );
    
    -- User groups table
    CREATE TABLE IF NOT EXISTS user_groups (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        chat_id BIGINT NOT NULL,
        UNIQUE(user_id, chat_id)
    );
    
    -- Achievements table
    CREATE TABLE IF NOT EXISTS achievements (
        id SERIAL PRIMARY KEY,
        user_id INTEGER REFERENCES users(id),
        achievement_id TEXT NOT NULL,
        achieved_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW()),
        UNIQUE(user_id, achievement_id)
    );
    
    -- Clans table
    CREATE TABLE IF NOT EXISTS clans (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        leader_id INTEGER REFERENCES users(id),
        created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())
    );
    
    -- Clan members table
    CREATE TABLE IF NOT EXISTS clan_members (
        id SERIAL PRIMARY KEY,
        clan_id INTEGER REFERENCES clans(id),
        user_id INTEGER REFERENCES users(id),
        joined_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW()),
        UNIQUE(user_id)
    );
    
    -- Market listings table
    CREATE TABLE IF NOT EXISTS market_listings (
        id SERIAL PRIMARY KEY,
        cat_id INTEGER REFERENCES cats(id),
        seller_id INTEGER REFERENCES users(id),
        buyer_id INTEGER REFERENCES users(id),
        price INTEGER NOT NULL,
        fee INTEGER NOT NULL,
        status TEXT DEFAULT 'active',
        created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW()),
        expires_at INTEGER NOT NULL,
        sold_at INTEGER
    );
    
    -- Breeding history table
    CREATE TABLE IF NOT EXISTS breeding_history (
        id SERIAL PRIMARY KEY,
        parent1_id INTEGER REFERENCES cats(id),
        parent2_id INTEGER REFERENCES cats(id),
        offspring_id INTEGER REFERENCES cats(id),
        success BOOLEAN,
        bred_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())
    );
    
    -- Daily events table
    CREATE TABLE IF NOT EXISTS daily_events (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        date TEXT NOT NULL,
        count INTEGER DEFAULT 0,
        UNIQUE(chat_id, date)
    );
    
    -- Active events table
    CREATE TABLE IF NOT EXISTS active_events (
        id SERIAL PRIMARY KEY,
        chat_id BIGINT NOT NULL,
        event_id TEXT NOT NULL,
        event_text TEXT NOT NULL,
        expected_answer TEXT NOT NULL,
        created_at INTEGER DEFAULT EXTRACT(EPOCH FROM NOW())
    );
    
    -- Add indexes for performance
    CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
    CREATE INDEX IF NOT EXISTS idx_cats_owner_id ON cats(owner_id);
    CREATE INDEX IF NOT EXISTS idx_cats_is_alive ON cats(is_alive);
    CREATE INDEX IF NOT EXISTS idx_market_status ON market_listings(status);
    CREATE INDEX IF NOT EXISTS idx_market_expires ON market_listings(expires_at);
    """

# ---------- Users Functions ----------

def get_user(telegram_id: int) -> Optional[Dict]:
    """Get a user by their telegram_id."""
    rows = _get("users", {"telegram_id": telegram_id})
    return rows[0] if rows else None

def get_user_by_db_id(user_db_id: int) -> Optional[Dict]:
    """Get user by database ID."""
    rows = _get("users", {"id": user_db_id})
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
        "is_special": False,
        "last_breed_ts": 0,
        "created_at": int(time.time()),
        "last_tick_ts": int(time.time()),
    }
    result = _insert("cats", data)
    return result.get("id") if result else None

def update_cat_stats(cat_id: int, owner_id: int, **kwargs) -> bool:
    """
    Update stats for a cat.
    Accepts: hunger, happiness, xp, level, gear, stat_power, 
             stat_agility, stat_luck, last_tick_ts, is_alive, 
             description, name, last_breed_ts, special_ability
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

# ---------- Achievements Functions ----------

def add_achievement(user_id: int, achievement_id: str) -> bool:
    """Add achievement for user."""
    data = {
        "user_id": user_id,
        "achievement_id": achievement_id,
        "achieved_at": int(time.time())
    }
    result = _insert("achievements", data)
    return result is not None

def get_user_achievements(user_id: int) -> List[Dict]:
    """Get user achievements."""
    return _get("achievements", {"user_id": user_id})

# ---------- Clan Functions ----------

def create_clan(leader_id: int, name: str, creation_cost: int) -> bool:
    """Create a new clan."""
    # Check if clan name already exists
    existing_clans = _get("clans", {"name": name})
    if existing_clans:
        return False
    
    # Create clan
    clan_data = {
        "name": name,
        "leader_id": leader_id,
        "created_at": int(time.time())
    }
    result = _insert("clans", clan_data)
    
    if not result:
        return False
    
    clan_id = result["id"]
    
    # Add leader as member
    member_data = {
        "clan_id": clan_id,
        "user_id": leader_id,
        "joined_at": int(time.time())
    }
    return _insert("clan_members", member_data) is not None

def join_clan(user_id: int, clan_name: str) -> bool:
    """Join an existing clan."""
    # Check if already in a clan
    existing = _get("clan_members", {"user_id": user_id})
    if existing:
        return False
    
    # Get clan
    clans = _get("clans", {"name": clan_name})
    if not clans:
        return False
    
    clan = clans[0]
    
    # Check clan size
    members = _get("clan_members", {"clan_id": clan["id"]})
    if len(members) >= CLAN_MAX_MEMBERS:
        return False
    
    # Join clan
    member_data = {
        "clan_id": clan["id"],
        "user_id": user_id,
        "joined_at": int(time.time())
    }
    return _insert("clan_members", member_data) is not None

def get_clan_info(user_id: int) -> Optional[Dict]:
    """Get clan info for user."""
    # Get user's clan membership
    memberships = _get("clan_members", {"user_id": user_id})
    if not memberships:
        return None
    
    membership = memberships[0]
    
    # Get clan details
    clans = _get("clans", {"id": membership["clan_id"]})
    if not clans:
        return None
    
    clan = clans[0]
    
    # Get leader info
    leader = get_user_by_db_id(clan["leader_id"])
    
    return {
        "id": clan["id"],
        "name": clan["name"],
        "leader_id": clan["leader_id"],
        "leader_username": leader.get("username") if leader else None,
        "created_at": clan["created_at"]
    }

def get_clan_by_name(clan_name: str) -> Optional[Dict]:
    """Get clan by name."""
    clans = _get("clans", {"name": clan_name})
    return clans[0] if clans else None

def get_clan_members(clan_id: int) -> List[Dict]:
    """Get clan members with user info."""
    members = _get("clan_members", {"clan_id": clan_id})
    result = []
    
    for member in members:
        user = get_user_by_db_id(member["user_id"])
        if user:
            result.append({
                "user_id": user["id"],
                "telegram_id": user["telegram_id"],
                "username": user.get("username"),
                "mew_points": user.get("mew_points", 0),
                "joined_at": member["joined_at"]
            })
    
    # Sort by points descending
    result.sort(key=lambda x: x["mew_points"], reverse=True)
    
    return result

def leave_clan(user_id: int) -> bool:
    """Leave current clan."""
    return _delete("clan_members", {"user_id": user_id})

def delete_clan(clan_id: int) -> bool:
    """Delete a clan."""
    # First delete all members
    _delete("clan_members", {"clan_id": clan_id})
    # Then delete the clan
    return _delete("clans", {"id": clan_id})

def transfer_clan_leadership(clan_id: int, new_leader_id: int) -> bool:
    """Transfer clan leadership to another member."""
    data = {"leader_id": new_leader_id}
    result = _update("clans", {"id": clan_id}, data)
    return result is not None

def get_available_clans(limit: int = 20) -> List[Dict]:
    """Get clans that are not full."""
    all_clans = _get("clans", {"limit": limit})
    available_clans = []
    
    for clan in all_clans:
        members = get_clan_members(clan["id"])
        if len(members) < CLAN_MAX_MEMBERS:
            leader = get_user_by_db_id(clan["leader_id"])
            clan["leader_username"] = leader.get("username") if leader else None
            available_clans.append(clan)
    
    return available_clans

# ---------- Marketplace Functions ----------

def create_market_listing(cat_id: int, seller_id: int, price: int, fee: int, expires_at: int) -> Optional[int]:
    """Create marketplace listing."""
    # Check if cat already listed
    existing = _get("market_listings", {"cat_id": cat_id, "status": "active"})
    if existing:
        return None
    
    data = {
        "cat_id": cat_id,
        "seller_id": seller_id,
        "price": price,
        "fee": fee,
        "status": "active",
        "created_at": int(time.time()),
        "expires_at": expires_at
    }
    
    result = _insert("market_listings", data)
    return result.get("id") if result else None

def get_market_listings(limit: int = 20) -> List[Dict]:
    """Get active market listings."""
    all_listings = _get("market_listings", {"limit": limit})
    
    # Filter active listings that haven't expired
    now = int(time.time())
    active_listings = [
        l for l in all_listings 
        if l.get("status") == "active" and l.get("expires_at", 0) > now
    ]
    
    return active_listings

def buy_market_listing(listing_id: int, buyer_id: int) -> bool:
    """Process marketplace purchase."""
    listings = _get("market_listings", {"id": listing_id})
    if not listings:
        return False
    
    listing = listings[0]
    
    # Check if still active
    if listing.get("status") != "active" or listing.get("expires_at", 0) < int(time.time()):
        return False
    
    # Update listing
    update_data = {
        "buyer_id": buyer_id,
        "status": "sold",
        "sold_at": int(time.time())
    }
    
    result = _update("market_listings", {"id": listing_id}, update_data)
    if not result:
        return False
    
    # Transfer cat ownership
    return set_cat_owner(listing["cat_id"], buyer_id)

def get_user_market_listings(user_id: int) -> List[Dict]:
    """Get user's market listings."""
    return _get("market_listings", {"seller_id": user_id})

def cancel_market_listing(listing_id: int) -> bool:
    """Cancel marketplace listing."""
    return _update("market_listings", {"id": listing_id}, {"status": "cancelled"}) is not None

# ---------- Breeding Functions ----------

def breed_cats(parent1_id: int, parent2_id: int, offspring_id: int, success: bool) -> bool:
    """Record breeding attempt."""
    data = {
        "parent1_id": parent1_id,
        "parent2_id": parent2_id,
        "offspring_id": offspring_id,
        "success": success,
        "bred_at": int(time.time())
    }
    return _insert("breeding_history", data) is not None

def get_cat_offspring(cat_id: int) -> List[Dict]:
    """Get offspring of a cat."""
    as_parent1 = _get("breeding_history", {"parent1_id": cat_id})
    as_parent2 = _get("breeding_history", {"parent2_id": cat_id})
    return as_parent1 + as_parent2

# ---------- Special Cats Functions ----------

def add_special_cat(owner_id: int, name: str, rarity: str, element: str, 
                    trait: str, description: str, special_ability: str = "") -> Optional[int]:
    """Add a special cat."""
    data = {
        "owner_id": owner_id,
        "name": name,
        "rarity": rarity,
        "element": element,
        "trait": trait,
        "description": description,
        "special_ability": special_ability,
        "is_special": True,
        "level": 1,
        "xp": 0,
        "hunger": 100,
        "happiness": 100,
        "stat_power": 1,
        "stat_agility": 1,
        "stat_luck": 1,
        "gear": "",
        "is_alive": True,
        "last_breed_ts": 0,
        "created_at": int(time.time()),
        "last_tick_ts": int(time.time()),
    }
    result = _insert("cats", data)
    return result.get("id") if result else None

def get_special_cats(owner_id: int) -> List[Dict]:
    """Get user's special cats."""
    cats = _get("cats", {"owner_id": owner_id, "is_special": "eq.true"})
    return [cat for cat in cats if cat.get("is_alive", True)]

# ---------- Event System Functions ----------

def get_daily_event_count(chat_id: int, date_str: str) -> int:
    """Get daily event count for a chat."""
    rows = _get("daily_events", {"chat_id": chat_id, "date": date_str})
    return rows[0]["count"] if rows else 0

def update_daily_event_count(chat_id: int, date_str: str, count: int) -> bool:
    """Update daily event count for a chat."""
    rows = _get("daily_events", {"chat_id": chat_id, "date": date_str})
    
    if rows:
        # Update existing record
        data = {"count": count}
        result = _update("daily_events", {"id": rows[0]["id"]}, data)
        return result is not None
    else:
        # Create new record
        data = {
            "chat_id": chat_id,
            "date": date_str,
            "count": count
        }
        result = _insert("daily_events", data)
        return result is not None

def update_daily_events_table():
    """Initialize daily events table if needed."""
    # This is a placeholder - tables should be created via SQL
    pass

def create_active_event(chat_id: int, event_id: str, event_text: str, expected_answer: str) -> bool:
    """Create an active event."""
    # First, delete any existing active events for this chat
    _delete("active_events", {"chat_id": chat_id})
    
    # Create new event
    data = {
        "chat_id": chat_id,
        "event_id": event_id,
        "event_text": event_text,
        "expected_answer": expected_answer,
        "created_at": int(time.time())
    }
    result = _insert("active_events", data)
    return result is not None

def get_active_events(chat_id: int) -> List[Dict]:
    """Get active events for a chat."""
    events = _get("active_events", {"chat_id": chat_id})
    
    # Clean up old events (older than 2 hours)
    now = int(time.time())
    fresh_events = []
    for event in events:
        if now - event.get("created_at", 0) < 7200:  # 2 hours
            fresh_events.append(event)
        else:
            _delete("active_events", {"id": event["id"]})
    
    return fresh_events

def delete_active_event(chat_id: int) -> bool:
    """Delete active event for a chat."""
    return _delete("active_events", {"chat_id": chat_id})
