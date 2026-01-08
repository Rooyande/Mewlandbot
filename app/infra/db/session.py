from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config.settings import settings


def _get_from_settings(*names: str) -> Optional[str]:
    """
    Safely fetch a string attribute from settings if it exists and is truthy.
    Tries names in order.
    """
    for name in names:
        if hasattr(settings, name):
            value = getattr(settings, name)
            if value:
                return str(value)
    return None


def _get_from_env(*names: str) -> Optional[str]:
    """
    Fetch a string value from environment variables if present and non-empty.
    Tries names in order.
    """
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return None


def _build_database_url() -> str:
    """
    Build database URL robustly, supporting multiple config styles.

    Priority:
    1) ENV: DATABASE_URL / DB_URL / SQLALCHEMY_DATABASE_URL
    2) settings: DATABASE_URL / DB_URL / SQLALCHEMY_DATABASE_URL
    3) ENV pieces: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME
    4) settings pieces: DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME

    If nothing found, raises RuntimeError with clear instructions.
    """

    # 1) ENV URL
    url = _get_from_env("DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL")
    if url:
        return url

    # 2) settings URL
    url = _get_from_settings("DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URL")
    if url:
        return url

    # helper to read parts either from env or settings
    def read_part(key: str) -> Optional[str]:
        return _get_from_env(key) or _get_from_settings(key)

    user = read_part("DB_USER")
    password = read_part("DB_PASSWORD")
    host = read_part("DB_HOST")
    port = read_part("DB_PORT")
    name = read_part("DB_NAME")

    if all([user, password, host, port, name]):
        return f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{name}"

    raise RuntimeError(
        "Database configuration is missing.\n"
        "Set one of these:\n"
        "  - ENV DATABASE_URL (recommended)\n"
        "  - ENV DB_URL\n"
        "  - ENV SQLALCHEMY_DATABASE_URL\n"
        "OR provide all parts:\n"
        "  - DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME\n"
    )


DATABASE_URL: str = _build_database_url()

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=bool(_get_from_env("DB_ECHO") or _get_from_settings("DB_ECHO") or False),
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
