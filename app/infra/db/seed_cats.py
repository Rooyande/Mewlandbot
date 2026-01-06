import asyncio

from sqlalchemy import select

from app.infra.db.session import AsyncSessionLocal
from app.domain.cats.models import Cat, CatRarity


SEED_CATS = [
    {
        "name": "Siamese",
        "rarity": CatRarity.COMMON.value,
        "price_meow": 10,
        "base_meow_amount": 1,
        "base_meow_interval_sec": 600,
        "base_image_path": "assets/cats/siamese.png",
    },
    {
        "name": "Orange",
        "rarity": CatRarity.COMMON.value,
        "price_meow": 12,
        "base_meow_amount": 1,
        "base_meow_interval_sec": 540,
        "base_image_path": "assets/cats/orange.png",
    },
    {
        "name": "British Shorthair",
        "rarity": CatRarity.RARE.value,
        "price_meow": 40,
        "base_meow_amount": 2,
        "base_meow_interval_sec": 600,
        "base_image_path": "assets/cats/british.png",
    },
    {
        "name": "Persian",
        "rarity": CatRarity.EPIC.value,
        "price_meow": 120,
        "base_meow_amount": 5,
        "base_meow_interval_sec": 600,
        "base_image_path": "assets/cats/persian.png",
    },
    {
        "name": "Legend Lion",
        "rarity": CatRarity.LEGENDARY.value,
        "price_meow": 350,
        "base_meow_amount": 12,
        "base_meow_interval_sec": 600,
        "base_image_path": "assets/cats/legend_lion.png",
    },
    {
        "name": "Mythic Swan",
        "rarity": CatRarity.MYTHIC.value,
        "price_meow": 1000,
        "base_meow_amount": 40,
        "base_meow_interval_sec": 600,
        "base_image_path": "assets/cats/mythic_swan.png",
    },
]


async def seed() -> None:
    async with AsyncSessionLocal() as session:
        for item in SEED_CATS:
            exists = await session.execute(
                select(Cat).where(Cat.name == item["name"])
            )
            cat = exists.scalar_one_or_none()
            if cat:
                continue

            cat = Cat(
                name=item["name"],
                rarity=item["rarity"],
                price_meow=item["price_meow"],
                base_meow_amount=item["base_meow_amount"],
                base_meow_interval_sec=item["base_meow_interval_sec"],
                base_image_path=item["base_image_path"],
                is_active=True,
            )
            session.add(cat)

        await session.commit()

    print("Cats seeded.")


if __name__ == "__main__":
    asyncio.run(seed())
