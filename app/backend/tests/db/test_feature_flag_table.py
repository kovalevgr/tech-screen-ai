"""§3 carve-out positive test for ``feature_flag`` (T05a / FR-013 / SC-009).

The ``feature_flag`` table is INTENTIONALLY excluded from the §3 append-only
guarantee that protects the six audit tables. This test fails loudly if any
future change extends audit-table protections to it.

Asserts:
- the table exists after ``alembic upgrade head``;
- no ``reject_audit_mutation`` trigger is wired on it;
- the ``techscreen_app`` role has UPDATE and DELETE privileges (the audit
  tables do NOT);
- end-to-end as ``techscreen_app``: INSERT → UPDATE → DELETE all succeed.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.tests.conftest import set_role

pytestmark = pytest.mark.asyncio


async def test_table_exists_after_migration(db_conn: AsyncConnection) -> None:
    """``feature_flag`` is materialised by the baseline migrations."""
    row = await db_conn.execute(
        text(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_name = 'feature_flag'"
        )
    )
    assert row.scalar_one() == 1


async def test_no_reject_audit_mutation_trigger_on_feature_flag(
    db_conn: AsyncConnection,
) -> None:
    """No ``reject_audit_mutation`` trigger may live on ``feature_flag``.

    Future contributor checkpoint: if you find yourself adding the
    audit-table guard here, stop and re-read FR-013 / the migration
    docstring. The carve-out is the whole point.
    """
    result = await db_conn.execute(
        text(
            "SELECT tgname FROM pg_trigger "
            "WHERE tgrelid = 'feature_flag'::regclass AND NOT tgisinternal"
        )
    )
    trigger_names = [row[0] for row in result.fetchall()]
    assert not any("reject_audit_mutation" in t for t in trigger_names), trigger_names
    # The notify trigger and the updated_at touch trigger SHOULD be present.
    assert any("notify" in t for t in trigger_names), trigger_names


async def test_app_role_has_update_and_delete_privileges(
    db_conn: AsyncConnection,
) -> None:
    """``techscreen_app`` retains full DML on this table (unlike the audit set)."""
    for op_name in ("INSERT", "SELECT", "UPDATE", "DELETE"):
        granted = await db_conn.execute(
            text("SELECT has_table_privilege(:role, :table, :op)"),
            {"role": "techscreen_app", "table": "feature_flag", "op": op_name},
        )
        assert granted.scalar_one() is True, f"{op_name} should be granted on feature_flag"


async def test_app_role_can_insert_update_and_delete_end_to_end(
    db_conn: AsyncConnection,
) -> None:
    """End-to-end SC-009 — the audit-set guard would block these; this table allows them."""
    flag_name = f"sc009_{uuid.uuid4().hex[:8]}"
    trans = await db_conn.begin()
    try:
        async with set_role(db_conn, "techscreen_app"):
            inserted = await db_conn.execute(
                text(
                    "INSERT INTO feature_flag (name, owner) VALUES (:name, :owner) RETURNING name"
                ),
                {"name": flag_name, "owner": "@sc009-test"},
            )
            assert inserted.scalar_one() == flag_name
            updated = await db_conn.execute(
                text("UPDATE feature_flag SET enabled = true WHERE name = :name"),
                {"name": flag_name},
            )
            assert updated.rowcount == 1
            deleted = await db_conn.execute(
                text("DELETE FROM feature_flag WHERE name = :name"),
                {"name": flag_name},
            )
            assert deleted.rowcount == 1
    finally:
        await trans.rollback()
