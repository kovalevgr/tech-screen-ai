#!/usr/bin/env python3
"""Bidirectional feature-flag registration guard (T05a — FR-010, FR-011).

Pre-commit + CI hook. Runs on the **post-state of the tree** (no git-diff
awareness, research §8) and enforces every consistency invariant between:

- ``configs/feature-flags.yaml``                  (source of truth)
- ``docs/contracts/feature-flag.schema.json``     (the YAML schema)
- ``docs/engineering/feature-flags.md``           (the human index)
- ``app/backend/**/*.py``                          (in-code call sites)

Exit codes:
- ``0`` — clean tree, all invariants hold.
- ``1`` — one or more violations; each violation is reported with a precise
  file + actionable message.
- ``2`` — a required file is missing (configuration error, not a violation).

Use ``--root <path>`` to point the hook at a fake-tree for testing (the
default is auto-detected from the script's location).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

_DEFAULT_REPO_ROOT: Path = Path(__file__).resolve().parents[1]

# Match `is_enabled("name")` or `is_enabled('name')` (string-literal arg only).
_IS_ENABLED_PATTERN: re.Pattern[str] = re.compile(r"""is_enabled\s*\(\s*["']([^"']+)["']""")


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: expected a YAML mapping at top level")
    return loaded


def _scan_call_sites(backend_root: Path, repo_root: Path) -> dict[str, list[Path]]:
    """Return mapping ``flag_name -> [paths]`` for every literal ``is_enabled(...)`` call.

    Skips the service module itself (which defines ``is_enabled``) and the
    test tree (tests may reference non-existent names by design).
    """
    result: dict[str, list[Path]] = {}
    if not backend_root.exists():
        return result
    service_definition = backend_root / "services" / "feature_flags.py"
    for py_file in backend_root.rglob("*.py"):
        if py_file == service_definition:
            continue
        if "tests" in py_file.relative_to(backend_root).parts:
            continue
        content = py_file.read_text(encoding="utf-8", errors="replace")
        for match in _IS_ENABLED_PATTERN.finditer(content):
            name = match.group(1)
            result.setdefault(name, []).append(py_file.relative_to(repo_root))
    return result


def _parse_docs_tables(path: Path) -> tuple[set[str], dict[str, tuple[str, str]]]:
    """Return (active_names, sunset_entries[name] = (pr, date)) from the docs.

    Recognises sections by case-insensitive ``## Active flags`` / ``## Sunset
    flags`` headers; reads the leading two/three columns of subsequent table
    rows (skipping the header separator).
    """
    if not path.exists():
        return set(), {}
    active: set[str] = set()
    sunset: dict[str, tuple[str, str]] = {}
    section: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        lower = stripped.lower()
        if lower.startswith("## active flags"):
            section = "active"
            continue
        if lower.startswith("## sunset flags"):
            section = "sunset"
            continue
        if stripped.startswith("## "):
            section = None
            continue
        if section is None or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0].strip("`")
        # Skip header row + separator row.
        if first.lower() in ("name", ""):
            continue
        if set(first) <= {"-", ":"}:
            continue
        if section == "active":
            active.add(first)
        elif section == "sunset" and len(cells) >= 3:
            sunset[first] = (cells[1], cells[2])
    return active, sunset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        default=str(_DEFAULT_REPO_ROOT),
        help="Repo root (default: auto-detected from script location).",
    )
    # Pre-commit passes the list of changed files as positional args; we
    # accept and ignore them — the post-state check runs on the whole tree.
    parser.add_argument("files", nargs="*", help="Ignored (pre-commit compatibility).")
    args = parser.parse_args(argv)
    repo_root = Path(args.root).resolve()
    yaml_path = repo_root / "configs" / "feature-flags.yaml"
    schema_path = repo_root / "docs" / "contracts" / "feature-flag.schema.json"
    docs_path = repo_root / "docs" / "engineering" / "feature-flags.md"
    backend_path = repo_root / "app" / "backend"

    # ---- Load required files ----
    missing: list[Path] = [p for p in (yaml_path, schema_path) if not p.exists()]
    if missing:
        for p in missing:
            print(f"error: required file missing: {p}", file=sys.stderr)
        return 2

    yaml_doc = _load_yaml(yaml_path)
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    errors: list[str] = []

    # ---- (a) Schema validation (FR-006) ----
    validator = Draft202012Validator(schema)
    schema_errors = list(validator.iter_errors(yaml_doc))
    for err in schema_errors:
        path = ".".join(str(p) for p in err.absolute_path) or "<root>"
        errors.append(f"{yaml_path.relative_to(repo_root)}: ${path}: {err.message}")
    if schema_errors:
        # Downstream checks assume a conformant YAML; stop here.
        for line in errors:
            print(f"error: {line}", file=sys.stderr)
        return 1

    flags = yaml_doc.get("flags") or []
    yaml_active = {f["name"] for f in flags if f["state"] == "active"}
    yaml_sunset = {f["name"]: f for f in flags if f["state"] == "sunset"}

    # ---- (b) Scan call sites ----
    call_sites = _scan_call_sites(backend_path, repo_root)
    call_names = set(call_sites)

    # ---- (c) Parse docs tables ----
    docs_active, docs_sunset = _parse_docs_tables(docs_path)

    # ---- FR-010a: undeclared call sites ----
    for name in sorted(call_names - yaml_active):
        files = ", ".join(str(f) for f in call_sites[name])
        errors.append(
            f"'{name}' is referenced in code ({files}) but not declared in "
            f"configs/feature-flags.yaml with state=active"
        )

    # ---- FR-010b: active YAML entry without a call site ----
    for name in sorted(yaml_active - call_names):
        errors.append(
            f"'{name}' is state=active but has no call site in app/backend/ "
            f"— flip to state=sunset (with sunset_pr + sunset_date + docs row) "
            f"or restore a call site"
        )

    # ---- FR-011: sunset entries must have docs rows with pr + date ----
    for name in sorted(yaml_sunset):
        if name not in docs_sunset:
            errors.append(
                f"'{name}' is state=sunset but missing from "
                f"docs/engineering/feature-flags.md Sunset table"
            )
            continue
        pr, date = docs_sunset[name]
        if not pr:
            errors.append(f"'{name}' sunset row in docs has an empty PR back-reference")
        if not date:
            errors.append(f"'{name}' sunset row in docs has an empty sunset_date")

    # ---- FR-011: orphan docs rows ----
    for name in sorted(set(docs_sunset) - set(yaml_sunset)):
        errors.append(
            f"'{name}' appears in docs/engineering/feature-flags.md Sunset table "
            f"but not in configs/feature-flags.yaml"
        )

    if errors:
        for line in errors:
            print(f"error: {line}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
