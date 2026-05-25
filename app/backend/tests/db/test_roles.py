"""Role + grant + trigger shape checks (SC-003/005).

Confirms by catalog query (not by attempting mutations) that:
- both ``techscreen_app`` and ``techscreen_migrator`` roles exist,
- ``techscreen_app`` has INSERT + SELECT but lacks UPDATE + DELETE on all six
  append-only tables (``has_table_privilege``), and
- the ``reject_audit_mutation`` trigger is present on all six tables.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.asyncio

APPEND_ONLY_TABLES: tuple[str, ...] = (
    "turn_trace",
    "assessment",
    "assessment_correction",
    "turn_annotation",
    "audit_log",
    "session_decision",
)


async def test_both_roles_exist(db_conn: AsyncConnection) -> None:
    result = await db_conn.execute(
        text(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname IN ('techscreen_app', 'techscreen_migrator')"
        )
    )
    names = {row[0] for row in result}
    assert names == {"techscreen_app", "techscreen_migrator"}


async def test_roles_are_nologin(db_conn: AsyncConnection) -> None:
    result = await db_conn.execute(
        text(
            "SELECT rolname, rolcanlogin FROM pg_roles "
            "WHERE rolname IN ('techscreen_app', 'techscreen_migrator')"
        )
    )
    canlogin = {row[0]: row[1] for row in result}
    assert canlogin["techscreen_app"] is False
    assert canlogin["techscreen_migrator"] is False


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
async def test_app_role_has_insert_select_not_update_delete(
    db_conn: AsyncConnection, table: str
) -> None:
    result = await db_conn.execute(
        text(
            "SELECT "
            "has_table_privilege('techscreen_app', :t, 'INSERT'), "
            "has_table_privilege('techscreen_app', :t, 'SELECT'), "
            "has_table_privilege('techscreen_app', :t, 'UPDATE'), "
            "has_table_privilege('techscreen_app', :t, 'DELETE')"
        ),
        {"t": table},
    )
    can_insert, can_select, can_update, can_delete = result.one()
    assert can_insert is True, f"{table}: app role must keep INSERT"
    assert can_select is True, f"{table}: app role must keep SELECT"
    assert can_update is False, f"{table}: app role must NOT have UPDATE"
    assert can_delete is False, f"{table}: app role must NOT have DELETE"


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
async def test_migrator_role_retains_full_dml(db_conn: AsyncConnection, table: str) -> None:
    result = await db_conn.execute(
        text(
            "SELECT "
            "has_table_privilege('techscreen_migrator', :t, 'UPDATE'), "
            "has_table_privilege('techscreen_migrator', :t, 'DELETE')"
        ),
        {"t": table},
    )
    can_update, can_delete = result.one()
    assert can_update is True, f"{table}: migrator must keep UPDATE"
    assert can_delete is True, f"{table}: migrator must keep DELETE"


@pytest.mark.parametrize("table", APPEND_ONLY_TABLES)
async def test_reject_mutation_trigger_present(db_conn: AsyncConnection, table: str) -> None:
    result = await db_conn.execute(
        text(
            "SELECT count(*) FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = :t AND NOT t.tgisinternal "
            "AND t.tgname = :name"
        ),
        {"t": table, "name": f"{table}_no_mutation"},
    )
    assert result.scalar_one() == 1, f"{table}: append-only trigger missing"
