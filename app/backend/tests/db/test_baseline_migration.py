"""Migration round-trip: up / idempotent re-up / down empties (SC-001/002/006).

These tests shell out to the real ``alembic`` CLI (same path CI uses) so they
exercise the actual migration, not the model metadata. The downgrade test
restores the schema to ``head`` on exit so the rest of the DB suite — which
relies on the session-scoped migrated schema — still sees a populated database.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.asyncio

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]

EXPECTED_TABLES: frozenset[str] = frozenset(
    {
        "rubric_tree_version",
        "stack",
        "competency_block",
        "competency",
        "topic",
        "level",
        "user",
        "position_template",
        "interview_session",
        "interview_plan",
        "turn_trace",
        "assessment",
        "assessment_correction",
        "turn_annotation",
        "audit_log",
        "session_decision",
    }
)


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell
        ["alembic", *args],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result


async def _public_table_names(conn: AsyncConnection) -> set[str]:
    result = await conn.execute(
        text(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'alembic_version'"
        )
    )
    return {row[0] for row in result}


async def test_upgrade_creates_all_sixteen_tables(
    db_conn: AsyncConnection, migrated_schema: str
) -> None:
    assert await _public_table_names(db_conn) == set(EXPECTED_TABLES)


async def test_extensions_and_roles_present_after_upgrade(
    db_conn: AsyncConnection, migrated_schema: str
) -> None:
    extensions = await db_conn.execute(
        text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pgcrypto')")
    )
    assert {row[0] for row in extensions} == {"vector", "pgcrypto"}

    roles = await db_conn.execute(
        text(
            "SELECT rolname FROM pg_roles "
            "WHERE rolname IN ('techscreen_app', 'techscreen_migrator')"
        )
    )
    assert {row[0] for row in roles} == {"techscreen_app", "techscreen_migrator"}


async def test_second_upgrade_is_idempotent(migrated_schema: str) -> None:
    """A re-run of ``upgrade head`` on an initialised DB must succeed (SC-006)."""
    result = _alembic("upgrade", "head")
    assert result.returncode == 0, f"second upgrade failed:\n{result.stdout}\n{result.stderr}"


async def test_downgrade_base_then_upgrade_head_round_trip(
    db_engine: object, migrated_schema: str
) -> None:
    """``downgrade base`` empties the DB; ``upgrade head`` restores it (SC-002)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    down = _alembic("downgrade", "base")
    assert down.returncode == 0, f"downgrade failed:\n{down.stdout}\n{down.stderr}"

    # A fresh engine because downgrade dropped/changed objects out from under
    # any cached connection state.
    engine = create_async_engine(migrated_schema)
    try:
        async with engine.connect() as conn:
            remaining = await _public_table_names(conn)
            assert remaining == set(), f"downgrade left orphaned tables: {remaining}"
            roles = await conn.execute(
                text(
                    "SELECT rolname FROM pg_roles WHERE rolname IN "
                    "('techscreen_app', 'techscreen_migrator')"
                )
            )
            assert {row[0] for row in roles} == set(), "downgrade left roles behind"
    finally:
        await engine.dispose()

    # Restore so the rest of the DB suite still sees the schema.
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, f"restore upgrade failed:\n{up.stdout}\n{up.stderr}"
