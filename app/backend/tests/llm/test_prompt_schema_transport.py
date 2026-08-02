"""Offline regression: every committed prompt schema must transport verbatim.

Blocker context (030): the previously pinned ``google-genai 0.8.0``
rejected ALL committed ``prompts/<agent>/<version>/schema.json`` files
pre-network — its ``response_schema`` transformer (``t_schema``) forbade
standard JSON-Schema keywords (``$schema``, ``$id``,
``additionalProperties``, ``"type": [..., "null"]`` unions, ``const``),
and the failure was masked as ``VertexUpstreamUnavailableError``. The
fix transports the raw document via ``response_json_schema`` (SDK ≥
1.22), which the SDK passes through untouched as ``responseJsonSchema``.

This test pins that behaviour against the exact installed SDK version:

- Parametrized over ``sorted(prompts/*/v*/schema.json)`` so every current
  AND future prompt schema is covered automatically.
- Exercises the SDK's actual pre-network request-build path for Vertex
  (``types.GenerateContentConfig`` construction +
  ``models._GenerateContentParameters_to_vertex``) — the exact code that
  runs before any network I/O in ``generate_content``. A stub namespace
  stands in for the api client; no network, no ADC, no real client.
- MUST FAIL if someone commits a schema the pinned SDK cannot transport,
  or if an SDK bump reintroduces client-side schema mutation.

This file is allowlisted in ``scripts/check-no-provider-sdk-imports.sh``:
it deliberately imports the provider SDK to pin its transport behaviour.
Production code outside ``app/backend/llm/_real_backend.py`` still must
not.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import models as genai_models
from google.genai import types as genai_types

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_SCHEMA_PATHS: list[Path] = sorted((_REPO_ROOT / "prompts").glob("*/v*/schema.json"))


def _case_id(path: Path) -> str:
    """`prompts/assessor/v0001/schema.json` → `assessor-v0001`."""
    return f"{path.parent.parent.name}-{path.parent.name}"


def test_schema_inventory_covers_all_three_agents() -> None:
    """The glob must find the three committed agent contracts (guards drift)."""
    agents = {path.parent.parent.name for path in _SCHEMA_PATHS}
    assert {"interviewer", "assessor", "planner"} <= agents, (
        f"expected schema.json for all three agents under prompts/, found: {sorted(agents)}"
    )


@pytest.mark.parametrize("schema_path", _SCHEMA_PATHS, ids=_case_id)
def test_prompt_schema_transports_verbatim_pre_network(schema_path: Path) -> None:
    """The committed schema survives the SDK's pre-network build unmutated.

    Mirrors exactly what ``RealVertexBackend.generate`` hands to the SDK
    (``response_mime_type`` + ``response_json_schema``), then runs the
    Vertex request converter the SDK invokes before any network I/O and
    asserts the schema lands on the wire-shaped request verbatim.
    """
    schema: dict[str, Any] = json.loads(schema_path.read_text(encoding="utf-8"))

    # Step 1 — config construction (first pre-network validation point).
    config = genai_types.GenerateContentConfig(
        system_instruction="offline schema-transport check",
        temperature=0.0,
        max_output_tokens=16,
        response_mime_type="application/json",
        # deepcopy so the verbatim assertion below cannot be satisfied by
        # aliasing — a mutating SDK would mutate the copy, not `schema`.
        response_json_schema=copy.deepcopy(schema),
    )

    # Step 2 — the Vertex request converter (second and final pre-network
    # step; 0.8.0's `t_schema` rejection fired at this layer). The
    # converter only reads `.vertexai` off the api client, so a stub
    # namespace keeps the test fully offline.
    params = genai_types._GenerateContentParameters(
        model="gemini-2.5-flash",
        contents="ping",
        config=config,
    )
    stub_api_client: Any = SimpleNamespace(vertexai=True)
    request = genai_models._GenerateContentParameters_to_vertex(stub_api_client, params)

    generation_config = request["generationConfig"]
    assert generation_config["responseMimeType"] == "application/json"
    assert generation_config["responseJsonSchema"] == schema, (
        f"{schema_path}: schema was mutated in pre-network transport — "
        "the SDK no longer passes response_json_schema through verbatim"
    )
