"""Tests for ``scripts/check-feature-flag-registration.py`` (T05a, US3).

Each fixture builds a fake-repo on ``tmp_path`` and invokes the hook with
``--root tmp_path``; assertions check the exit code and that the precise
violation message appears in stderr (SC-006).

Five failure modes + one positive (clean-tree) test.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCRIPT: Path = _REPO_ROOT / "scripts" / "check-feature-flag-registration.py"
_SCHEMA: Path = _REPO_ROOT / "docs" / "contracts" / "feature-flag.schema.json"


def _setup_fake_repo(
    tmp_path: Path,
    *,
    yaml_body: str,
    docs_body: str,
    call_site_body: str | None = None,
) -> Path:
    """Build a minimal tmp_path/{configs,docs/contracts,docs/engineering,app/backend} tree."""
    (tmp_path / "configs").mkdir()
    (tmp_path / "docs" / "contracts").mkdir(parents=True)
    (tmp_path / "docs" / "engineering").mkdir(parents=True)
    (tmp_path / "app" / "backend").mkdir(parents=True)
    (tmp_path / "configs" / "feature-flags.yaml").write_text(yaml_body, encoding="utf-8")
    shutil.copy(_SCHEMA, tmp_path / "docs" / "contracts" / "feature-flag.schema.json")
    (tmp_path / "docs" / "engineering" / "feature-flags.md").write_text(docs_body, encoding="utf-8")
    if call_site_body is not None:
        (tmp_path / "app" / "backend" / "demo.py").write_text(call_site_body, encoding="utf-8")
    return tmp_path


def _run(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )


# Reusable minimal contents.
_CLEAN_YAML = textwrap.dedent(
    """\
    flags:
      - name: legacy_demo
        owner: "@andrii"
        default: false
        description: "demo"
        state: sunset
        sunset_pr: "#1"
        sunset_date: "2026-04-28"
    """
)
_CLEAN_DOCS = textwrap.dedent(
    """\
    # Feature flags

    ## Active flags
    | name | owner | default | description |
    | ---- | ----- | ------- | ----------- |

    ## Sunset flags
    | name | sunsetted in | date | description |
    | ---- | ------------ | ---- | ----------- |
    | legacy_demo | #1 | 2026-04-28 | demo |
    """
)


def test_clean_tree_passes(tmp_path: Path) -> None:
    """Positive: a minimal valid synthetic tree exits 0."""
    root = _setup_fake_repo(tmp_path, yaml_body=_CLEAN_YAML, docs_body=_CLEAN_DOCS)
    result = _run(root)
    assert result.returncode == 0, f"clean tree should pass; stderr=\n{result.stderr}"


def test_undeclared_name_in_code(tmp_path: Path) -> None:
    """FR-010a: is_enabled("typo_flag") without YAML declaration fails."""
    root = _setup_fake_repo(
        tmp_path,
        yaml_body=_CLEAN_YAML,
        docs_body=_CLEAN_DOCS,
        call_site_body='async def f():\n    await is_enabled("typo_flag")\n',
    )
    result = _run(root)
    assert result.returncode == 1
    assert "'typo_flag' is referenced in code" in result.stderr
    assert "configs/feature-flags.yaml" in result.stderr


def test_orphan_active_yaml_entry(tmp_path: Path) -> None:
    """FR-010b: state=active YAML entry with no call site fails."""
    yaml = textwrap.dedent(
        """\
        flags:
          - name: orphan_active
            owner: "@andrii"
            default: false
            description: "no call site"
            state: active
        """
    )
    root = _setup_fake_repo(tmp_path, yaml_body=yaml, docs_body=_CLEAN_DOCS)
    result = _run(root)
    assert result.returncode == 1
    assert "'orphan_active' is state=active but has no call site" in result.stderr


def test_sunset_missing_docs_row(tmp_path: Path) -> None:
    """FR-011: state=sunset YAML entry with no matching docs row fails."""
    yaml = textwrap.dedent(
        """\
        flags:
          - name: retired_no_docs
            owner: "@andrii"
            default: false
            description: "sunset without docs"
            state: sunset
            sunset_pr: "#2"
            sunset_date: "2026-04-28"
        """
    )
    # docs body has no Sunset row for retired_no_docs (only legacy_demo).
    root = _setup_fake_repo(tmp_path, yaml_body=yaml, docs_body=_CLEAN_DOCS)
    result = _run(root)
    assert result.returncode == 1
    assert "'retired_no_docs' is state=sunset but missing from" in result.stderr


def test_schema_violation_in_yaml(tmp_path: Path) -> None:
    """FR-006: a YAML entry that violates the JSON Schema fails with a precise message."""
    yaml = textwrap.dedent(
        """\
        flags:
          - name: bad_state
            owner: "@andrii"
            default: false
            description: "invalid state"
            state: pending
        """
    )
    root = _setup_fake_repo(tmp_path, yaml_body=yaml, docs_body=_CLEAN_DOCS)
    result = _run(root)
    assert result.returncode == 1
    assert "configs/feature-flags.yaml" in result.stderr
    assert "pending" in result.stderr


def test_orphan_docs_row(tmp_path: Path) -> None:
    """FR-011: a docs Sunset row without a matching YAML entry fails."""
    yaml = textwrap.dedent(
        """\
        flags: []
        """
    )
    docs = textwrap.dedent(
        """\
        # Feature flags

        ## Active flags
        | name | owner | default | description |
        | ---- | ----- | ------- | ----------- |

        ## Sunset flags
        | name | sunsetted in | date | description |
        | ---- | ------------ | ---- | ----------- |
        | ghost_flag | #1 | 2026-04-28 | doc orphan |
        """
    )
    root = _setup_fake_repo(tmp_path, yaml_body=yaml, docs_body=docs)
    result = _run(root)
    assert result.returncode == 1
    assert "'ghost_flag' appears in docs/engineering/feature-flags.md" in result.stderr


def test_real_tree_is_clean() -> None:
    """The actual T05a tree must pass the hook (baseline for SC-004)."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"hook failed on the real tree; stderr=\n{result.stderr}\nstdout=\n{result.stdout}"
    )
