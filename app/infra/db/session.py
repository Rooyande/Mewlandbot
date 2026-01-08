from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import settings


def _resolve_database_url() -> str:
    """
    Priority:
    1) If ENV has DATABASE_URL / DB_URL / SQLALCHEMY_DATABASE_URL => use it
    2) Else use settings.database_url() (your project standard)
    """

    # 1) ENV-based URL (most robust for deployments)
    env_url = (
        os.getenv("DATABASE_URL")
        or os.getenv("DB_URL")
        or os.getenv("SQLALCHEMY_DATABASE_URL")
    )
    if env_url:
        return env_url

    # 2) Project's Settings method
    return settings.database_url()


DATABASE_URL: str = _resolve_database_url()

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

async_session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
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
