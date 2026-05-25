"""Async-aware Alembic environment for TechScreen (T05, research §1).

A single ``asyncpg`` driver serves both the app runtime and migrations: the
online path opens an async connection and runs the migration body via
``connection.run_sync(...)``. The offline path renders DDL without any
connection, which is what the T10 ``alembic upgrade head --sql`` dry-run gate
relies on — every structural statement in ``0001_baseline.py`` is raw
``op.execute()`` SQL that renders verbatim offline.

The database URL is read from :class:`Settings` (``DATABASE_URL``); it is never
hard-coded in ``alembic.ini`` (constitution §5). Offline mode falls back to a
dialect-only placeholder URL so ``--sql`` works with no env configured.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import the model package (side-effect) so every table is registered on
# Base.metadata before Alembic inspects ``target_metadata`` for autogenerate.
import app.backend.db.models  # noqa: F401  (side-effect import: populates metadata)
from alembic import context
from app.backend.db.base import Base
from app.backend.settings import Settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Offline `--sql` rendering needs a dialect but no live server. asyncpg is an
# async driver and cannot be used by Alembic's offline literal renderer, so we
# render against the synchronous psycopg dialect name (DDL is dialect-portable
# across the two Postgres drivers; our migration uses only raw SQL + core ops).
_OFFLINE_PLACEHOLDER_URL = "postgresql://techscreen@localhost/techscreen"


def _database_url() -> str | None:
    """Resolve the migration DSN from Settings (``DATABASE_URL``)."""
    return Settings().database_url


def run_migrations_offline() -> None:
    """Render migrations as SQL without a DB connection (the ``--sql`` gate)."""
    url = _database_url() or _OFFLINE_PLACEHOLDER_URL
    # Strip the +asyncpg driver tag: offline literal rendering uses the
    # default (sync) dialect; asyncpg has no offline renderer.
    url = url.replace("+asyncpg", "")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run the migration body against a (sync-facade) connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Open an async connection and run migrations via ``run_sync``."""
    url = _database_url()
    if url is None:
        raise RuntimeError(
            "DATABASE_URL is not set; cannot run online migrations. "
            "Set DATABASE_URL or use `alembic upgrade head --sql` for offline."
        )
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
