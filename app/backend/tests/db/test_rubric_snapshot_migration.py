"""0005_rubric_snapshot migration shape + seed compatibility (T15 / §4).

The migration is applied by the session-scoped ``migrated_schema`` fixture
(real ``alembic upgrade head``).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.asyncio


async def test_rubric_snapshot_column_is_not_null_with_jsonb_default(
    db_conn: AsyncConnection,
) -> None:
    row = (
        await db_conn.execute(
            text(
                "SELECT is_nullable, data_type, column_default "
                "FROM information_schema.columns "
                "WHERE table_name = 'interview_session' AND column_name = 'rubric_snapshot'"
            )
        )
    ).one()
    is_nullable, data_type, column_default = row
    assert is_nullable == "NO"
    assert data_type == "jsonb"
    assert "jsonb" in (column_default or "").lower()


async def test_placeholder_insert_without_snapshot_still_works(db_conn: AsyncConnection) -> None:
    """The transitional default keeps the T05-style placeholder insert valid."""
    trans = await db_conn.begin()
    try:
        sid = (
            await db_conn.execute(text("INSERT INTO interview_session DEFAULT VALUES RETURNING id"))
        ).scalar_one()
        stored = (
            await db_conn.execute(
                text("SELECT rubric_snapshot::text FROM interview_session WHERE id = :s"),
                {"s": sid},
            )
        ).scalar_one()
        assert stored == "{}"
    finally:
        await trans.rollback()
