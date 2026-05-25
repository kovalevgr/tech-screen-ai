"""Append-only audit set — the six §3 tables (data-model §Audit; ADR-019).

All six carry the ``reject_audit_mutation()`` ``BEFORE UPDATE OR DELETE``
trigger and have ``UPDATE``/``DELETE`` revoked from ``techscreen_app`` in the
baseline migration. The §3 guarantee lives in the migration (trigger + revoke),
not in these models — the models exist for ``mypy --strict`` coverage and to
feed Alembic's ``target_metadata``.

The "corrections are new rows" shape (§3 / ADR-019) is encoded structurally:
``assessment_correction.assessment_id`` references the corrected ``assessment``
row; the old row is never mutated.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base
from app.backend.db.models._mixins import TimestampCreated, UUIDPk


class TurnTrace(UUIDPk, TimestampCreated, Base):
    """One row per LLM call.

    DEFERRED to T21: the rich columns reserved by T04's ``TraceRecord`` shape
    (``agent``, ``model``, ``model_version``, ``outcome``, ``attempts``,
    ``latency_ms``, ``cost_usd NUMERIC``, ``prompt_sha``) are intentionally NOT
    added here. T05 creates the table + the §3 guard; T21 adds those columns via
    a forward-only migration (constitution §10). This comment is T21's anchor.
    """

    __tablename__ = "turn_trace"

    interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=True,
    )


class Assessment(UUIDPk, TimestampCreated, Base):
    """The Assessor's output, per session × competency."""

    __tablename__ = "assessment"

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=False,
    )
    competency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competency.id"),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)


class AssessmentCorrection(UUIDPk, TimestampCreated, Base):
    """A reviewer override — a NEW row referencing the corrected assessment.

    Never a mutation of the original ``assessment`` row (§3 / ADR-019).
    """

    __tablename__ = "assessment_correction"

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assessment.id"),
        nullable=False,
    )
    corrected_score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    corrected_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=False,
    )


class TurnAnnotation(UUIDPk, TimestampCreated, Base):
    """A reviewer per-turn quality mark (label/comment columns deferred to T35)."""

    __tablename__ = "turn_annotation"

    turn_trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("turn_trace.id"),
        nullable=False,
    )
    annotated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=False,
    )


class AuditLog(UUIDPk, Base):
    """Actor / action / subject for every state change (§15: NO PII).

    Limited to ``actor_id`` / ``action`` / ``subject_hash`` / ``ts`` — never raw
    candidate PII. Uses ``ts`` (named in the implementation-plan) as its event
    timestamp; it has no separate ``created_at`` and therefore does NOT use the
    :class:`TimestampCreated` mixin.
    """

    __tablename__ = "audit_log"

    # NULLABLE: system actions have no human actor.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=True,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    # A hashed reference to the subject — never the raw subject (§15).
    subject_hash: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class SessionDecision(UUIDPk, TimestampCreated, Base):
    """The final hiring decision artefact (enum/justification deferred to T37)."""

    __tablename__ = "session_decision"

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=False,
    )
    decided_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=False,
    )
