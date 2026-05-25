"""Async engine + session factory for the FastAPI runtime.

Used by application code in later tiers (repositories accept an
``AsyncSession``); it is **not** imported by Alembic — migrations open their
own connection in ``alembic/env.py``. No model module imports this file.

The factory is lazy: it reads ``settings.database_url`` only when first
asked for an engine, so importing this module never requires a configured
database (keeps the no-DB unit run and module-import smoke tests green).
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.backend.settings import Settings


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when an async engine is requested but ``DATABASE_URL`` is unset."""


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Return the process-wide async engine, creating it on first use.

    Returns:
        The shared :class:`AsyncEngine` bound to ``settings.database_url``.

    Raises:
        DatabaseNotConfiguredError: If ``DATABASE_URL`` is not set.
    """
    settings = Settings()
    if settings.database_url is None:
        raise DatabaseNotConfiguredError("DATABASE_URL is not set; cannot create an async engine.")
    return create_async_engine(settings.database_url, future=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return the process-wide ``async_sessionmaker`` bound to the engine.

    Returns:
        An :class:`async_sessionmaker` producing :class:`AsyncSession` objects.

    Raises:
        DatabaseNotConfiguredError: If ``DATABASE_URL`` is not set.
    """
    return async_sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
        class_=AsyncSession,
    )
