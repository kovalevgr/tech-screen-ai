"""Schema-violation matrix for rubric YAML (T08 / US3 / SC-006 / SC-007).

Five distinct fixture YAMLs each violate a single rule; the validator must
report the offending JSON path. Plus a positive baseline: the committed
``configs/rubric/example.yaml`` validates clean (SC-006).
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCHEMA_PATH: Path = _REPO_ROOT / "docs" / "contracts" / "rubric.schema.json"
_EXAMPLE_YAML: Path = _REPO_ROOT / "configs" / "rubric" / "example.yaml"


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(_SCHEMA_PATH.read_text(encoding="utf-8")))


def _violations(validator: Draft202012Validator, doc_text: str) -> list[str]:
    doc = yaml.safe_load(doc_text)
    return [
        ".".join(str(p) for p in err.absolute_path) + ": " + err.message
        for err in validator.iter_errors(doc)
    ]


def test_clean_example_yaml_passes(validator: Draft202012Validator) -> None:
    """SC-006 baseline: the shipped example file validates."""
    text = _EXAMPLE_YAML.read_text(encoding="utf-8")
    assert _violations(validator, text) == []


def test_missing_label_uk_on_active_node(validator: Draft202012Validator) -> None:
    text = textwrap.dedent(
        """\
        version: 1
        retired: false
        nodes:
          - id: python.concurrency
            label_en: Concurrency
            parent: null
            retired: false
        """
    )
    errors = _violations(validator, text)
    assert any("label_uk" in e for e in errors), errors


def test_invalid_level_above_5(validator: Draft202012Validator) -> None:
    text = textwrap.dedent(
        """\
        version: 1
        nodes:
          - id: python.x
            label_en: X
            label_uk: Х
            parent: null
            retired: false
            levels:
              - level: 6
                label_uk: Mid
                descriptor_en: too high
        """
    )
    errors = _violations(validator, text)
    assert any("level" in e for e in errors), errors


def test_bad_id_regex(validator: Draft202012Validator) -> None:
    text = textwrap.dedent(
        """\
        version: 1
        nodes:
          - id: NotSnakeCase
            label_en: Bad
            label_uk: Поганий
        """
    )
    errors = _violations(validator, text)
    assert any("does not match" in e and "NotSnakeCase" in e for e in errors), errors


def test_missing_descriptor_en_on_level(validator: Draft202012Validator) -> None:
    text = textwrap.dedent(
        """\
        version: 1
        nodes:
          - id: python.x
            label_en: X
            label_uk: Х
            parent: null
            levels:
              - level: 1
                label_uk: Junior
        """
    )
    errors = _violations(validator, text)
    assert any("descriptor_en" in e for e in errors), errors


def test_missing_required_version(validator: Draft202012Validator) -> None:
    text = textwrap.dedent(
        """\
        retired: false
        nodes: []
        """
    )
    errors = _violations(validator, text)
    assert any("version" in e for e in errors), errors
