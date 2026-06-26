"""Rubric snapshotting (T15, constitution §4).

``snapshot_rubric`` deep-copies a rubric version's whole tree into the
self-contained :class:`RubricSnapshot` shape; ``freeze_session_rubric`` writes it
onto an ``interview_session``. Data access is SQLAlchemy Core over an
``AsyncConnection`` (the rubric read style), so the producer is ORM-independent.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.schemas.rubric_snapshot import (
    RubricSnapshot,
    SnapshotCompetency,
    SnapshotCompetencyBlock,
    SnapshotLevel,
    SnapshotStack,
    SnapshotTopic,
)


class RubricSnapshotError(ValueError):
    """Raised when a rubric snapshot cannot be produced (e.g. unknown version)."""


async def snapshot_rubric(
    conn: AsyncConnection, rubric_tree_version_id: uuid.UUID
) -> RubricSnapshot:
    """Deep-copy the full tree for ``rubric_tree_version_id`` into a snapshot.

    Raises :class:`RubricSnapshotError` if the version does not exist (FR-005).
    Ordering is deterministic so the serialized snapshot is stable.
    """
    label_row = (
        await conn.execute(
            text("SELECT label FROM rubric_tree_version WHERE id = :v"),
            {"v": rubric_tree_version_id},
        )
    ).first()
    if label_row is None:
        raise RubricSnapshotError(f"rubric_tree_version {rubric_tree_version_id} does not exist")
    label: str = label_row[0]

    stack_rows = (
        await conn.execute(
            text("SELECT id, name FROM stack WHERE rubric_tree_version_id = :v ORDER BY name, id"),
            {"v": rubric_tree_version_id},
        )
    ).all()
    block_rows = (
        await conn.execute(
            text(
                "SELECT id, stack_id, name, position FROM competency_block "
                "WHERE rubric_tree_version_id = :v ORDER BY position, name, id"
            ),
            {"v": rubric_tree_version_id},
        )
    ).all()
    competency_rows = (
        await conn.execute(
            text(
                "SELECT id, competency_block_id, name FROM competency "
                "WHERE rubric_tree_version_id = :v ORDER BY name, id"
            ),
            {"v": rubric_tree_version_id},
        )
    ).all()
    topic_rows = (
        await conn.execute(
            text(
                "SELECT id, competency_id, name FROM topic "
                "WHERE rubric_tree_version_id = :v ORDER BY name, id"
            ),
            {"v": rubric_tree_version_id},
        )
    ).all()
    level_rows = (
        await conn.execute(
            text(
                "SELECT id, competency_id, rank, descriptor FROM level "
                "WHERE rubric_tree_version_id = :v ORDER BY rank, id"
            ),
            {"v": rubric_tree_version_id},
        )
    ).all()

    topics_by_competency: defaultdict[uuid.UUID, list[SnapshotTopic]] = defaultdict(list)
    for topic_id, competency_id, name in topic_rows:
        topics_by_competency[competency_id].append(SnapshotTopic(id=topic_id, name=name))

    levels_by_competency: defaultdict[uuid.UUID, list[SnapshotLevel]] = defaultdict(list)
    for level_id, competency_id, rank, descriptor in level_rows:
        levels_by_competency[competency_id].append(
            SnapshotLevel(id=level_id, rank=rank, descriptor=descriptor)
        )

    competencies_by_block: defaultdict[uuid.UUID, list[SnapshotCompetency]] = defaultdict(list)
    for competency_id, block_id, name in competency_rows:
        competencies_by_block[block_id].append(
            SnapshotCompetency(
                id=competency_id,
                name=name,
                topics=topics_by_competency.get(competency_id, []),
                levels=levels_by_competency.get(competency_id, []),
            )
        )

    blocks_by_stack: defaultdict[uuid.UUID, list[SnapshotCompetencyBlock]] = defaultdict(list)
    for block_id, stack_id, name, position in block_rows:
        blocks_by_stack[stack_id].append(
            SnapshotCompetencyBlock(
                id=block_id,
                name=name,
                position=position,
                competencies=competencies_by_block.get(block_id, []),
            )
        )

    stacks = [
        SnapshotStack(
            id=stack_id,
            name=name,
            competency_blocks=blocks_by_stack.get(stack_id, []),
        )
        for stack_id, name in stack_rows
    ]

    return RubricSnapshot(rubric_tree_version_id=rubric_tree_version_id, label=label, stacks=stacks)


async def freeze_session_rubric(
    conn: AsyncConnection,
    interview_session_id: uuid.UUID,
    rubric_tree_version_id: uuid.UUID,
) -> RubricSnapshot:
    """Snapshot the version and write it onto the session (§4 capture).

    Used by the real session-start flow (T28); exercised directly in T15 tests.
    """
    snapshot = await snapshot_rubric(conn, rubric_tree_version_id)
    await conn.execute(
        text("UPDATE interview_session SET rubric_snapshot = CAST(:snap AS JSONB) WHERE id = :sid"),
        {"snap": json.dumps(snapshot.model_dump(mode="json")), "sid": interview_session_id},
    )
    return snapshot
