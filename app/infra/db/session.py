from __future__ import annotations

from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import settings


def _build_database_url() -> str:
    """
    Supports both styles:
    1) settings.DATABASE_URL (if exists)
    2) DB_* pieces (DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME)
    """

    # Style 1: DATABASE_URL if defined in Settings
    if hasattr(settings, "DATABASE_URL"):
        url = getattr(settings, "DATABASE_URL")
        if url:
            return url

    # Style 2: Build from DB_* parts
    # We assume these exist because your project was already using them.
    user = getattr(settings, "DB_USER")
    password = getattr(settings, "DB_PASSWORD")
    host = getattr(settings, "DB_HOST")
    port = getattr(settings, "DB_PORT")
    name = getattr(settings, "DB_NAME")

    return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"


DATABASE_URL = _build_database_url()

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=getattr(settings, "DB_ECHO", False),
    pool_pre_ping=True,
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_session() -> AsyncSession:
    """
    Usage:
        async with get_session() as session:
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
