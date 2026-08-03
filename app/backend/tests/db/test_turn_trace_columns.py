"""Migration 0007 — the widened ``turn_trace`` and its §3 guard (T21).

DB-gated like the rest of ``tests/db/``: the session-scoped ``migrated_schema``
fixture runs the real ``alembic upgrade head``, and the whole suite skips when
no ``DATABASE_URL`` is reachable.

What is proved here:

- every column named by ``docs/contracts/turn-trace.schema.json`` exists, with
  the nullability the contract implies;
- the additive migration did NOT weaken constitution §3 — ``UPDATE`` and
  ``DELETE`` are still rejected on the widened table, including on the columns
  0007 added;
- ``session_decision`` accepts a system decision (no human actor) and records
  its reason;
- the two dark-launch flag rows exist and are ``false`` (§9).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.tests.conftest import set_role
from app.backend.tests.db._seed import seed_chain

pytestmark = pytest.mark.asyncio

#: (column, expected is_nullable) for every column the row contract names.
_EXPECTED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("id", "NO"),
    ("created_at", "NO"),
    ("interview_session_id", "YES"),
    ("turn_id", "YES"),
    ("transition", "YES"),
    ("agent", "NO"),
    ("prompt_version", "NO"),
    ("model", "NO"),
    ("model_version", "YES"),
    ("outcome", "NO"),
    ("wrapper_outcome", "YES"),
    ("attempts", "NO"),
    ("latency_ms", "NO"),
    ("input_tokens", "NO"),
    ("output_tokens", "NO"),
    ("cost_usd", "NO"),
    ("prompt_sha", "NO"),
    ("error_message", "YES"),
    ("system_prompt", "NO"),
    ("user_payload", "NO"),
    ("response_text", "NO"),
    ("parsed", "YES"),
)


async def test_turn_trace_has_every_contract_column(db_conn: AsyncConnection) -> None:
    rows = (
        await db_conn.execute(
            text(
                "SELECT column_name, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'turn_trace'"
            )
        )
    ).all()
    actual = {name: nullable for name, nullable in rows}

    assert actual == dict(_EXPECTED_COLUMNS)


async def test_cost_usd_is_numeric_12_6(db_conn: AsyncConnection) -> None:
    """Money is NUMERIC end to end — never a float (row contract, §12)."""
    row = (
        await db_conn.execute(
            text(
                "SELECT data_type, numeric_precision, numeric_scale "
                "FROM information_schema.columns "
                "WHERE table_name = 'turn_trace' AND column_name = 'cost_usd'"
            )
        )
    ).one()

    assert row == ("numeric", 12, 6)


async def test_a_full_contract_row_inserts(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        inserted = (
            await db_conn.execute(
                text(
                    "INSERT INTO turn_trace (interview_session_id, turn_id, transition, agent, "
                    "prompt_version, model, model_version, outcome, wrapper_outcome, attempts, "
                    "latency_ms, input_tokens, output_tokens, cost_usd, prompt_sha, "
                    "error_message, system_prompt, user_payload, response_text, parsed) "
                    "VALUES (:sid, :tid, CAST(:tr AS JSONB), 'interviewer', 'v0001', "
                    "'gemini-2.5-flash', 'gemini-2.5-flash-001', 'ok', 'accepted', 1, 42, 10, 20, "
                    "0.000123, :sha, NULL, 'SYSTEM', 'PAYLOAD', 'RAW', CAST(:p AS JSONB)) "
                    "RETURNING cost_usd, wrapper_outcome, transition"
                ),
                {
                    "sid": ids.interview_session_id,
                    "tid": uuid.uuid4(),
                    "tr": '{"phase": "tech", "state_before_sha": "a", "state_after_sha": "b"}',
                    "sha": "0" * 64,
                    "p": '{"utterance": "текст"}',
                },
            )
        ).one()

        assert inserted[0] == Decimal("0.000123")
        assert inserted[1] == "accepted"
        assert inserted[2]["phase"] == "tech"
    finally:
        await trans.rollback()


@pytest.mark.parametrize("column", ["user_payload", "cost_usd", "wrapper_outcome"])
async def test_append_only_still_blocks_update_on_new_columns(
    db_conn: AsyncConnection, column: str
) -> None:
    """§3 survived the widening: the app role may not UPDATE the new columns."""
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        nested = await db_conn.begin_nested()
        await db_conn.execute(text('SET ROLE "techscreen_app"'))
        with pytest.raises(DBAPIError) as err:
            await db_conn.execute(
                text(f"UPDATE turn_trace SET {column} = {column} WHERE id = :id"),
                {"id": ids.turn_trace_id},
            )
        assert "permission denied" in str(err.value).lower()
        await nested.rollback()
    finally:
        await trans.rollback()


async def test_append_only_trigger_still_fires_on_the_widened_table(
    db_conn: AsyncConnection,
) -> None:
    """The superuser bypasses the REVOKE, so this isolates the trigger layer."""
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        nested = await db_conn.begin_nested()
        with pytest.raises(DBAPIError) as err:
            await db_conn.execute(
                text("UPDATE turn_trace SET response_text = 'tampered' WHERE id = :id"),
                {"id": ids.turn_trace_id},
            )
        message = str(err.value)
        assert "append-only:" in message
        assert "not allowed on turn_trace" in message
        await nested.rollback()

        nested = await db_conn.begin_nested()
        with pytest.raises(DBAPIError) as delete_err:
            await db_conn.execute(
                text("DELETE FROM turn_trace WHERE id = :id"), {"id": ids.turn_trace_id}
            )
        assert "append-only:" in str(delete_err.value)
        await nested.rollback()
    finally:
        await trans.rollback()


async def test_session_decision_accepts_a_system_decision(db_conn: AsyncConnection) -> None:
    """No human actor, and the reason is recorded (T21 cost-ceiling path)."""
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        async with set_role(db_conn, "techscreen_app"):
            row = (
                await db_conn.execute(
                    text(
                        "INSERT INTO session_decision (interview_session_id, decided_by, reason) "
                        "VALUES (:sid, NULL, 'cost_ceiling') RETURNING decided_by, reason"
                    ),
                    {"sid": ids.interview_session_id},
                )
            ).one()

        assert row == (None, "cost_ceiling")
    finally:
        await trans.rollback()


async def test_interview_session_has_a_nullable_dev_transcript(db_conn: AsyncConnection) -> None:
    row = (
        await db_conn.execute(
            text(
                "SELECT is_nullable, data_type FROM information_schema.columns "
                "WHERE table_name = 'interview_session' AND column_name = 'dev_transcript'"
            )
        )
    ).one()

    assert row == ("YES", "jsonb")


@pytest.mark.parametrize("flag", ["enforce_session_cost_ceiling", "enable_live_orchestrator"])
async def test_the_t21_flags_are_seeded_disabled(db_conn: AsyncConnection, flag: str) -> None:
    """§9 dark launch: both flags exist and both start false."""
    enabled = (
        await db_conn.execute(text("SELECT enabled FROM feature_flag WHERE name = :n"), {"n": flag})
    ).scalar_one()

    assert enabled is False
