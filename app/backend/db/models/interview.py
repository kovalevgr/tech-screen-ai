"""Session placeholder tables (data-model §Session placeholders).

These three tables are intentionally minimal (spec Clarification): a PK, a
``created_at``, and the foreign keys other T05 tables (or the rubric snapshot
mechanism) point at. Domain columns are owned by the tier that finalises each
table:

- ``position_template`` — name, stack link, JD text, rubric selection (T12).
- ``interview_session`` — ``rubric_snapshot JSONB NOT NULL`` (T15, §4),
  candidate link (Tier 5), status enum, magic-link token (T28), lifecycle
  timestamps.
- ``interview_plan`` — plan JSON, freeze flag, planner trace link (T24/T25).

The FKs into ``position_template`` / ``interview_session`` are NULLABLE so a
placeholder row can be created standalone before its parent exists.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base
from app.backend.db.models._mixins import TimestampCreated, UUIDPk


class PositionTemplate(UUIDPk, TimestampCreated, Base):
    """A reusable position definition (placeholder; extended by T12)."""

    __tablename__ = "position_template"


class InterviewSession(UUIDPk, TimestampCreated, Base):
    """A single interview run (placeholder; extended by T15 / Tier 5)."""

    __tablename__ = "interview_session"

    position_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("position_template.id"),
        nullable=True,
    )


class InterviewPlan(UUIDPk, TimestampCreated, Base):
    """The planner's per-session plan (placeholder; extended by T24/T25)."""

    __tablename__ = "interview_plan"

    interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=True,
    )
