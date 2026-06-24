"""0004_position_template migration shape + soft-delete (T12 / US3).

Verifies the additive migration materialised the new columns + association
tables, that the level CHECK constraint is enforced, and that "deletion" is a
soft archive that preserves the row (FR-007). The migration itself is applied by
the session-scoped ``migrated_schema`` fixture (real ``alembic upgrade head``).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.asyncio


async def test_new_columns_present(db_conn: AsyncConnection) -> None:
    rows = await db_conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'position_template'"
        )
    )
    columns = {row[0] for row in rows}
    assert {"title", "jd_text", "level", "archived_at", "created_by"} <= columns


async def test_association_tables_present(db_conn: AsyncConnection) -> None:
    rows = await db_conn.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name IN ('position_template_stack', 'position_template_competency')"
        )
    )
    assert {row[0] for row in rows} == {
        "position_template_stack",
        "position_template_competency",
    }


async def test_level_check_rejects_invalid_value(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        with pytest.raises(IntegrityError):
            await db_conn.execute(
                text("INSERT INTO position_template (title, level) VALUES (:t, :l)"),
                {"t": "x", "l": "Architect"},
            )
    finally:
        await trans.rollback()


async def test_level_check_accepts_valid_value(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        new_id = (
            await db_conn.execute(
                text("INSERT INTO position_template (title, level) VALUES (:t, :l) RETURNING id"),
                {"t": "Senior Backend", "l": "Senior"},
            )
        ).scalar_one()
        assert isinstance(new_id, uuid.UUID)
    finally:
        await trans.rollback()


async def test_soft_delete_preserves_row(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        new_id = (
            await db_conn.execute(
                text("INSERT INTO position_template (title, level) VALUES (:t, :l) RETURNING id"),
                {"t": "To Archive", "l": "Middle"},
            )
        ).scalar_one()
        await db_conn.execute(
            text("UPDATE position_template SET archived_at = now() WHERE id = :id"),
            {"id": new_id},
        )
        row = (
            await db_conn.execute(
                text("SELECT archived_at FROM position_template WHERE id = :id"),
                {"id": new_id},
            )
        ).one()
        assert row[0] is not None  # archived, but the row still exists
    finally:
        await trans.rollback()
