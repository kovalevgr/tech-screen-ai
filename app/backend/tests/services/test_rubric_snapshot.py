"""snapshot_rubric + the §4 immutability invariant (T15).

Each test seeds inside a transaction that is rolled back, so nothing persists.
"""

from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.services.rubric_snapshot import (
    RubricSnapshotError,
    freeze_session_rubric,
    snapshot_rubric,
)

pytestmark = pytest.mark.asyncio


async def _seed_version(conn: AsyncConnection) -> dict[str, uuid.UUID]:
    """Seed a one-of-each rubric version; return the ids."""
    rtv = (
        await conn.execute(
            text(
                "INSERT INTO rubric_tree_version (label, payload_hash) VALUES (:l, :h) RETURNING id"
            ),
            {"l": "2026-Q2", "h": uuid.uuid4().hex + uuid.uuid4().hex},
        )
    ).scalar_one()
    stack = (
        await conn.execute(
            text("INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n) RETURNING id"),
            {"v": rtv, "n": "Backend Python"},
        )
    ).scalar_one()
    block = (
        await conn.execute(
            text(
                "INSERT INTO competency_block (rubric_tree_version_id, stack_id, name, position) "
                "VALUES (:v, :s, :n, :p) RETURNING id"
            ),
            {"v": rtv, "s": stack, "n": "Core", "p": 1},
        )
    ).scalar_one()
    comp = (
        await conn.execute(
            text(
                "INSERT INTO competency (rubric_tree_version_id, competency_block_id, name) "
                "VALUES (:v, :b, :n) RETURNING id"
            ),
            {"v": rtv, "b": block, "n": "Concurrency"},
        )
    ).scalar_one()
    await conn.execute(
        text("INSERT INTO topic (rubric_tree_version_id, competency_id, name) VALUES (:v, :c, :n)"),
        {"v": rtv, "c": comp, "n": "asyncio"},
    )
    await conn.execute(
        text(
            "INSERT INTO level (rubric_tree_version_id, competency_id, rank, descriptor) "
            "VALUES (:v, :c, :r, :d)"
        ),
        {"v": rtv, "c": comp, "r": 3, "d": "Solid working knowledge"},
    )
    return {"version": rtv, "stack": stack, "block": block, "competency": comp}


async def test_snapshot_reproduces_full_tree(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        ids = await _seed_version(db_conn)
        snap = await snapshot_rubric(db_conn, ids["version"])

        assert snap.rubric_tree_version_id == ids["version"]
        assert snap.label == "2026-Q2"
        assert [s.name for s in snap.stacks] == ["Backend Python"]
        block = snap.stacks[0].competency_blocks[0]
        assert block.name == "Core"
        assert block.position == 1
        competency = block.competencies[0]
        assert competency.name == "Concurrency"
        assert [t.name for t in competency.topics] == ["asyncio"]
        assert [(level.rank, level.descriptor) for level in competency.levels] == [
            (3, "Solid working knowledge")
        ]
    finally:
        await trans.rollback()


async def test_snapshot_is_self_contained_json(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        ids = await _seed_version(db_conn)
        snap = await snapshot_rubric(db_conn, ids["version"])
        dumped = snap.model_dump(mode="json")
        # Fully JSON-serializable and carries copied values (names), not just refs.
        text_form = json.dumps(dumped)
        assert "Backend Python" in text_form
        assert "Concurrency" in text_form
        assert "asyncio" in text_form
    finally:
        await trans.rollback()


async def test_snapshot_unknown_version_raises(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        with pytest.raises(RubricSnapshotError, match="does not exist"):
            await snapshot_rubric(db_conn, uuid.uuid4())
    finally:
        await trans.rollback()


async def test_snapshot_is_immutable_against_rubric_edits(db_conn: AsyncConnection) -> None:
    """§4: a rubric edit after capture never changes a session's stored snapshot."""
    trans = await db_conn.begin()
    try:
        ids = await _seed_version(db_conn)
        session_id = (
            await db_conn.execute(text("INSERT INTO interview_session DEFAULT VALUES RETURNING id"))
        ).scalar_one()

        await freeze_session_rubric(db_conn, session_id, ids["version"])
        captured = json.loads(
            (
                await db_conn.execute(
                    text("SELECT rubric_snapshot::text FROM interview_session WHERE id = :s"),
                    {"s": session_id},
                )
            ).scalar_one()
        )
        assert captured["stacks"][0]["name"] == "Backend Python"

        # Mutate the live tree three ways.
        await db_conn.execute(
            text("UPDATE stack SET name = :n WHERE id = :s"),
            {"n": "RENAMED STACK", "s": ids["stack"]},
        )
        await db_conn.execute(
            text(
                "INSERT INTO competency (rubric_tree_version_id, competency_block_id, name) "
                "VALUES (:v, :b, :n)"
            ),
            {"v": ids["version"], "b": ids["block"], "n": "Brand New Competency"},
        )
        await db_conn.execute(
            text("INSERT INTO rubric_tree_version (label, payload_hash) VALUES (:l, :h)"),
            {"l": "2026-Q3", "h": uuid.uuid4().hex + uuid.uuid4().hex},
        )

        after = json.loads(
            (
                await db_conn.execute(
                    text("SELECT rubric_snapshot::text FROM interview_session WHERE id = :s"),
                    {"s": session_id},
                )
            ).scalar_one()
        )
        assert after == captured  # the stored snapshot did not change
    finally:
        await trans.rollback()
