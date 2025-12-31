import random
from typing import Dict, Any, List, Tuple

RARITY_CONFIG: Dict[str, Dict[str, Any]] = {
    "common": {"price": 200, "base_mph": 1.0, "emoji": "⚪️"},
    "rare": {"price": 800, "base_mph": 3.0, "emoji": "🟦"},
    "epic": {"price": 2500, "base_mph": 7.0, "emoji": "🟪"},
    "legendary": {"price": 7000, "base_mph": 15.0, "emoji": "🟨"},
    "mythic": {"price": 15000, "base_mph": 30.0, "emoji": "🟥"},
    "special": {"price": 50000, "base_mph": 50.0, "emoji": "🌟"},
}

RARITY_WEIGHTS: List[Tuple[str, int]] = [
    ("common", 50),
    ("rare", 23),
    ("epic", 12),
    ("legendary", 8),
    ("mythic", 5),
    ("special", 2),
]

ELEMENTS = ["fire", "water", "earth", "air", "shadow", "light", "ice", "candy"]
TRAITS = ["lazy", "hyper", "greedy", "cuddly", "brave", "shy", "noisy", "sleepy"]


def rarity_emoji(rarity: str) -> str:
    return RARITY_CONFIG.get(rarity, RARITY_CONFIG["common"]).get("emoji", "⚪️")


def choose_rarity() -> str:
    roll = random.randint(1, 100)
    cur = 0
    for rarity, w in RARITY_WEIGHTS:
        cur += w
        if roll <= cur:
            return rarity
    return "common"
