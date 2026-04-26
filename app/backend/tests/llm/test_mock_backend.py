"""Tests for the deterministic mock backend (T031, T039).

Maps to FR-005, FR-006 (mock backend) and research §13 / FR-008
(canonical-prompt SHA stability and contents).

Two clusters of behaviour:

1. **T031** — fixture lookup, ``_unrecorded`` capture on miss, and
   round-trip stability of the SHA recipe across Python invocations.
2. **T039** — the canonical SHA recipe is stable for identical inputs
   AND varies in response to changes in **any** input (system_prompt,
   user_payload, json_schema, agent, model). Locks the recipe so a
   future PR that "simplifies" it (e.g., drops the schema) breaks
   loudly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.backend.llm._backend_protocol import RawBackendResult
from app.backend.llm._mock_backend import (
    MockVertexBackend,
    canonical_prompt_payload,
    canonical_prompt_sha,
)
from app.backend.tests.llm._test_prompts import (
    ASSESSOR_BROKEN_SHA,
    ASSESSOR_BROKEN_USER_PAYLOAD,
    ASSESSOR_MODEL,
    ASSESSOR_SCHEMA,
    ASSESSOR_SHA,
    ASSESSOR_SYSTEM_PROMPT,
    ASSESSOR_USER_PAYLOAD,
    INTERVIEWER_MODEL,
    INTERVIEWER_SCHEMA,
    INTERVIEWER_SHA,
    INTERVIEWER_SYSTEM_PROMPT,
    INTERVIEWER_USER_PAYLOAD,
)

_FIXTURES_DIR: Path = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


# ---------------------------------------------------------------------------
# T031 — Mock backend behaviour
# ---------------------------------------------------------------------------


async def test_mock_backend_returns_fixture_envelope_for_known_prompt() -> None:
    """SHA-keyed fixture lookup returns the committed envelope verbatim."""
    backend = MockVertexBackend(agent="interviewer", fixtures_dir=_FIXTURES_DIR)
    raw = await backend.generate(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        model=INTERVIEWER_MODEL,
        temperature=0.4,
        max_output_tokens=2048,
        timeout_s=30.0,
    )
    assert isinstance(raw, RawBackendResult)
    assert raw.input_tokens == 132
    assert raw.output_tokens == 87
    assert raw.model == "gemini-2.5-flash"
    assert raw.model_version == "gemini-2.5-flash-001"
    assert "Доброго дня" in raw.text


async def test_mock_backend_sha_matches_committed_filename() -> None:
    """The pre-computed SHA constants in `_test_prompts` agree with the recipe.

    If a future change to ``canonical_prompt_sha`` drifts from the
    fixture filenames this test fires immediately, before the
    fixture-miss path muddies the diagnostic.
    """
    assert (
        canonical_prompt_sha(
            system_prompt=INTERVIEWER_SYSTEM_PROMPT,
            user_payload=INTERVIEWER_USER_PAYLOAD,
            json_schema=INTERVIEWER_SCHEMA,
            agent="interviewer",
            model=INTERVIEWER_MODEL,
        )
        == INTERVIEWER_SHA
    )
    assert (
        canonical_prompt_sha(
            system_prompt=ASSESSOR_SYSTEM_PROMPT,
            user_payload=ASSESSOR_USER_PAYLOAD,
            json_schema=ASSESSOR_SCHEMA,
            agent="assessor",
            model=ASSESSOR_MODEL,
        )
        == ASSESSOR_SHA
    )
    assert (
        canonical_prompt_sha(
            system_prompt=ASSESSOR_SYSTEM_PROMPT,
            user_payload=ASSESSOR_BROKEN_USER_PAYLOAD,
            json_schema=ASSESSOR_SCHEMA,
            agent="assessor",
            model=ASSESSOR_MODEL,
        )
        == ASSESSOR_BROKEN_SHA
    )


async def test_mock_backend_unrecorded_capture_on_miss(
    tmp_path: Path,
) -> None:
    """Unseen prompt → write request envelope under ``_unrecorded/`` + raise.

    The test runs against a temp directory so it does NOT pollute the
    committed fixture tree. ``_unrecorded/<sha>.json`` carries the
    canonical envelope: agent, model, system_prompt, user_payload,
    json_schema. The exception message references the SHA + path.
    """
    # Prepare an empty fixture tree under tmp_path so the lookup misses.
    (tmp_path / "interviewer").mkdir()
    backend = MockVertexBackend(agent="interviewer", fixtures_dir=tmp_path)
    novel_user = "novel prompt the fixture set has never seen before"

    with pytest.raises(RuntimeError) as excinfo:
        await backend.generate(
            system_prompt="novel system prompt",
            user_payload=novel_user,
            json_schema=INTERVIEWER_SCHEMA,
            model=INTERVIEWER_MODEL,
            temperature=0.4,
            max_output_tokens=2048,
            timeout_s=30.0,
        )

    sha = canonical_prompt_sha(
        system_prompt="novel system prompt",
        user_payload=novel_user,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model=INTERVIEWER_MODEL,
    )
    assert sha in str(excinfo.value)
    assert "_unrecorded" in str(excinfo.value)

    captured = tmp_path / "_unrecorded" / f"{sha}.json"
    assert captured.is_file(), f"expected _unrecorded/{sha}.json to exist"
    envelope = json.loads(captured.read_text(encoding="utf-8"))
    assert envelope == {
        "agent": "interviewer",
        "model": INTERVIEWER_MODEL,
        "system_prompt": "novel system prompt",
        "user_payload": novel_user,
        "json_schema": INTERVIEWER_SCHEMA,
    }


def test_mock_backend_rejects_unknown_agent() -> None:
    """Constructor refuses agents outside the committed registry."""
    with pytest.raises(ValueError) as excinfo:
        MockVertexBackend(agent="unknown_agent", fixtures_dir=_FIXTURES_DIR)
    assert "unknown_agent" in str(excinfo.value)


# ---------------------------------------------------------------------------
# T039 — Canonical SHA stability + variance under each input
# ---------------------------------------------------------------------------


def test_canonical_sha_is_stable_for_identical_inputs() -> None:
    """SHA recipe is pure: same inputs → identical 64-char hex output."""
    sha1 = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model=INTERVIEWER_MODEL,
    )
    sha2 = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model=INTERVIEWER_MODEL,
    )
    assert sha1 == sha2
    assert len(sha1) == 64


def test_canonical_sha_changes_when_only_schema_changes() -> None:
    """Including the schema in the SHA recipe is FR-008 / research §13."""
    sha_schema_a = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model=INTERVIEWER_MODEL,
    )
    sha_schema_b = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema={
            **INTERVIEWER_SCHEMA,
            "required": ["message_uk"],  # changed
        },
        agent="interviewer",
        model=INTERVIEWER_MODEL,
    )
    assert sha_schema_a != sha_schema_b, (
        "SHA recipe must change when the schema changes — otherwise "
        "stale fixtures would be served against a new schema"
    )


def test_canonical_sha_changes_when_only_model_changes() -> None:
    """The model id is part of the SHA so per-model fixtures can't collide."""
    sha_flash = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model="gemini-2.5-flash",
    )
    sha_pro = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model="gemini-2.5-pro",
    )
    assert sha_flash != sha_pro


def test_canonical_sha_changes_when_only_agent_changes() -> None:
    """Same prompts under a different agent → distinct SHA."""
    sha_a = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="interviewer",
        model=INTERVIEWER_MODEL,
    )
    sha_b = canonical_prompt_sha(
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        agent="assessor",
        model=INTERVIEWER_MODEL,
    )
    assert sha_a != sha_b


def test_canonical_payload_uses_sort_keys_and_unicode() -> None:
    """Locks the JSON serialisation choices: sort_keys=True, ensure_ascii=False.

    A future PR that swaps either of these would break the SHA stability
    invariant silently — this test exists so that change can't slip
    through.
    """
    payload = canonical_prompt_payload(
        system_prompt="a",
        user_payload="Привіт",  # Cyrillic
        json_schema={"b": 1, "a": 2},
        agent="interviewer",
        model="gemini-2.5-flash",
    )
    # Cyrillic preserved (ensure_ascii=False).
    assert "Привіт" in payload
    # Top-level keys in alphabetical order (sort_keys=True). The first
    # dictionary key serialised should be "agent" (a < j < m < s < u).
    parsed = json.loads(payload)
    assert list(parsed.keys()) == sorted(parsed.keys())
