#!/usr/bin/env python3
"""Rubric YAML schema guard (T08 — FR-011).

Pre-commit + CI hook. Validates every ``configs/rubric/*.yaml`` against the
committed schema at ``docs/contracts/rubric.schema.json``. Mirrors the shape
of ``scripts/check-feature-flag-registration.py`` (T05a).

Exit codes:
- ``0`` — every YAML file validates cleanly.
- ``1`` — one or more files violate the schema (precise message per failure).
- ``2`` — a required file is missing (configuration error, not a violation).

Use ``--root <path>`` to point the hook at a fake-tree for testing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

_DEFAULT_REPO_ROOT: Path = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    return loaded


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        default=str(_DEFAULT_REPO_ROOT),
        help="Repo root (default: auto-detected).",
    )
    parser.add_argument("files", nargs="*", help="Ignored (pre-commit compatibility).")
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()
    schema_path = repo_root / "docs" / "contracts" / "rubric.schema.json"
    rubric_dir = repo_root / "configs" / "rubric"

    if not schema_path.exists():
        print(f"error: required file missing: {schema_path}", file=sys.stderr)
        return 2
    if not rubric_dir.exists():
        print(f"error: required directory missing: {rubric_dir}", file=sys.stderr)
        return 2

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    errors: list[str] = []
    for path in sorted(rubric_dir.glob("*.yaml")):
        try:
            doc = _load_yaml(path)
        except (yaml.YAMLError, ValueError) as exc:
            errors.append(f"{path.relative_to(repo_root)}: cannot parse YAML: {exc}")
            continue
        for err in validator.iter_errors(doc):
            json_path = ".".join(str(p) for p in err.absolute_path) or "<root>"
            errors.append(f"{path.relative_to(repo_root)}: ${json_path}: {err.message}")

    if errors:
        for line in errors:
            print(f"error: {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
