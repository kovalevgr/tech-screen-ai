"""Stateless validation rules for PositionTemplateCreate (T12 / US1 / SC-002).

No database needed — these exercise the Pydantic boundary: the level enum,
must-have ⊆ selected, ≥1 competency, and id de-duplication.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.backend.schemas.position_template import PositionLevel, PositionTemplateCreate


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_valid_payload_accepted() -> None:
    stack = _ids(1)
    comp = _ids(2)
    tpl = PositionTemplateCreate(
        title="Senior Backend Python",
        level=PositionLevel.SENIOR,
        jd_text=None,
        stack_ids=stack,
        competency_ids=comp,
        must_have_competency_ids=[comp[0]],
    )
    assert tpl.level is PositionLevel.SENIOR
    assert tpl.must_have_competency_ids == [comp[0]]


def test_invalid_level_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTemplateCreate(
            title="x",
            level="Architect",  # type: ignore[arg-type]
            stack_ids=_ids(1),
            competency_ids=_ids(1),
        )


def test_empty_title_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTemplateCreate(
            title="",
            level=PositionLevel.MIDDLE,
            stack_ids=_ids(1),
            competency_ids=_ids(1),
        )


def test_zero_competencies_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTemplateCreate(
            title="x",
            level=PositionLevel.MIDDLE,
            stack_ids=_ids(1),
            competency_ids=[],
        )


def test_zero_stacks_rejected() -> None:
    with pytest.raises(ValidationError):
        PositionTemplateCreate(
            title="x",
            level=PositionLevel.MIDDLE,
            stack_ids=[],
            competency_ids=_ids(1),
        )


def test_must_have_not_subset_rejected() -> None:
    comp = _ids(2)
    rogue = uuid.uuid4()
    with pytest.raises(ValidationError, match="subset"):
        PositionTemplateCreate(
            title="x",
            level=PositionLevel.MIDDLE,
            stack_ids=_ids(1),
            competency_ids=comp,
            must_have_competency_ids=[rogue],
        )


def test_duplicate_competency_ids_rejected() -> None:
    dup = uuid.uuid4()
    with pytest.raises(ValidationError, match="duplicate"):
        PositionTemplateCreate(
            title="x",
            level=PositionLevel.MIDDLE,
            stack_ids=_ids(1),
            competency_ids=[dup, dup],
        )


def test_extra_field_forbidden() -> None:
    with pytest.raises(ValidationError):
        PositionTemplateCreate(
            title="x",
            level=PositionLevel.MIDDLE,
            stack_ids=_ids(1),
            competency_ids=_ids(1),
            surprise="nope",  # type: ignore[call-arg]
        )
