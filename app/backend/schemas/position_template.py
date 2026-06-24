"""Pydantic boundary schemas for Position Templates (T12).

Stateless validation only — the `level` enum, the must-have ⊆ selected subset
rule, the "at least one competency" rule, and id de-duplication. DB-dependent
rules (stack existence, competency-belongs-to-a-selected-stack) cannot run here
because Pydantic is stateless; they live in
:mod:`app.backend.services.position_template`.

These shapes are the source of truth mirrored by
``docs/contracts/position-template.schema.json`` (the §14 contract).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PositionLevel(StrEnum):
    """Target seniority of a role — distinct from rubric per-competency levels."""

    JUNIOR = "Junior"
    MIDDLE = "Middle"
    SENIOR = "Senior"
    TECH_LEADER = "Tech Leader"


def _reject_duplicates(ids: list[uuid.UUID], field: str) -> None:
    if len(set(ids)) != len(ids):
        raise ValueError(f"{field} contains duplicate ids")


class PositionTemplateCreate(BaseModel):
    """Request body for creating a Position Template (the T13 POST shape)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    level: PositionLevel
    jd_text: str | None = None
    stack_ids: list[uuid.UUID] = Field(min_length=1)
    competency_ids: list[uuid.UUID] = Field(min_length=1)
    must_have_competency_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        _reject_duplicates(self.stack_ids, "stack_ids")
        _reject_duplicates(self.competency_ids, "competency_ids")
        _reject_duplicates(self.must_have_competency_ids, "must_have_competency_ids")
        not_selected = set(self.must_have_competency_ids) - set(self.competency_ids)
        if not_selected:
            raise ValueError(
                "must_have_competency_ids must be a subset of competency_ids; "
                f"not selected: {sorted(str(c) for c in not_selected)}"
            )
        return self


class CompetencySelection(BaseModel):
    """One selected competency and whether it is mandatory."""

    model_config = ConfigDict(extra="forbid")

    competency_id: uuid.UUID
    must_have: bool


class PositionTemplateRead(BaseModel):
    """Response body for reading a Position Template (the T13 GET shape)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: uuid.UUID
    title: str
    level: PositionLevel
    jd_text: str | None
    archived_at: datetime | None
    created_at: datetime
    created_by: uuid.UUID | None
    stack_ids: list[uuid.UUID]
    competencies: list[CompetencySelection]
