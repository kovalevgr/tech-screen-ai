"""Database layer: declarative base, async session factory, and models.

Introduced by T05 (DB schema v0 + Alembic baseline). The runtime async
engine/session live in :mod:`app.backend.db.session`; the ORM models that
feed both the application and Alembic's ``target_metadata`` live under
:mod:`app.backend.db.models`.
"""

from __future__ import annotations

from app.backend.db.base import Base, metadata

__all__ = ["Base", "metadata"]
