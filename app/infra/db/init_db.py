import asyncio

from app.infra.db.session import engine

# Base مشترک
from app.domain.users.models import Base  # noqa: F401

# فقط برای اینکه مدل‌ها import شوند و Base.metadata پر شود:
from app.domain.users.models import User  # noqa: F401
from app.domain.cats.models import Cat, UserCat  # noqa: F401


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created/updated")


if __name__ == "__main__":
    asyncio.run(init_db())
