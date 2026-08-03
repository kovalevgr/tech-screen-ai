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
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base
from app.backend.db.models._mixins import TimestampCreated, UUIDPk


class TurnTrace(UUIDPk, TimestampCreated, Base):
    """One row per LLM call — the durable audit trail (T21).

    Shape is the committed contract ``docs/contracts/turn-trace.schema.json``:
    T04's ``TraceRecord`` fields, the full payloads, and the orchestrator
    context. T05 created the table + the §3 guard; ``0007`` added the columns
    below via a forward-only migration (constitution §10).

    The non-nullable text columns carry a transitional ``''`` server default so
    the pre-T21 placeholder rows stayed valid through the additive migration;
    :class:`app.backend.llm.persistent_trace.PostgresTraceSink` always writes
    them explicitly.

    ``user_payload`` DOES carry candidate answers — this table is the §1 audit
    trail. Access is role-gated at the API layer, and constitution §15 keeps the
    payload out of logs, metrics and exports.
    """

    __tablename__ = "turn_trace"

    interview_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=True,
    )

    # --- orchestrator context (NULL for non-session calls) ------------------
    turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    transition: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- T04 TraceRecord mirror ---------------------------------------------
    agent: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    model: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    wrapper_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), nullable=False, server_default=text("0")
    )
    prompt_sha: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- full payloads -------------------------------------------------------
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    user_payload: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    response_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    parsed: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


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
    """The final hiring decision artefact (enum/justification deferred to T37).

    T21 widened this table for SYSTEM decisions: the orchestrator's
    ``RecordDecision`` commands (``plan_invalid``, ``agent_failure``,
    ``timeout``, ``operator``, ``completed``) and the cost-ceiling breach
    (``cost_ceiling``) have no human actor, so ``decided_by`` became nullable
    and ``reason`` records which decision was taken. Still append-only (§3):
    a superseding decision is a new row.
    """

    __tablename__ = "session_decision"

    interview_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("interview_session.id"),
        nullable=False,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user.id"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
