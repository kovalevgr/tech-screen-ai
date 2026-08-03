"""Load/save of ``interview_session.session_state`` (contract §9).

The only module in :mod:`app.backend.orchestrator` that touches the database —
the core (:mod:`app.backend.orchestrator.state_machine`) stays a pure
function, and everything durable happens here or in the shell (T22).

Two contract points this module owns:

- **In-place update is correct.** ``interview_session`` is NOT one of the six
  append-only audit tables (constitution §3): ``session_state`` is mutable
  working state. The audit trail is ``turn_trace`` + the T21 transition
  records, never this column.
- **State-schema versions fail loudly.** Every persisted document carries
  ``state_schema_version``; a document written by a different version is a
  :class:`StateSchemaVersionError`, never a silent best-effort migration
  (plan.md § Risks).

Data access is SQLAlchemy Core over an ``AsyncConnection`` — the same style
as :mod:`app.backend.services.rubric_snapshot`, which owns the sibling
``rubric_snapshot`` column.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.orchestrator.state_machine import SessionState


class SessionStatePersistenceError(Exception):
    """Base for every failure raised by this module."""


class StateSchemaVersionError(SessionStatePersistenceError):
    """A stored ``session_state`` was written by a different state schema version.

    Fails loudly on purpose (contract §9 / plan.md § Risks): silently
    coercing an old document into the current shape would corrupt a live
    interview. Resolution is an explicit, reviewed migration step.
    """


class SessionStateDecodeError(SessionStatePersistenceError):
    """A stored ``session_state`` is not a valid :class:`SessionState` document."""


class InterviewSessionNotFound(SessionStatePersistenceError):
    """No ``interview_session`` row exists for the given id."""


def encode_session_state(state: SessionState) -> dict[str, Any]:
    """Serialise a state to the JSON-object form stored in the column.

    Args:
        state: The state produced by the last transition.

    Returns:
        A JSON-mode dict (UUIDs and timestamps as strings) that
        :func:`decode_session_state` round-trips losslessly.
    """
    return state.model_dump(mode="json")


def decode_session_state(raw: object, *, expected_version: int) -> SessionState:
    """Parse a stored document back into a typed state.

    Args:
        raw: The JSONB payload as read from the column.
        expected_version: ``OrchestratorConfig.state_schema_version``.

    Returns:
        The rehydrated :class:`SessionState`.

    Raises:
        StateSchemaVersionError: The document's ``state_schema_version``
            differs from ``expected_version``, or is missing/not an int.
        SessionStateDecodeError: The document is not a mapping, or does not
            satisfy the :class:`SessionState` shape.
    """
    if not isinstance(raw, dict):
        raise SessionStateDecodeError(
            f"session_state must be a JSON object, got {type(raw).__name__}"
        )
    stored_version = raw.get("state_schema_version")
    if not isinstance(stored_version, int) or isinstance(stored_version, bool):
        raise StateSchemaVersionError(
            f"session_state carries no integer state_schema_version (got {stored_version!r})"
        )
    if stored_version != expected_version:
        raise StateSchemaVersionError(
            f"session_state schema version {stored_version} != expected {expected_version}; "
            "an explicit migration is required (no silent upgrade)"
        )
    try:
        return SessionState.model_validate(raw)
    except ValidationError as exc:
        raise SessionStateDecodeError(f"stored session_state is not a valid state: {exc}") from exc


async def load_session_state(
    conn: AsyncConnection,
    interview_session_id: uuid.UUID,
    *,
    expected_version: int,
) -> SessionState | None:
    """Read the orchestrator state for a session.

    Args:
        conn: An open async connection.
        interview_session_id: The session to read.
        expected_version: ``OrchestratorConfig.state_schema_version``.

    Returns:
        The rehydrated state, or ``None`` when the session has not started
        yet (the column is NULL).

    Raises:
        InterviewSessionNotFound: No row with that id.
        StateSchemaVersionError: See :func:`decode_session_state`.
        SessionStateDecodeError: See :func:`decode_session_state`.
    """
    row = (
        await conn.execute(
            text("SELECT session_state FROM interview_session WHERE id = :sid"),
            {"sid": interview_session_id},
        )
    ).first()
    if row is None:
        raise InterviewSessionNotFound(f"interview_session {interview_session_id} does not exist")
    stored: Any = row[0]
    if stored is None:
        return None
    return decode_session_state(stored, expected_version=expected_version)


async def save_session_state(
    conn: AsyncConnection,
    interview_session_id: uuid.UUID,
    state: SessionState,
) -> None:
    """Write the orchestrator state for a session (in-place update, §9).

    The shell calls this after every transition, before issuing the wrapper
    calls the commands describe, so a crash resumes at the last consistent
    point (contract §9, spec Clarification 4).

    Args:
        conn: An open async connection.
        interview_session_id: The session to update.
        state: The state produced by the transition.

    Raises:
        InterviewSessionNotFound: No row with that id.
    """
    result = await conn.execute(
        text("UPDATE interview_session SET session_state = CAST(:state AS JSONB) WHERE id = :sid"),
        {"state": json.dumps(encode_session_state(state)), "sid": interview_session_id},
    )
    if result.rowcount == 0:
        raise InterviewSessionNotFound(f"interview_session {interview_session_id} does not exist")
