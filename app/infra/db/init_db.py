import asyncio

from app.infra.db.session import engine
from app.domain.users.models import Base

# ✅ مهم: فقط برای اینکه SQLAlchemy جدول‌ها را بشناسد
# هیچ چیز از این‌ها استفاده نمی‌کنیم ولی import لازم است
import app.domain.cats.models  # noqa: F401
import app.domain.items.models  # noqa: F401


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created/updated")


if __name__ == "__main__":
    asyncio.run(init_db())
