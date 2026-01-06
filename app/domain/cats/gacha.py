import random
from dataclasses import dataclass
from typing import Iterable

from app.domain.cats.models import Cat, CatRarity


@dataclass(frozen=True)
class RarityRates:
    common: float = 0.70
    rare: float = 0.20
    epic: float = 0.08
    legendary: float = 0.019
    mythic: float = 0.001  # خیلی خیلی کم

    def as_weights(self) -> dict[str, float]:
        return {
            CatRarity.COMMON.value: self.common,
            CatRarity.RARE.value: self.rare,
            CatRarity.EPIC.value: self.epic,
            CatRarity.LEGENDARY.value: self.legendary,
            CatRarity.MYTHIC.value: self.mythic,
        }


def pick_rarity(rates: RarityRates) -> str:
    weights = rates.as_weights()
    rarities = list(weights.keys())
    probs = list(weights.values())
    return random.choices(rarities, weights=probs, k=1)[0]


def pick_cat_from_pool(cats: Iterable[Cat], rarity: str) -> Cat | None:
    candidates = [c for c in cats if c.is_active and c.rarity == rarity]
    if not candidates:
        return None
    return random.choice(candidates)
