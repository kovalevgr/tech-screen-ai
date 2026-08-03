"""The two T21/T22 contracts vs. what the code actually exposes (§14).

``docs/contracts/dev-session-api.yaml`` and
``docs/contracts/turn-trace.schema.json`` were committed before the backend and
frontend streams forked. These tests are the standing check that neither side
drifted: the generated ``app/backend/openapi.yaml`` must carry the contract's
paths and operations, and the trace row the API returns must carry the
contract's fields.

No database needed — this is a static comparison of committed artefacts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, get_args

import yaml

from app.backend.db.models.audit import TurnTrace
from app.backend.llm.persistent_trace import WrapperOutcome
from app.backend.services.dev_session import SessionView, TraceRow, TranscriptEntry, TurnResult

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_API_CONTRACT: Path = _REPO_ROOT / "docs" / "contracts" / "dev-session-api.yaml"
_ROW_CONTRACT: Path = _REPO_ROOT / "docs" / "contracts" / "turn-trace.schema.json"
_GENERATED: Path = _REPO_ROOT / "app" / "backend" / "openapi.yaml"

_HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete"})


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def _operations(document: dict[str, Any], prefix: str = "") -> dict[tuple[str, str], str]:
    """Map ``(path, method)`` → ``operationId`` for the paths under ``prefix``."""
    return {
        (path, method): operation["operationId"]
        for path, item in document["paths"].items()
        if path.startswith(prefix)
        for method, operation in item.items()
        if method in _HTTP_METHODS
    }


def _row_schema() -> dict[str, Any]:
    loaded: Any = json.loads(_ROW_CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


# ---------------------------------------------------------------------------
# dev-session-api.yaml
# ---------------------------------------------------------------------------


def test_the_generated_openapi_carries_every_contract_operation() -> None:
    contract = _operations(_load_yaml(_API_CONTRACT))
    generated = _operations(_load_yaml(_GENERATED), prefix="/api/dev/")

    assert generated == contract


def test_the_session_view_matches_the_contract_shape() -> None:
    contract = _load_yaml(_API_CONTRACT)["components"]["schemas"]["SessionView"]

    assert set(SessionView.model_fields) == set(contract["properties"])
    required = {name for name, field in SessionView.model_fields.items() if field.is_required()}
    assert required == set(contract["required"])


def test_the_transcript_entry_matches_the_contract_shape() -> None:
    contract = _load_yaml(_API_CONTRACT)["components"]["schemas"]["SessionView"]["properties"][
        "transcript"
    ]["items"]

    assert set(TranscriptEntry.model_fields) == set(contract["properties"])
    assert set(contract["required"]) <= set(TranscriptEntry.model_fields)


def test_the_turn_response_matches_the_contract_shape() -> None:
    contract = _load_yaml(_API_CONTRACT)["paths"]["/api/dev/sessions/{session_id}/turns"]["post"][
        "responses"
    ]["200"]["content"]["application/json"]["schema"]

    assert set(TurnResult.model_fields) == set(contract["properties"])
    assert set(contract["required"]) == set(TurnResult.model_fields)


def test_the_dev_routes_are_the_only_api_dev_paths() -> None:
    """Nothing else may squat under the dev-only prefix."""
    generated = _load_yaml(_GENERATED)
    dev_paths = {path for path in generated["paths"] if path.startswith("/api/dev")}

    assert dev_paths == set(_load_yaml(_API_CONTRACT)["paths"])


# ---------------------------------------------------------------------------
# turn-trace.schema.json
# ---------------------------------------------------------------------------


def test_the_trace_row_model_matches_the_row_contract() -> None:
    contract = _row_schema()

    assert set(TraceRow.model_fields) == set(contract["properties"])


def test_every_contract_required_field_is_required_on_the_model() -> None:
    contract = _row_schema()
    required = {name for name, field in TraceRow.model_fields.items() if field.is_required()}

    assert set(contract["required"]) <= required


def test_the_turn_trace_table_has_a_column_per_contract_property() -> None:
    """The ORM mapping is the static half of the DB test in tests/db/."""
    contract = _row_schema()
    columns = set(TurnTrace.__table__.columns.keys())

    # `interview_session_id` is the table's name for the contract's session
    # link; everything else is named identically.
    assert set(contract["properties"]) <= columns


def test_the_wrapper_outcome_enum_matches_the_contract() -> None:
    contract = _row_schema()["properties"]["wrapper_outcome"]

    assert set(get_args(WrapperOutcome)) == {v for v in contract["enum"] if v is not None}
