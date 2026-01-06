import asyncio

from sqlalchemy import select

from app.infra.db.session import AsyncSessionLocal
from app.domain.items.models import Item


SEED_ITEMS = [
    # flat boost
    ("Small Bowl", 50, "mps_flat", 0.0005),
    ("Medium Bowl", 120, "mps_flat", 0.0010),
    ("Big Bowl", 250, "mps_flat", 0.0020),
    ("Golden Bowl", 600, "mps_flat", 0.0050),

    # multiplier boost
    ("Fluffy Hat", 80, "mps_multiplier", 1.05),
    ("Cute Collar", 140, "mps_multiplier", 1.10),
    ("Luxury Bed", 220, "mps_multiplier", 1.15),
    ("Royal Crown", 400, "mps_multiplier", 1.25),
    ("Legend Cape", 700, "mps_multiplier", 1.35),
    ("Mythic Aura", 1200, "mps_multiplier", 1.50),

    # more items
    ("Fish Snack", 30, "mps_multiplier", 1.02),
    ("Milk Bottle", 40, "mps_multiplier", 1.03),
    ("Shiny Bell", 90, "mps_multiplier", 1.06),
    ("Soft Pillow", 110, "mps_multiplier", 1.07),
    ("Warm Blanket", 160, "mps_multiplier", 1.12),
    ("Magic Yarn", 300, "mps_multiplier", 1.18),
    ("Ancient Charm", 800, "mps_multiplier", 1.40),
    ("Lucky Coin", 200, "mps_multiplier", 1.14),
    ("Moon Dust", 1500, "mps_multiplier", 1.60),
    ("Sun Relic", 1800, "mps_multiplier", 1.70),
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Item.name))
        existing = {row[0] for row in res.all()}

        created = 0
        for name, price, effect_type, effect_value in SEED_ITEMS:
            if name in existing:
                continue

            session.add(
                Item(
                    name=name,
                    price_meow=price,
                    effect_type=effect_type,
                    effect_value=effect_value,
                    image_file_id=None,
                    is_active=True,
                )
            )
            created += 1

        await session.commit()

    print(f"Seed OK: {created} items inserted.")


if __name__ == "__main__":
    asyncio.run(seed())
