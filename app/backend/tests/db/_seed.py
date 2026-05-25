"""Seed helpers for the T05 DB integration tests.

Inserts a coherent FK chain (rubric tree → user → session) plus one row in each
of the six append-only tables, returning the ids tests need. INSERT is always
allowed (the §3 trigger is ``BEFORE UPDATE OR DELETE`` only), so seeding runs as
the connection's current role without needing the migrator exemption.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection


@dataclass(frozen=True)
class SeedIds:
    """Primary keys produced by :func:`seed_chain`, one per relevant table."""

    rubric_tree_version_id: uuid.UUID
    stack_id: uuid.UUID
    competency_block_id: uuid.UUID
    competency_id: uuid.UUID
    user_id: uuid.UUID
    position_template_id: uuid.UUID
    interview_session_id: uuid.UUID
    turn_trace_id: uuid.UUID
    assessment_id: uuid.UUID
    assessment_correction_id: uuid.UUID
    turn_annotation_id: uuid.UUID
    audit_log_id: uuid.UUID
    session_decision_id: uuid.UUID


async def _insert(conn: AsyncConnection, sql: str, **params: object) -> uuid.UUID:
    result = await conn.execute(text(sql), params)
    return result.scalar_one()  # type: ignore[no-any-return]


async def seed_chain(conn: AsyncConnection) -> SeedIds:
    """Insert one row in every table needed to probe the append-only set.

    Runs entirely as INSERTs (allowed under §3). The caller owns the
    transaction and is expected to roll it back so no rows persist.
    """
    rtv = await _insert(
        conn,
        "INSERT INTO rubric_tree_version (label) VALUES (:label) RETURNING id",
        label="test-version",
    )
    stack = await _insert(
        conn,
        "INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :name) RETURNING id",
        v=rtv,
        name="Backend Python",
    )
    block = await _insert(
        conn,
        "INSERT INTO competency_block (rubric_tree_version_id, stack_id, name) "
        "VALUES (:v, :s, :name) RETURNING id",
        v=rtv,
        s=stack,
        name="Core",
    )
    competency = await _insert(
        conn,
        "INSERT INTO competency (rubric_tree_version_id, competency_block_id, name) "
        "VALUES (:v, :b, :name) RETURNING id",
        v=rtv,
        b=block,
        name="Concurrency",
    )
    user = await _insert(
        conn,
        'INSERT INTO "user" (subject, role) VALUES (:subject, :role) RETURNING id',
        subject=f"sso|{uuid.uuid4()}",
        role="reviewer",
    )
    template = await _insert(
        conn,
        "INSERT INTO position_template DEFAULT VALUES RETURNING id",
    )
    session = await _insert(
        conn,
        "INSERT INTO interview_session (position_template_id) VALUES (:t) RETURNING id",
        t=template,
    )
    turn_trace = await _insert(
        conn,
        "INSERT INTO turn_trace (interview_session_id) VALUES (:s) RETURNING id",
        s=session,
    )
    assessment = await _insert(
        conn,
        "INSERT INTO assessment (interview_session_id, competency_id, score, "
        "confidence) VALUES (:s, :c, :score, :conf) RETURNING id",
        s=session,
        c=competency,
        score=3,
        conf="0.900",
    )
    correction = await _insert(
        conn,
        "INSERT INTO assessment_correction (assessment_id, corrected_score, "
        "corrected_by) VALUES (:a, :score, :u) RETURNING id",
        a=assessment,
        score=4,
        u=user,
    )
    annotation = await _insert(
        conn,
        "INSERT INTO turn_annotation (turn_trace_id, annotated_by) VALUES (:t, :u) RETURNING id",
        t=turn_trace,
        u=user,
    )
    audit = await _insert(
        conn,
        "INSERT INTO audit_log (actor_id, action, subject_hash) "
        "VALUES (:u, :action, :hash) RETURNING id",
        u=user,
        action="session.created",
        hash="deadbeef",
    )
    decision = await _insert(
        conn,
        "INSERT INTO session_decision (interview_session_id, decided_by) "
        "VALUES (:s, :u) RETURNING id",
        s=session,
        u=user,
    )
    return SeedIds(
        rubric_tree_version_id=rtv,
        stack_id=stack,
        competency_block_id=block,
        competency_id=competency,
        user_id=user,
        position_template_id=template,
        interview_session_id=session,
        turn_trace_id=turn_trace,
        assessment_id=assessment,
        assessment_correction_id=correction,
        turn_annotation_id=annotation,
        audit_log_id=audit,
        session_decision_id=decision,
    )
