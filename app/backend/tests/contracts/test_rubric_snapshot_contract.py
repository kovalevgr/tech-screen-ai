"""The committed rubric-snapshot JSON-schema contract (T15 / §14 / SC-005).

Asserts docs/contracts/rubric-snapshot.schema.json is a valid Draft 2020-12
schema and that it accepts a good snapshot and rejects a malformed one. Also
checks that a real RubricSnapshot serialization validates against it (producer ↔
contract agreement).
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

from app.backend.schemas.rubric_snapshot import (
    RubricSnapshot,
    SnapshotCompetency,
    SnapshotCompetencyBlock,
    SnapshotLevel,
    SnapshotStack,
    SnapshotTopic,
)

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "contracts" / "rubric-snapshot.schema.json"


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


def _good_snapshot() -> RubricSnapshot:
    return RubricSnapshot(
        rubric_tree_version_id=uuid.uuid4(),
        label="2026-Q2",
        stacks=[
            SnapshotStack(
                id=uuid.uuid4(),
                name="Backend Python",
                competency_blocks=[
                    SnapshotCompetencyBlock(
                        id=uuid.uuid4(),
                        name="Core",
                        position=1,
                        competencies=[
                            SnapshotCompetency(
                                id=uuid.uuid4(),
                                name="Concurrency",
                                topics=[SnapshotTopic(id=uuid.uuid4(), name="asyncio")],
                                levels=[SnapshotLevel(id=uuid.uuid4(), rank=3, descriptor="Solid")],
                            )
                        ],
                    )
                ],
            )
        ],
    )


def test_schema_is_valid_draft_2020_12(schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)


def test_real_snapshot_validates(validator: Draft202012Validator) -> None:
    assert validator.is_valid(_good_snapshot().model_dump(mode="json"))


def test_malformed_snapshot_rejected(validator: Draft202012Validator) -> None:
    bad = _good_snapshot().model_dump(mode="json")
    del bad["rubric_tree_version_id"]
    assert not validator.is_valid(bad)


def test_empty_stacks_is_valid(validator: Draft202012Validator) -> None:
    snap = {"rubric_tree_version_id": str(uuid.uuid4()), "label": "empty", "stacks": []}
    assert validator.is_valid(snap)
