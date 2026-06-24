"""The committed Position Template JSON-schema contract (T12 / US2 / SC-003).

Asserts docs/contracts/position-template.schema.json is a valid Draft 2020-12
schema and that it accepts a good `create` example and rejects a bad-level one.
This is the §14 contract T13/T14 build against.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "contracts" / "position-template.schema.json"

_GOOD_CREATE = {
    "title": "Senior Backend Python",
    "level": "Senior",
    "jd_text": None,
    "stack_ids": ["11111111-1111-1111-1111-111111111111"],
    "competency_ids": ["22222222-2222-2222-2222-222222222222"],
    "must_have_competency_ids": ["22222222-2222-2222-2222-222222222222"],
}


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return cast("dict[str, Any]", json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def validator(schema: dict[str, Any]) -> Draft202012Validator:
    return Draft202012Validator(schema)


def test_schema_is_valid_draft_2020_12(schema: dict[str, Any]) -> None:
    Draft202012Validator.check_schema(schema)


def test_good_create_example_validates(validator: Draft202012Validator) -> None:
    assert validator.is_valid(_GOOD_CREATE)


def test_bad_level_example_rejected(validator: Draft202012Validator) -> None:
    bad = dict(_GOOD_CREATE)
    bad["level"] = "Architect"
    assert not validator.is_valid(bad)


def test_create_requires_competency_ids(validator: Draft202012Validator) -> None:
    bad = dict(_GOOD_CREATE)
    del bad["competency_ids"]
    assert not validator.is_valid(bad)
