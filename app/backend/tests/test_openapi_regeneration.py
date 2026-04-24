"""Guard against drift between the live FastAPI app and the committed OpenAPI.

Running the full test suite is how contributors (and CI, via T10) learn they
have forgotten to regenerate ``app/backend/openapi.yaml``. On drift, the
failure message includes a short unified diff so the reviewer can diagnose
without re-running the generator manually.
"""

from __future__ import annotations

import difflib

from app.backend.generate_openapi import OPENAPI_PATH, build_yaml_bytes


def test_committed_openapi_matches_regenerated_bytes() -> None:
    regenerated = build_yaml_bytes()
    committed = OPENAPI_PATH.read_bytes()
    if committed == regenerated:
        return
    diff = "\n".join(
        list(
            difflib.unified_diff(
                committed.decode("utf-8").splitlines(),
                regenerated.decode("utf-8").splitlines(),
                fromfile=f"{OPENAPI_PATH} (committed)",
                tofile=f"{OPENAPI_PATH} (regenerated)",
                lineterm="",
            )
        )[:40]
    )
    raise AssertionError(
        "openapi.yaml is out of sync with the live FastAPI app. Run "
        "`uv run python -m app.backend.generate_openapi` and commit the result.\n"
        f"{diff}"
    )
