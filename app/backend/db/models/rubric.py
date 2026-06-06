"""Rubric read-only tree (data-model §Rubric; §4 / ADR-018).

The tree is ``rubric_tree_version → stack → competency_block → competency →
{topic, level}``. Every node carries a ``rubric_tree_version_id`` so a whole
tree is addressable by version: new rubric content creates a *new* version and
existing nodes are never edited in place (T15 snapshotting copies by version).

Columns are minimal-but-coherent (research §10): the parent FK + version FK +
the one or two domain columns named in the data model. Weightings, scoring
anchors, and localisation are deferred to the T08 rubric tooling.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.backend.db.base import Base
from app.backend.db.models._mixins import TimestampCreated, UUIDPk


class RubricTreeVersion(UUIDPk, TimestampCreated, Base):
    """A named, versioned snapshot root for an entire rubric tree."""

    __tablename__ = "rubric_tree_version"

    label: Mapped[str] = mapped_column(Text, nullable=False)
    # At most one active version is enforced in app/importer logic (T08),
    # not as a DB constraint at T05.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class Stack(UUIDPk, TimestampCreated, Base):
    """Top of the tree, e.g. "Backend Python"."""

    __tablename__ = "stack"

    rubric_tree_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_tree_version.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)


class CompetencyBlock(UUIDPk, TimestampCreated, Base):
    """Groups competencies within a stack."""

    __tablename__ = "competency_block"

    rubric_tree_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_tree_version.id"),
        nullable=False,
    )
    stack_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("stack.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


class Competency(UUIDPk, TimestampCreated, Base):
    """A scored competency."""

    __tablename__ = "competency"

    rubric_tree_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_tree_version.id"),
        nullable=False,
    )
    competency_block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competency_block.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Topic(UUIDPk, TimestampCreated, Base):
    """A probe area within a competency."""

    __tablename__ = "topic"

    rubric_tree_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_tree_version.id"),
        nullable=False,
    )
    competency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competency.id"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)


class Level(UUIDPk, TimestampCreated, Base):
    """A proficiency descriptor for a competency (e.g. rank 1–5)."""

    __tablename__ = "level"

    rubric_tree_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rubric_tree_version.id"),
        nullable=False,
    )
    competency_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("competency.id"),
        nullable=False,
    )
    rank: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    descriptor: Mapped[str] = mapped_column(Text, nullable=False)
