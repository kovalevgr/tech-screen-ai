"""The frozen rubric snapshot shape (T15, constitution §4).

A self-contained copy of a rubric version's tree, stored on
``interview_session.rubric_snapshot``. Mirrors the T08 rubric tree
(stack → competency_block → competency → {topic, level}); source ids are carried
as plain values (provenance + Assessor correlation), never as live foreign keys.
The committed JSON-schema contract is ``docs/contracts/rubric-snapshot.schema.json``.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class SnapshotLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    rank: int
    descriptor: str


class SnapshotTopic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str


class SnapshotCompetency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    topics: list[SnapshotTopic]
    levels: list[SnapshotLevel]


class SnapshotCompetencyBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    position: int
    competencies: list[SnapshotCompetency]


class SnapshotStack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    name: str
    competency_blocks: list[SnapshotCompetencyBlock]


class RubricSnapshot(BaseModel):
    """The whole frozen tree for one rubric version."""

    model_config = ConfigDict(extra="forbid")

    rubric_tree_version_id: uuid.UUID
    label: str
    stacks: list[SnapshotStack]
