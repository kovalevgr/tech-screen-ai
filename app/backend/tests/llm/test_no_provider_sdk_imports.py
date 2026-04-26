"""Subprocess-based test for the static SDK-import guardrail (T030).

Maps to FR-014, SC-003.

The guardrail script ``scripts/check-no-provider-sdk-imports.sh``
greps the entire ``app/backend/`` tree for forbidden ``import`` /
``from`` statements that reach into a model-provider SDK
(``vertexai``, ``google.genai``, ``google.cloud.aiplatform``,
``anthropic``, ``openai``). The two underscore-prefixed wrapper
backends are the only allowlisted call sites.

This test:

1. Invokes the script on the tree as it stands at the start of the
   run — it MUST exit 0 (no violations in the post-T04 tree).
2. Plants a temporary ``app/backend/services/_demo.py`` file
   containing ``import vertexai`` — re-runs the script, asserts exit
   1, asserts the violation file path appears in stderr.
3. Cleans up via ``try/finally`` (also removes the ``services/``
   directory if this test created it).

The script is invoked from the repo root because its allowlist uses
repo-relative paths.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCRIPT: Path = _REPO_ROOT / "scripts" / "check-no-provider-sdk-imports.sh"
_TMP_FILE: Path = _REPO_ROOT / "app" / "backend" / "services" / "_demo.py"


def _run_script() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        cwd=str(_REPO_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def test_guardrail_passes_on_clean_tree_and_blocks_planted_violation() -> None:
    """End-to-end exercise of the static SDK-import guardrail."""
    if not _SCRIPT.is_file():
        pytest.fail(f"guardrail script missing at {_SCRIPT}; T019 must land it")

    # 1. Clean tree — script must exit 0.
    clean = _run_script()
    assert clean.returncode == 0, (
        f"guardrail unexpectedly failed on clean tree:\n"
        f"stdout={clean.stdout!r}\nstderr={clean.stderr!r}"
    )

    # 2. Plant a violation — re-run, expect exit 1 + violation in stderr.
    services_dir = _TMP_FILE.parent
    created_services_dir = not services_dir.exists()
    try:
        services_dir.mkdir(parents=True, exist_ok=True)
        _TMP_FILE.write_text(
            "# T030: planted violation. The guardrail must catch this line.\nimport vertexai\n",
            encoding="utf-8",
        )
        violated = _run_script()
        assert violated.returncode == 1, (
            f"guardrail must reject the planted violation; got "
            f"returncode={violated.returncode}\n"
            f"stdout={violated.stdout!r}\nstderr={violated.stderr!r}"
        )
        # The script writes "ERROR:" + the violating file path to stderr.
        assert "_demo.py" in violated.stderr, (
            f"expected the violation file in stderr, got: {violated.stderr!r}"
        )
        assert "vertexai" in violated.stderr, (
            f"expected the violating import in stderr, got: {violated.stderr!r}"
        )
    finally:
        # 3. Cleanup — remove the planted file (and the services/ dir if
        # this test was responsible for creating it).
        if _TMP_FILE.exists():
            _TMP_FILE.unlink()
        if created_services_dir and services_dir.exists():
            try:
                services_dir.rmdir()
            except OSError:
                # Directory was populated by something else — leave it.
                pass

    # 4. Sanity — re-run after cleanup; clean tree again.
    final = _run_script()
    assert final.returncode == 0, (
        f"after cleanup the guardrail should pass again; got stderr={final.stderr!r}"
    )
