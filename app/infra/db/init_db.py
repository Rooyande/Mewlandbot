import asyncio

from app.infra.db.session import engine
from app.domain.users.models import Base


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created")


if __name__ == "__main__":
    asyncio.run(init_db())
