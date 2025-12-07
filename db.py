# Add these functions to db.py

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

def create_clan(leader_id: int, name: str, creation_cost: int) -> bool:
    """Create a new clan."""
    # Check if user already in a clan
    existing = _get("clan_members", {"user_id": leader_id})
    if existing:
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
    
    # Add leader as member
    member_data = {
        "clan_id": result["id"],
        "user_id": leader_id
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
        "user_id": user_id
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
    
    return result

def get_user_by_db_id(user_db_id: int) -> Optional[Dict]:
    """Get user by database ID."""
    rows = _get("users", {"id": user_db_id})
    return rows[0] if rows else None

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
    now = int(time.time())
    # This is a simplified query - in production use proper filtering
    all_listings = _get("market_listings", {})
    
    active_listings = [
        l for l in all_listings 
        if l.get("status") == "active" and l.get("expires_at", 0) > now
    ]
    
    return active_listings[:limit]

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

def add_special_cat(owner_id: int, name: str, rarity: str, element: str, 
                    trait: str, description: str, special_ability: str) -> Optional[int]:
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
        "stat_power": random.randint(3, 5),
        "stat_agility": random.randint(3, 5),
        "stat_luck": random.randint(3, 5),
        "gear": "",
        "is_alive": True,
        "created_at": int(time.time()),
        "last_tick_ts": int(time.time()),
    }
    result = _insert("cats", data)
    return result.get("id") if result else None

def get_special_cats(owner_id: int) -> List[Dict]:
    """Get user's special cats."""
    cats = _get("cats", {"owner_id": owner_id, "is_special": "eq.true"})
    return [cat for cat in cats if cat.get("is_alive", True)]

def get_seasonal_events(season: str) -> List[Dict]:
    """Get seasonal events."""
    return _get("seasonal_events", {"season": season})

def add_seasonal_event(season: str, event_data: Dict) -> bool:
    """Add seasonal event."""
    data = {
        "season": season,
        "event_data": event_data,
        "created_at": int(time.time())
    }
    return _insert("seasonal_events", data) is not None

def get_user_seasonal_progress(user_id: int, season: str) -> Optional[Dict]:
    """Get user's seasonal progress."""
    rows = _get("seasonal_progress", {"user_id": user_id, "season": season})
    return rows[0] if rows else None

def update_seasonal_progress(user_id: int, season: str, progress_data: Dict) -> bool:
    """Update user's seasonal progress."""
    existing = get_user_seasonal_progress(user_id, season)
    
    if existing:
        # Update existing
        data = {
            "progress_data": progress_data,
            "updated_at": int(time.time())
        }
        return _update("seasonal_progress", {"id": existing["id"]}, data) is not None
    else:
        # Create new
        data = {
            "user_id": user_id,
            "season": season,
            "progress_data": progress_data
        }
        return _insert("seasonal_progress", data) is not None
