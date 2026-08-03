"""Determinism and JSON round-trip (spec SC-2).

The core is only auditable and replayable if the same inputs always give the
same outputs, and if the persisted document is a lossless picture of the
state (contract §1, §9).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.state_machine import (
    CandidateTurnReceived,
    OrchestratorStateError,
    Phase,
    Reconnected,
    SessionStarted,
    SessionState,
    TimerTick,
    derive_turn_id,
    initial_state,
    transition,
)

from ._builders import (
    NODE_A,
    SESSION_ID,
    T0,
    at,
    complete_assessment,
    created_state,
    deliver_reply,
    drive_to_intro,
    drive_to_tech,
    turn_uuid,
)


def _rich_state(config: OrchestratorConfig) -> SessionState:
    """A state exercising every non-default field: coverage, flags, pending ids."""
    probing = transition(
        drive_to_tech(config),
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state
    scored = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 4, 0.8),),
        red_flags=("LIKELY_CHEATING", "FACTUALLY_WRONG"),
        needs_manual_review=True,
        now=at(minutes=1, seconds=5),
    )
    delivered = deliver_reply(scored, config, now=at(minutes=1, seconds=10))
    return transition(
        delivered,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Ще відповідь", now=at(minutes=2)),
        config,
    ).new_state


def test_repeated_transitions_with_equal_inputs_are_equal(config: OrchestratorConfig) -> None:
    state = drive_to_tech(config)
    event = CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1))

    first = transition(state, event, config)
    second = transition(state, event, config)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()


def test_a_replayed_event_sequence_reaches_an_identical_state(
    config: OrchestratorConfig,
) -> None:
    assert _rich_state(config) == _rich_state(config)


def test_session_state_round_trips_through_json(config: OrchestratorConfig) -> None:
    state = _rich_state(config)

    document: Any = json.loads(state.model_dump_json())
    restored = SessionState.model_validate(document)

    assert restored == state
    assert restored.model_dump_json() == state.model_dump_json()


def test_round_trip_preserves_coverage_and_pending_bookkeeping(
    config: OrchestratorConfig,
) -> None:
    state = _rich_state(config)

    restored = SessionState.model_validate(json.loads(state.model_dump_json()))

    assert restored.tech.coverage == state.tech.coverage
    assert restored.tech.pending_assessments == state.tech.pending_assessments
    assert restored.tech.assessment_focus == state.tech.assessment_focus
    assert restored.pending_command == state.pending_command
    assert restored.plan == state.plan


def test_a_resumed_state_re_issues_the_identical_command(config: OrchestratorConfig) -> None:
    """§6.9 + §9: rehydrate → ``Reconnected`` → byte-identical re-issue."""
    live = drive_to_intro(config)
    rehydrated = SessionState.model_validate(json.loads(live.model_dump_json()))

    from_live = transition(live, Reconnected(now=at(minutes=1)), config)
    from_disk = transition(rehydrated, Reconnected(now=at(minutes=1)), config)

    assert from_live.commands == from_disk.commands


def test_command_ids_are_uuid5_over_the_structural_counter(
    config: OrchestratorConfig,
) -> None:
    intro = transition(created_state(config), SessionStarted(now=T0), config)
    tech = transition(
        intro.new_state,
        CandidateTurnReceived(turn_id=turn_uuid(0), text="Готовий", now=T0),
        config,
    )

    assert intro.new_state.turn_seq == 1
    assert tech.new_state.turn_seq == 2
    assert intro.commands[0].turn_id == derive_turn_id(SESSION_ID, "turn/0")  # type: ignore[union-attr]  # EmitScriptedOpening, asserted by edge 1 test
    assert tech.commands[0].turn_id == derive_turn_id(SESSION_ID, "turn/1")  # type: ignore[union-attr]  # RunInterviewer, asserted by edge 3 test


def test_initial_state_stamps_the_configured_schema_version(
    config: OrchestratorConfig,
) -> None:
    state = initial_state(session_id=SESSION_ID, plan_input={}, config=config)

    assert state.state_schema_version == config.state_schema_version
    assert state.phase is Phase.CREATED
    assert state.plan is None


def test_evolving_an_unknown_field_fails_loudly(config: OrchestratorConfig) -> None:
    """The internal ``_evolve`` guard: a typo'd field name is never silent."""
    from app.backend.orchestrator.state_machine import _evolve

    with pytest.raises(OrchestratorStateError, match="unknown field"):
        _evolve(created_state(config), phaze=Phase.TECH)


def test_a_tech_state_without_a_plan_fails_loudly(config: OrchestratorConfig) -> None:
    """Hand-built impossible states raise instead of guessing."""
    broken = created_state(config).model_copy(
        update={"phase": Phase.TECH, "awaiting": "candidate", "plan": None}
    )

    with pytest.raises(OrchestratorStateError, match="without a validated plan"):
        transition(
            broken,
            CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
            config,
        )


def test_an_untabulated_event_is_a_no_op(config: OrchestratorConfig) -> None:
    created = created_state(config)

    result = transition(created, TimerTick(now=at(minutes=1)), config)

    assert result.new_state == created
    assert result.commands == ()
