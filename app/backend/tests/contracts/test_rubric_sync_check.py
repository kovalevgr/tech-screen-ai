"""Tests for ``scripts/sync_rubric_to_db.py check`` (T16 destructive-change gate).

Mirrors the subprocess pattern of ``test_feature_flag_registration.py``: each
case builds a baseline dir + current dir + ADR-context file on ``tmp_path``
and asserts on exit code and message text. No database, no git — the gate is
a pure YAML-vs-YAML comparison (the workflow supplies the git extraction).

Coverage (T16 deliverable): benign edit, removed topic (retire), retyped
level, plus the forbidden-removal / removed-level / un-retire / ADR-authorised
/ empty-baseline paths.
"""

from __future__ import annotations

import copy
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCRIPT: Path = _REPO_ROOT / "scripts" / "sync_rubric_to_db.py"

# Baseline fixture: one stack file with a block, a leaf competency carrying
# two levels, and a topic child — the shapes the detector must distinguish.
_BASELINE_DOC: dict[str, Any] = {
    "version": 1,
    "retired": False,
    "nodes": [
        {
            "id": "block.core",
            "label_en": "Core",
            "label_uk": "Ядро",
            "parent": None,
            "retired": False,
        },
        {
            "id": "python.concurrency",
            "label_en": "Concurrency",
            "label_uk": "Конкурентність",
            "parent": "block.core",
            "retired": False,
            "levels": [
                {
                    "level": 1,
                    "label_uk": "Початківець",
                    "descriptor_en": "Knows threads exist.",
                },
                {
                    "level": 2,
                    "label_uk": "Середній",
                    "descriptor_en": "Uses asyncio primitives correctly.",
                },
            ],
        },
        {
            "id": "python.concurrency.gil",
            "label_en": "GIL",
            "label_uk": "GIL",
            "parent": "python.concurrency",
            "retired": False,
        },
    ],
}


def _write_dirs(
    tmp_path: Path,
    current_doc: dict[str, Any],
    *,
    baseline_doc: dict[str, Any] | None = _BASELINE_DOC,
    adr_context: str | None = None,
) -> list[str]:
    """Materialise fixture dirs and return the CLI argument vector."""
    baseline_dir = tmp_path / "baseline"
    rubric_dir = tmp_path / "current"
    baseline_dir.mkdir()
    rubric_dir.mkdir()
    if baseline_doc is not None:
        (baseline_dir / "python.yaml").write_text(
            yaml.safe_dump(baseline_doc, allow_unicode=True), encoding="utf-8"
        )
    (rubric_dir / "python.yaml").write_text(
        yaml.safe_dump(current_doc, allow_unicode=True), encoding="utf-8"
    )
    argv = [
        sys.executable,
        str(_SCRIPT),
        "check",
        "--baseline-dir",
        str(baseline_dir),
        "--rubric-dir",
        str(rubric_dir),
    ]
    if adr_context is not None:
        adr_file = tmp_path / "adr-context.txt"
        adr_file.write_text(adr_context, encoding="utf-8")
        argv += ["--adr-context-file", str(adr_file)]
    return argv


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _node(doc: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(n for n in doc["nodes"] if n["id"] == node_id)


def test_benign_edit_passes_without_adr(tmp_path: Path) -> None:
    """Label edit + new node + new level + version bump — all benign."""
    doc = copy.deepcopy(_BASELINE_DOC)
    doc["version"] = 2
    _node(doc, "python.concurrency")["label_uk"] = "Конкурентність і паралелізм"
    _node(doc, "python.concurrency")["levels"].append(
        {"level": 3, "label_uk": "Просунутий", "descriptor_en": "Designs safe concurrent APIs."}
    )
    doc["nodes"].append(
        {
            "id": "python.decorators",
            "label_en": "Decorators",
            "label_uk": "Декоратори",
            "parent": "block.core",
            "retired": False,
        }
    )
    result = _run(_write_dirs(tmp_path, doc))
    assert result.returncode == 0, result.stderr
    assert "no destructive changes" in result.stdout


def test_removed_topic_via_retire_requires_adr(tmp_path: Path) -> None:
    """Retiring a topic node is destructive → fails without an ADR citation."""
    doc = copy.deepcopy(_BASELINE_DOC)
    _node(doc, "python.concurrency.gil")["retired"] = True
    result = _run(_write_dirs(tmp_path, doc))
    assert result.returncode == 1
    assert "NODE_RETIRED" in result.stdout
    assert "python.concurrency.gil" in result.stdout
    assert "ADR" in result.stderr


def test_retyped_level_requires_adr(tmp_path: Path) -> None:
    """Changing a level's descriptor_en is destructive → fails without ADR."""
    doc = copy.deepcopy(_BASELINE_DOC)
    _node(doc, "python.concurrency")["levels"][1]["descriptor_en"] = (
        "Explains the event loop and structured concurrency."
    )
    result = _run(_write_dirs(tmp_path, doc))
    assert result.returncode == 1
    assert "LEVEL_RETYPED" in result.stdout
    assert "python.concurrency" in result.stdout


def test_removed_level_requires_adr(tmp_path: Path) -> None:
    doc = copy.deepcopy(_BASELINE_DOC)
    del _node(doc, "python.concurrency")["levels"][1]
    result = _run(_write_dirs(tmp_path, doc))
    assert result.returncode == 1
    assert "LEVEL_REMOVED" in result.stdout
    assert "level 2" in result.stdout


def test_destructive_with_adr_citation_passes(tmp_path: Path) -> None:
    """The same retire passes when the PR-body context cites an ADR."""
    doc = copy.deepcopy(_BASELINE_DOC)
    _node(doc, "python.concurrency.gil")["retired"] = True
    result = _run(
        _write_dirs(tmp_path, doc, adr_context="Retire GIL topic per ADR-024 (scope cut).")
    )
    assert result.returncode == 0, result.stderr
    assert "authorised" in result.stdout
    assert "ADR-024" in result.stdout


def test_removed_id_is_forbidden_even_with_adr(tmp_path: Path) -> None:
    """Deleting a stable id outright is refused regardless of citation (FR-009)."""
    doc = copy.deepcopy(_BASELINE_DOC)
    doc["nodes"] = [n for n in doc["nodes"] if n["id"] != "python.concurrency.gil"]
    result = _run(_write_dirs(tmp_path, doc, adr_context="Approved via ADR-024."))
    assert result.returncode == 2
    assert "NODE_REMOVED" in result.stdout
    assert "retire" in (result.stdout + result.stderr).lower()


def test_unretire_requires_adr(tmp_path: Path) -> None:
    """Resurrecting a retired id is gated too — ids are never reused after retire."""
    baseline = copy.deepcopy(_BASELINE_DOC)
    _node(baseline, "python.concurrency.gil")["retired"] = True
    doc = copy.deepcopy(_BASELINE_DOC)  # gil active again
    result = _run(_write_dirs(tmp_path, doc, baseline_doc=baseline))
    assert result.returncode == 1
    assert "NODE_UNRETIRED" in result.stdout


def test_empty_baseline_treats_everything_as_new(tmp_path: Path) -> None:
    """First sync (or initial commit): no baseline files → all nodes are additions."""
    result = _run(_write_dirs(tmp_path, copy.deepcopy(_BASELINE_DOC), baseline_doc=None))
    assert result.returncode == 0, result.stderr
    assert "no destructive changes" in result.stdout


def test_adr_regex_is_word_bounded(tmp_path: Path) -> None:
    """'BADR-123' or 'ADR-12' must not satisfy the gate."""
    doc = copy.deepcopy(_BASELINE_DOC)
    _node(doc, "python.concurrency.gil")["retired"] = True
    result = _run(_write_dirs(tmp_path, doc, adr_context="see BADR-123 and ADR-12 maybe"))
    assert result.returncode == 1
