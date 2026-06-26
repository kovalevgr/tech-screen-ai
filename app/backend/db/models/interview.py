"""Session + position-template tables (data-model §Session, §Position Template).

``interview_session`` and ``interview_plan`` stay intentionally minimal
placeholders (spec Clarification): a PK, a ``created_at``, and the foreign keys
other tables point at. Their domain columns are owned by the tier that finalises
each table:

- ``interview_session`` — ``rubric_snapshot JSONB NOT NULL`` (T15, §4),
  candidate link (Tier 5), status enum, magic-link token (T28), lifecycle
  timestamps.
- ``interview_plan`` — plan JSON, freeze flag, planner trace link (T24/T25).

``position_template`` is **finalised here (T12)**: title, level, optional JD
text, soft-delete marker, ownership, and the stack/competency selections via two
association tables. It is **not** an append-only table (§3 excludes it), so
recruiter edits are normal UPDATEs; deletion is a soft archive (``archived_at``).

The FKs into ``position_template`` / ``interview_session`` are NULLABLE so a
placeholder row can be created standalone before its parent exists.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base
from app.backend.db.models._mixins import TimestampCreated, UUIDPk


class PositionTemplate(UUIDPk, TimestampCreated, Base):
    """A reusable, recruiter-authored definition of a role to interview for (T12)."""

    __tablename__ = "position_template"
    __table_args__ = (
        CheckConstraint(
            "level IN ('Junior', 'Middle', 'Senior', 'Tech Leader')",
            name="ck_position_template_level",
        ),
    )

    # Domain columns. `title`/`level` carry a transitional server_default so the
    # additive migration is zero-downtime on a table that may already hold dev
    # rows (research §3); the Pydantic boundary enforces a non-empty title.
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(Text, nullable=False, server_default="Middle")
    archived_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("user.id"), nullable=True
    )


class PositionTemplateStack(UUIDPk, TimestampCreated, Base):
    """Which rubric stacks a Position Template covers (selection link)."""

    __tablename__ = "position_template_stack"
    __table_args__ = (
        UniqueConstraint("position_template_id", "stack_id", name="uq_position_template_stack"),
    )

    position_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("position_template.id"), nullable=False
    )
    stack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("stack.id"), nullable=False
    )


class PositionTemplateCompetency(UUIDPk, TimestampCreated, Base):
    """Which competencies a Position Template assesses, with the must-have flag."""

    __tablename__ = "position_template_competency"
    __table_args__ = (
        UniqueConstraint(
            "position_template_id", "competency_id", name="uq_position_template_competency"
        ),
    )

    position_template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("position_template.id"), nullable=False
    )
    competency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("competency.id"), nullable=False
    )
    must_have: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class InterviewSession(UUIDPk, TimestampCreated, Base):
    """A single interview run (placeholder; extended by Tier 5).

    T15 adds ``rubric_snapshot`` — the frozen, self-contained copy of the rubric
    tree the session is assessed against (constitution §4). It is NOT NULL with a
    transitional ``'{}'`` default so the placeholder/seed inserts (which predate
    real session creation, T28) keep working; every real session overwrites the
    default via ``services.rubric_snapshot.freeze_session_rubric``.
    """

    __tablename__ = "interview_session"

    position_template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("position_template.id"),
        nullable=True,
    )
    rubric_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )


class InterviewPlan(UUIDPk, TimestampCreated, Base):
    """The planner's per-session plan (placeholder; extended by T24/T25)."""

    __tablename__ = "interview_plan"

    interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=True,
    )
