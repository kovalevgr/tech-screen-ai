"""Rubric tree FK chain + extensions + transactional rollback (US3, US2 #4).

Validates that downstream tiers can build FKs onto a coherent rubric tree, that
the ``vector`` + ``pgcrypto`` extensions are present so future embedding/UUID
work needs no destructive migration (SC-007), and that a normal transactional
write to a non-audit table rolls back cleanly (US2 acceptance #4).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

pytestmark = pytest.mark.asyncio


async def test_full_rubric_chain_resolves(db_conn: AsyncConnection) -> None:
    """A version → stack → block → competency → {topic, level} chain inserts."""
    trans = await db_conn.begin()
    try:
        rtv = (
            await db_conn.execute(
                text("INSERT INTO rubric_tree_version (label) VALUES (:l) RETURNING id"),
                {"l": "2026-Q2"},
            )
        ).scalar_one()
        stack = (
            await db_conn.execute(
                text(
                    "INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n) RETURNING id"
                ),
                {"v": rtv, "n": "Backend Python"},
            )
        ).scalar_one()
        block = (
            await db_conn.execute(
                text(
                    "INSERT INTO competency_block "
                    "(rubric_tree_version_id, stack_id, name) "
                    "VALUES (:v, :s, :n) RETURNING id"
                ),
                {"v": rtv, "s": stack, "n": "Core"},
            )
        ).scalar_one()
        competency = (
            await db_conn.execute(
                text(
                    "INSERT INTO competency "
                    "(rubric_tree_version_id, competency_block_id, name) "
                    "VALUES (:v, :b, :n) RETURNING id"
                ),
                {"v": rtv, "b": block, "n": "Concurrency"},
            )
        ).scalar_one()
        topic = (
            await db_conn.execute(
                text(
                    "INSERT INTO topic "
                    "(rubric_tree_version_id, competency_id, name) "
                    "VALUES (:v, :c, :n) RETURNING id"
                ),
                {"v": rtv, "c": competency, "n": "asyncio"},
            )
        ).scalar_one()
        level = (
            await db_conn.execute(
                text(
                    "INSERT INTO level "
                    "(rubric_tree_version_id, competency_id, rank, descriptor) "
                    "VALUES (:v, :c, :r, :d) RETURNING id"
                ),
                {"v": rtv, "c": competency, "r": 3, "d": "Solid working knowledge"},
            )
        ).scalar_one()

        for produced in (rtv, stack, block, competency, topic, level):
            assert isinstance(produced, uuid.UUID)

        # The whole tree is addressable by version.
        count = (
            await db_conn.execute(
                text("SELECT count(*) FROM competency WHERE rubric_tree_version_id = :v"),
                {"v": rtv},
            )
        ).scalar_one()
        assert count == 1
    finally:
        await trans.rollback()


async def test_orphan_fk_is_rejected(db_conn: AsyncConnection) -> None:
    """A stack referencing a non-existent version violates the FK."""
    from sqlalchemy.exc import IntegrityError

    trans = await db_conn.begin()
    try:
        with pytest.raises(IntegrityError):
            await db_conn.execute(
                text("INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n)"),
                {"v": uuid.uuid4(), "n": "Orphan"},
            )
    finally:
        await trans.rollback()


async def test_vector_and_pgcrypto_extensions_present(
    db_conn: AsyncConnection,
) -> None:
    result = await db_conn.execute(
        text("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pgcrypto')")
    )
    assert {row[0] for row in result} == {"vector", "pgcrypto"}


async def test_insert_then_rollback_leaves_no_row(db_conn: AsyncConnection) -> None:
    """A transactional INSERT on a non-audit table is undone by rollback."""
    rtv = None
    trans = await db_conn.begin()
    try:
        rtv = (
            await db_conn.execute(
                text("INSERT INTO rubric_tree_version (label) VALUES (:l) RETURNING id"),
                {"l": "rollme"},
            )
        ).scalar_one()
        stack_id = (
            await db_conn.execute(
                text(
                    "INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n) RETURNING id"
                ),
                {"v": rtv, "n": "Ephemeral"},
            )
        ).scalar_one()
        assert isinstance(stack_id, uuid.UUID)
    finally:
        await trans.rollback()

    # After rollback, the stack row must not exist.
    async with db_conn.begin():
        remaining = (
            await db_conn.execute(
                text("SELECT count(*) FROM stack WHERE rubric_tree_version_id = :v"),
                {"v": rtv},
            )
        ).scalar_one()
    assert remaining == 0
