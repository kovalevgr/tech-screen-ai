"""Shared column mixins for the T05 schema.

- :class:`UUIDPk` — a UUID primary key defaulted server-side by
  ``gen_random_uuid()`` (pgcrypto, research §7). Server-side generation lets
  plain ``INSERT ... DEFAULT`` work from SQL probes and bulk imports without
  the app pre-computing IDs.
- :class:`TimestampCreated` — a ``created_at TIMESTAMPTZ NOT NULL`` defaulted
  to ``now()`` (research §10). The append-only ``audit_log`` table uses ``ts``
  instead and therefore does **not** use this mixin.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPk:
    """Mixin adding a server-defaulted UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampCreated:
    """Mixin adding a ``created_at TIMESTAMPTZ NOT NULL DEFAULT now()`` column."""

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
