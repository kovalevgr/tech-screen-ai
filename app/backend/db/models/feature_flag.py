"""``feature_flag`` table — the §9 dark-launch substrate (T05a).

This table is **explicitly carved out of constitution §3 (FR-013)**:

- It is **mutable by design** — flags get flipped on, flipped off, and rewritten
  by the configs-as-code sync workflow and (in emergencies) by direct SQL.
- The baseline migration ``0002_feature_flags.py`` **does NOT** attach the
  shared ``reject_audit_mutation()`` trigger to this table, and **does NOT**
  ``REVOKE UPDATE, DELETE`` from ``techscreen_app``. Both choices are
  deliberate. A future contributor must NOT extend §3 protections to this
  table "for consistency" with the six audit tables — that would defeat the
  emergency-disable path (SC-007) and break SC-009.
- ``feature_flag`` history lives in (a) the ``updated_at`` / ``updated_by``
  columns for the latest mutation, (b) git history of
  ``configs/feature-flags.yaml`` for the canonical PR-driven flips, and
  (c) the docs Sunset table for retired flags. None of these requires
  database-level immutability.

The model exists for ``mypy --strict`` coverage and for Alembic's
``target_metadata`` (so future ``alembic revision --autogenerate`` produces
zero diff against the hand-written 0002 migration). The runtime path in
``app/backend/services/feature_flags.py`` reads + writes the table with raw
SQL via asyncpg — no ORM session per call — for sub-millisecond cache-miss
latency.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base


class FeatureFlag(Base):
    """Row in the ``feature_flag`` table.

    See module docstring for the §3 carve-out rationale (FR-013). The column
    set mirrors the runtime contract: ``name`` is the natural key (also the
    string callers pass to ``is_enabled``); ``enabled`` is the runtime gate;
    ``owner`` / ``updated_at`` / ``updated_by`` carry audit metadata;
    ``default_value`` is reserved for future non-boolean payloads.
    """

    __tablename__ = "feature_flag"

    name: Mapped[str] = mapped_column(Text, primary_key=True)
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=func.false(),
    )
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    default_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_by: Mapped[str | None] = mapped_column(Text, nullable=True)
