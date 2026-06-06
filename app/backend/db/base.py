"""SQLAlchemy 2.x declarative base with a deterministic naming convention.

The naming convention (research §6) gives every constraint and index a
stable, predictable name so that future ``alembic revision --autogenerate``
runs produce clean, reviewable diffs instead of churning Postgres-assigned
constraint names. ``Base.metadata`` is what ``alembic/env.py`` imports as
``target_metadata``.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Stable names for indexes / unique / check / foreign-key / primary-key
# constraints (research §6). Keep in sync with the migration if ever changed.
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata: MetaData = MetaData(naming_convention=NAMING_CONVENTION)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model in :mod:`app.backend.db`."""

    metadata = metadata
