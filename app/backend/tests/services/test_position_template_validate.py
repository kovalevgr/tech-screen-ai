"""Stateful (DB-backed) validation rules for Position Templates (T12 / US1).

Exercises validate_position_template against a real rubric tree: stack must
exist (FR-003), competency must exist and belong to a selected stack (FR-006).
Each test seeds inside a transaction that is rolled back, so no rows persist.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.schemas.position_template import PositionLevel, PositionTemplateCreate
from app.backend.services.position_template import (
    PositionTemplateValidationError,
    validate_position_template,
)

pytestmark = pytest.mark.asyncio


async def _seed_stack_with_competency(
    conn: AsyncConnection, stack_name: str = "Backend Python", comp_name: str = "Concurrency"
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert rubric_tree_version → stack → competency_block → competency."""
    # payload_hash carries a UNIQUE constraint (T08 / 0003) with a '' default, so
    # seeding two versions in one transaction needs a distinct hash per version.
    rtv = (
        await conn.execute(
            text(
                "INSERT INTO rubric_tree_version (label, payload_hash) VALUES (:l, :h) RETURNING id"
            ),
            {"l": f"t12-{uuid.uuid4()}", "h": uuid.uuid4().hex + uuid.uuid4().hex},
        )
    ).scalar_one()
    stack = (
        await conn.execute(
            text("INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n) RETURNING id"),
            {"v": rtv, "n": stack_name},
        )
    ).scalar_one()
    block = (
        await conn.execute(
            text(
                "INSERT INTO competency_block (rubric_tree_version_id, stack_id, name) "
                "VALUES (:v, :s, :n) RETURNING id"
            ),
            {"v": rtv, "s": stack, "n": "Core"},
        )
    ).scalar_one()
    comp = (
        await conn.execute(
            text(
                "INSERT INTO competency (rubric_tree_version_id, competency_block_id, name) "
                "VALUES (:v, :b, :n) RETURNING id"
            ),
            {"v": rtv, "b": block, "n": comp_name},
        )
    ).scalar_one()
    return stack, comp


def _payload(stack_ids: list[uuid.UUID], competency_ids: list[uuid.UUID]) -> PositionTemplateCreate:
    return PositionTemplateCreate(
        title="Role",
        level=PositionLevel.MIDDLE,
        stack_ids=stack_ids,
        competency_ids=competency_ids,
    )


async def test_valid_selection_passes(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        stack, comp = await _seed_stack_with_competency(db_conn)
        await validate_position_template(db_conn, _payload([stack], [comp]))  # no raise
    finally:
        await trans.rollback()


async def test_unknown_stack_rejected(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        _, comp = await _seed_stack_with_competency(db_conn)
        with pytest.raises(PositionTemplateValidationError, match="unknown stack"):
            await validate_position_template(db_conn, _payload([uuid.uuid4()], [comp]))
    finally:
        await trans.rollback()


async def test_unknown_competency_rejected(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        stack, _ = await _seed_stack_with_competency(db_conn)
        with pytest.raises(PositionTemplateValidationError, match="unknown competency"):
            await validate_position_template(db_conn, _payload([stack], [uuid.uuid4()]))
    finally:
        await trans.rollback()


async def test_competency_in_wrong_stack_rejected(db_conn: AsyncConnection) -> None:
    trans = await db_conn.begin()
    try:
        stack_a, _comp_a = await _seed_stack_with_competency(db_conn, "Backend Python", "Async")
        _stack_b, comp_b = await _seed_stack_with_competency(db_conn, "Frontend React", "Hooks")
        # Select stack A but a competency that belongs to stack B.
        with pytest.raises(PositionTemplateValidationError, match="not in any selected stack"):
            await validate_position_template(db_conn, _payload([stack_a], [comp_b]))
    finally:
        await trans.rollback()
