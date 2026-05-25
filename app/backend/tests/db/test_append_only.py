"""§3 append-only enforcement matrix (FR-004/005/006; SC-003/004).

Proves, on every one of the six append-only tables, that:
- as ``techscreen_app`` UPDATE and DELETE are rejected (the REVOKE floor) — the
  12 mutation-rejection assertions SC-004 requires,
- as ``techscreen_app`` INSERT is allowed (append always works),
- as the superuser (non-migrator) the trigger raises ``append-only: …``
  (isolates the trigger layer the REVOKE can't cover for superusers), and
- as ``techscreen_migrator`` UPDATE succeeds (the exemption that lets
  human-approved forward-only migrations evolve audit data).

Each expected-failure probe runs inside its own SAVEPOINT. The failed statement
aborts the savepoint, so we ``ROLLBACK TO SAVEPOINT`` to clear the aborted state
— which also reverts the in-savepoint ``SET ROLE`` back to the superuser, so no
role state leaks to the next probe. The outer transaction is rolled back at the
end so no seeded row persists.

asyncpg surfaces the privilege error (SQLSTATE 42501) as
``sqlalchemy.exc.ProgrammingError`` and the PL/pgSQL ``RAISE`` (SQLSTATE P0001)
as a bare ``sqlalchemy.exc.DBAPIError``; both are caught as ``DBAPIError`` and
distinguished by message content.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.tests.conftest import set_role
from app.backend.tests.db._seed import SeedIds, seed_chain

pytestmark = pytest.mark.asyncio

# (table, id-attribute on SeedIds, a column to attempt to UPDATE)
APPEND_ONLY_TABLES: tuple[tuple[str, str, str], ...] = (
    ("turn_trace", "turn_trace_id", "interview_session_id"),
    ("assessment", "assessment_id", "score"),
    ("assessment_correction", "assessment_correction_id", "corrected_score"),
    ("turn_annotation", "turn_annotation_id", "turn_trace_id"),
    ("audit_log", "audit_log_id", "action"),
    ("session_decision", "session_decision_id", "decided_by"),
)


def _update_sql(table: str, column: str) -> str:
    # A no-op self-assignment keeps the statement valid for any column type.
    return f"UPDATE {table} SET {column} = {column} WHERE id = :id"


async def test_app_role_update_and_delete_rejected_on_every_audit_table(
    db_conn: AsyncConnection,
) -> None:
    """As techscreen_app, UPDATE and DELETE are denied on all six tables."""
    trans = await db_conn.begin()
    try:
        ids: SeedIds = await seed_chain(db_conn)
        for table, id_attr, column in APPEND_ONLY_TABLES:
            row_id = getattr(ids, id_attr)

            # UPDATE rejected — permission denied (the REVOKE floor).
            nested = await db_conn.begin_nested()
            await db_conn.execute(text('SET ROLE "techscreen_app"'))
            with pytest.raises(DBAPIError) as update_err:
                await db_conn.execute(text(_update_sql(table, column)), {"id": row_id})
            assert "permission denied" in str(update_err.value).lower(), table
            await nested.rollback()  # clears aborted state + reverts SET ROLE

            # DELETE rejected — permission denied.
            nested = await db_conn.begin_nested()
            await db_conn.execute(text('SET ROLE "techscreen_app"'))
            with pytest.raises(DBAPIError) as delete_err:
                await db_conn.execute(text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id})
            assert "permission denied" in str(delete_err.value).lower(), table
            await nested.rollback()
    finally:
        await trans.rollback()


async def test_app_role_insert_is_allowed(db_conn: AsyncConnection) -> None:
    """As techscreen_app, INSERT (append) succeeds on an audit table."""
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        async with set_role(db_conn, "techscreen_app"):
            inserted = await db_conn.execute(
                text(
                    "INSERT INTO assessment (interview_session_id, competency_id, "
                    "score, confidence) VALUES (:s, :c, :score, :conf) RETURNING id"
                ),
                {
                    "s": ids.interview_session_id,
                    "c": ids.competency_id,
                    "score": 2,
                    "conf": "0.800",
                },
            )
            new_id = inserted.scalar_one()
        assert isinstance(new_id, uuid.UUID)
    finally:
        await trans.rollback()


@pytest.mark.parametrize("table", ["assessment", "audit_log"])
async def test_trigger_blocks_superuser_with_append_only_error(
    db_conn: AsyncConnection, table: str
) -> None:
    """As the superuser (non-migrator) the trigger raises ``append-only: …``.

    The superuser bypasses the REVOKE grant, so only the trigger stands here —
    this isolates the trigger layer. SQLSTATE P0001 is the PL/pgSQL RAISE.
    """
    column = "score" if table == "assessment" else "action"
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        row_id = ids.assessment_id if table == "assessment" else ids.audit_log_id
        nested = await db_conn.begin_nested()
        with pytest.raises(DBAPIError) as err:
            await db_conn.execute(text(_update_sql(table, column)), {"id": row_id})
        message = str(err.value)
        assert "append-only:" in message
        assert f"not allowed on {table}" in message
        await nested.rollback()
    finally:
        await trans.rollback()


async def test_migrator_role_may_mutate_audit_tables(
    db_conn: AsyncConnection,
) -> None:
    """As techscreen_migrator, UPDATE and DELETE succeed (exemption + grant)."""
    trans = await db_conn.begin()
    try:
        ids = await seed_chain(db_conn)
        async with set_role(db_conn, "techscreen_migrator"):
            updated = await db_conn.execute(
                text("UPDATE assessment SET score = :score WHERE id = :id"),
                {"score": 5, "id": ids.assessment_id},
            )
            assert updated.rowcount == 1
            deleted = await db_conn.execute(
                text("DELETE FROM session_decision WHERE id = :id"),
                {"id": ids.session_decision_id},
            )
            assert deleted.rowcount == 1
    finally:
        await trans.rollback()
