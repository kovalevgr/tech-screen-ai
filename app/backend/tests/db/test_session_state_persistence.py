"""``interview_session.session_state`` — migration shape + real round trip (T20).

DB-gated like the rest of ``tests/db/``: the session-scoped ``migrated_schema``
fixture runs the real ``alembic upgrade head``, and the whole suite skips when
no ``DATABASE_URL`` is reachable.

Contract §9 points proved here:

- the column exists, is JSONB, and is NULLABLE (a session that has not started
  has no state);
- a state written by the machine survives the JSONB round trip byte-for-byte;
- writing again overwrites in place — ``interview_session`` is deliberately NOT
  one of the six append-only tables (constitution §3), so no trigger blocks it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.orchestrator.config import load_orchestrator_config
from app.backend.orchestrator.persistence import (
    InterviewSessionNotFound,
    load_session_state,
    save_session_state,
)
from app.backend.orchestrator.state_machine import (
    CandidateTurnReceived,
    OperatorAbort,
    Phase,
    SessionStarted,
    initial_state,
    transition,
)
from app.backend.tests.orchestrator._builders import (
    NODE_A,
    T0,
    at,
    complete_assessment,
    deliver_reply,
    make_plan,
    turn_uuid,
)

pytestmark = pytest.mark.asyncio


async def _new_session(conn: AsyncConnection) -> uuid.UUID:
    """Insert a bare ``interview_session`` row and return its id."""
    result = await conn.execute(text("INSERT INTO interview_session DEFAULT VALUES RETURNING id"))
    return result.scalar_one()  # type: ignore[no-any-return]  # RETURNING id is a UUID


async def test_session_state_column_is_nullable_jsonb(db_conn: AsyncConnection) -> None:
    row = (
        await db_conn.execute(
            text(
                "SELECT is_nullable, data_type, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'interview_session' AND column_name = 'session_state'"
            )
        )
    ).one()
    is_nullable, data_type, column_default = row

    assert is_nullable == "YES"
    assert data_type == "jsonb"
    assert column_default is None


async def test_a_session_without_state_loads_as_none(db_conn: AsyncConnection) -> None:
    config = load_orchestrator_config()
    trans = await db_conn.begin()
    try:
        session_id = await _new_session(db_conn)

        loaded = await load_session_state(
            db_conn, session_id, expected_version=config.state_schema_version
        )

        assert loaded is None
    finally:
        await trans.rollback()


async def test_a_transition_state_round_trips_through_postgres(
    db_conn: AsyncConnection,
) -> None:
    config = load_orchestrator_config()
    trans = await db_conn.begin()
    try:
        session_id = await _new_session(db_conn)
        state = initial_state(session_id=session_id, plan_input=make_plan(), config=config)
        started = transition(state, SessionStarted(now=T0), config).new_state
        tech = transition(
            started,
            CandidateTurnReceived(turn_id=turn_uuid(0), text="Готовий", now=T0),
            config,
        ).new_state
        answered = transition(
            deliver_reply(tech, config, now=T0),
            CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
            config,
        ).new_state
        scored = complete_assessment(
            answered,
            config,
            turn_id=turn_uuid(1),
            competency_focus=NODE_A,
            levels=((NODE_A, 4, 0.85),),
            now=at(minutes=1, seconds=5),
        )

        await save_session_state(db_conn, session_id, scored)
        loaded = await load_session_state(
            db_conn, session_id, expected_version=config.state_schema_version
        )

        assert loaded == scored
        assert loaded is not None
        assert loaded.tech.coverage[NODE_A].best_level == 4
        assert loaded.pending_command == scored.pending_command
    finally:
        await trans.rollback()


async def test_saving_twice_overwrites_in_place(db_conn: AsyncConnection) -> None:
    """§3 does not cover ``interview_session``; working state is mutable (§9)."""
    config = load_orchestrator_config()
    trans = await db_conn.begin()
    try:
        session_id = await _new_session(db_conn)
        first = initial_state(session_id=session_id, plan_input=make_plan(), config=config)
        second = transition(first, SessionStarted(now=T0), config).new_state
        third = transition(second, OperatorAbort(now=at(minutes=1)), config).new_state

        await save_session_state(db_conn, session_id, first)
        await save_session_state(db_conn, session_id, second)
        await save_session_state(db_conn, session_id, third)

        loaded = await load_session_state(
            db_conn, session_id, expected_version=config.state_schema_version
        )
        row_count = (
            await db_conn.execute(
                text("SELECT count(*) FROM interview_session WHERE id = :sid"), {"sid": session_id}
            )
        ).scalar_one()

        assert loaded is not None
        assert loaded.phase is Phase.ABORTED
        assert row_count == 1
    finally:
        await trans.rollback()


async def test_an_unknown_session_id_raises(db_conn: AsyncConnection) -> None:
    config = load_orchestrator_config()
    missing = uuid.UUID("00000000-0000-5000-8000-000000000000")

    with pytest.raises(InterviewSessionNotFound):
        await load_session_state(db_conn, missing, expected_version=config.state_schema_version)


async def test_saving_to_an_unknown_session_id_raises(db_conn: AsyncConnection) -> None:
    config = load_orchestrator_config()
    missing = uuid.UUID("00000000-0000-5000-8000-000000000001")
    state = initial_state(session_id=missing, plan_input=make_plan(), config=config)

    trans = await db_conn.begin()
    try:
        with pytest.raises(InterviewSessionNotFound):
            await save_session_state(db_conn, missing, state)
    finally:
        await trans.rollback()
