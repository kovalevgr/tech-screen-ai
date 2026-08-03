"""Encode/decode of the persisted ``session_state`` document (contract §9).

The DB round trip lives in ``app/backend/tests/db/test_session_state_persistence.py``
(skipped without a reachable ``DATABASE_URL``); everything provable without a
database is proved here.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.persistence import (
    SessionStateDecodeError,
    StateSchemaVersionError,
    decode_session_state,
    encode_session_state,
)
from app.backend.orchestrator.state_machine import (
    CandidateTurnReceived,
    SessionStarted,
    transition,
)

from ._builders import NODE_A, T0, at, complete_assessment, created_state, drive_to_tech, turn_uuid


def _stateful(config: OrchestratorConfig) -> Any:
    """A TECH state carrying coverage, a pending command and a pending assessment."""
    probing = transition(
        drive_to_tech(config),
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state
    return complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 3, 0.7),),
        now=at(minutes=1, seconds=5),
    )


def test_encoded_state_is_json_serialisable(config: OrchestratorConfig) -> None:
    document = encode_session_state(_stateful(config))

    # A JSONB column can only take what json.dumps accepts.
    assert json.loads(json.dumps(document)) == document


def test_encode_decode_is_lossless(config: OrchestratorConfig) -> None:
    state = _stateful(config)

    assert (
        decode_session_state(
            encode_session_state(state), expected_version=state.state_schema_version
        )
        == state
    )


def test_a_created_state_round_trips_before_the_session_starts(
    config: OrchestratorConfig,
) -> None:
    created = created_state(config)

    restored = decode_session_state(
        encode_session_state(created), expected_version=config.state_schema_version
    )

    assert restored == created
    assert restored.plan is None
    assert restored.plan_input == created.plan_input


def test_a_started_state_keeps_both_the_raw_and_typed_plan(
    config: OrchestratorConfig,
) -> None:
    started = transition(created_state(config), SessionStarted(now=T0), config).new_state

    restored = decode_session_state(
        encode_session_state(started), expected_version=config.state_schema_version
    )

    assert restored.plan is not None
    assert restored.plan_input == started.plan_input


def test_a_foreign_schema_version_fails_loudly(config: OrchestratorConfig) -> None:
    document = encode_session_state(created_state(config))
    document["state_schema_version"] = config.state_schema_version + 1

    with pytest.raises(StateSchemaVersionError, match="explicit migration"):
        decode_session_state(document, expected_version=config.state_schema_version)


@pytest.mark.parametrize("stored", [None, "1", True, 1.0])
def test_a_missing_or_non_integer_schema_version_fails_loudly(
    config: OrchestratorConfig, stored: object
) -> None:
    document = encode_session_state(created_state(config))
    document["state_schema_version"] = stored

    with pytest.raises(StateSchemaVersionError, match="integer state_schema_version"):
        decode_session_state(document, expected_version=config.state_schema_version)


def test_a_non_object_document_is_rejected(config: OrchestratorConfig) -> None:
    with pytest.raises(SessionStateDecodeError, match="must be a JSON object"):
        decode_session_state(["nope"], expected_version=config.state_schema_version)


def test_a_structurally_broken_document_is_rejected(config: OrchestratorConfig) -> None:
    document = encode_session_state(created_state(config))
    document["phase"] = "not-a-phase"

    with pytest.raises(SessionStateDecodeError, match="not a valid state"):
        decode_session_state(document, expected_version=config.state_schema_version)
