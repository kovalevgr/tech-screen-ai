"""Subprocess tests for ``scripts/check-rubric-schema.py`` (T08 / US3).

Builds fake repo trees under ``tmp_path`` (with the schema + a fixture YAML)
and invokes the hook with ``--root <tmp_path>``. Positive: the real
post-T08 tree returns exit 0 (SC-006).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCRIPT: Path = _REPO_ROOT / "scripts" / "check-rubric-schema.py"
_SCHEMA: Path = _REPO_ROOT / "docs" / "contracts" / "rubric.schema.json"


def _setup_fake(tmp_path: Path, yaml_body: str) -> Path:
    (tmp_path / "configs" / "rubric").mkdir(parents=True)
    (tmp_path / "docs" / "contracts").mkdir(parents=True)
    (tmp_path / "configs" / "rubric" / "test.yaml").write_text(yaml_body, encoding="utf-8")
    shutil.copy(_SCHEMA, tmp_path / "docs" / "contracts" / "rubric.schema.json")
    return tmp_path


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_real_tree_is_clean() -> None:
    """SC-006: the committed configs/rubric/*.yaml + schema validate clean."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, f"stderr=\n{result.stderr}"


def test_fake_clean_tree_passes(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """\
        version: 1
        retired: false
        nodes:
          - id: example.x
            label_en: X
            label_uk: Х
            parent: null
            retired: true
        """
    )
    result = _run(_setup_fake(tmp_path, body))
    assert result.returncode == 0, result.stderr


def test_missing_required_field_fails(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """\
        retired: false
        nodes: []
        """
    )
    result = _run(_setup_fake(tmp_path, body))
    assert result.returncode == 1
    assert "version" in result.stderr


def test_invalid_id_pattern_fails(tmp_path: Path) -> None:
    body = textwrap.dedent(
        """\
        version: 1
        nodes:
          - id: BadName
            label_en: Bad
            label_uk: Поганий
        """
    )
    result = _run(_setup_fake(tmp_path, body))
    assert result.returncode == 1
    assert "id" in result.stderr.lower() or "pattern" in result.stderr.lower()
