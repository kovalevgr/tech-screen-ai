"""The owner's 2/1/0 adjudication table (contract §5) and the §6 policies.

Covers the full matrix required by spec FR-032-9 — {ANSWERED, CLARIFY, NONE}
× {assessment present, pending → ``proceed_planned``, failed} — plus the
boundary and distinctness rules the contract calls out by name:

- ``confidence`` exactly at ``confidence_min`` passes (§5, inclusive ≥);
- probe-budget and competency-time exhaustion force NONE (§5, §6.5);
- an evidence-backed level 0 and an empty ``assessments`` array both reach
  NONE but persist as DISTINCT coverage markers (§5);
- multi-seed iteration: ANSWERED on seed k moves to seed k+1 while
  competency time remains (§4).
"""

from __future__ import annotations

import pytest

from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.state_machine import (
    AssessmentFailed,
    CandidateTurnReceived,
    CoverageCell,
    InterviewerReplyReady,
    Phase,
    RecordGap,
    TimerTick,
    adjudicate,
    transition,
)

from ._builders import (
    NODE_A,
    NODE_B,
    at,
    competency,
    complete_assessment,
    deliver_reply,
    drive_to_tech,
    interviewer_output,
    make_plan,
    pending_interviewer,
    turn_uuid,
)

# A competency budget of 12 minutes; every scenario below is evaluated one
# minute in, so 660 s remain unless the test says otherwise.
PLENTY_OF_TIME = 660.0


# ---------------------------------------------------------------------------
# The matrix: verdict × evidence
# ---------------------------------------------------------------------------


def test_answered_with_a_present_assessment_at_or_above_target(
    config: OrchestratorConfig,
) -> None:
    verdict = adjudicate(
        cell=CoverageCell(best_level=3, best_confidence=0.8, latest_level=3, latest_confidence=0.8),
        target_level=3,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "ANSWERED"
    assert verdict.basis == "assessment"
    assert verdict.gap_marker is None


def test_answered_is_unreachable_while_the_assessment_is_pending(
    config: OrchestratorConfig,
) -> None:
    """§6.1 ``proceed_planned``: no completed assessment can never mean ANSWERED."""
    verdict = adjudicate(
        cell=None,
        target_level=1,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "CLARIFY"
    assert verdict.basis == "pending"


def test_answered_is_unreachable_after_an_assessment_failure(
    config: OrchestratorConfig,
) -> None:
    """§6.3: a failed assessment reads as "no assessment available"."""
    verdict = adjudicate(
        cell=CoverageCell(assessment_failed=True),
        target_level=1,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "CLARIFY"
    assert verdict.basis == "failed"


def test_clarify_with_a_present_assessment_below_target(config: OrchestratorConfig) -> None:
    verdict = adjudicate(
        cell=CoverageCell(best_level=2, best_confidence=0.9, latest_level=2, latest_confidence=0.9),
        target_level=3,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "CLARIFY"
    assert verdict.basis == "assessment"


def test_none_with_a_present_level_zero_assessment(config: OrchestratorConfig) -> None:
    """§5: the LATEST assessment at level 0 short-circuits the probe budget."""
    verdict = adjudicate(
        cell=CoverageCell(best_level=2, best_confidence=0.9, latest_level=0, latest_confidence=0.9),
        target_level=3,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "NONE"
    assert verdict.gap_marker == "level_zero"
    assert verdict.basis == "assessment"


def test_none_while_pending_once_the_probe_budget_is_gone(config: OrchestratorConfig) -> None:
    verdict = adjudicate(
        cell=None,
        target_level=3,
        probes_used=config.adjudication.max_probes_per_competency,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "NONE"
    assert verdict.basis == "pending"
    assert verdict.gap_marker == "gap_budget_exhausted"


def test_none_after_a_failure_once_the_probe_budget_is_gone(config: OrchestratorConfig) -> None:
    verdict = adjudicate(
        cell=CoverageCell(assessment_failed=True),
        target_level=3,
        probes_used=config.adjudication.max_probes_per_competency,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "NONE"
    assert verdict.basis == "failed"
    assert verdict.gap_marker == "gap_budget_exhausted"


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


def test_confidence_exactly_at_confidence_min_passes(config: OrchestratorConfig) -> None:
    """§5's ``confidence >= confidence_min`` is inclusive at the boundary."""
    boundary = config.adjudication.confidence_min

    verdict = adjudicate(
        cell=CoverageCell(
            best_level=3, best_confidence=boundary, latest_level=3, latest_confidence=boundary
        ),
        target_level=3,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "ANSWERED"


def test_confidence_just_below_confidence_min_does_not_answer(
    config: OrchestratorConfig,
) -> None:
    below = config.adjudication.confidence_min - 0.01

    verdict = adjudicate(
        cell=CoverageCell(
            best_level=5, best_confidence=below, latest_level=5, latest_confidence=below
        ),
        target_level=3,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "CLARIFY"


def test_probe_budget_exhaustion_forces_none(config: OrchestratorConfig) -> None:
    verdict = adjudicate(
        cell=CoverageCell(best_level=1, best_confidence=0.9, latest_level=1, latest_confidence=0.9),
        target_level=4,
        probes_used=config.adjudication.max_probes_per_competency,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert verdict.verdict == "NONE"
    assert verdict.gap_marker == "gap_budget_exhausted"


def test_competency_time_at_min_probe_seconds_forces_none(config: OrchestratorConfig) -> None:
    """§6.5: no point starting a probe we cannot hear the answer to."""
    verdict = adjudicate(
        cell=None,
        target_level=3,
        probes_used=0,
        seconds_remaining=float(config.adjudication.min_probe_seconds),
        config=config,
    )

    assert verdict.verdict == "NONE"
    assert verdict.gap_marker == "gap_budget_exhausted"


def test_not_assessable_needs_at_least_one_probe_before_it_closes(
    config: OrchestratorConfig,
) -> None:
    empty = CoverageCell(gap_not_assessable=True)

    without_probe = adjudicate(
        cell=empty,
        target_level=3,
        probes_used=0,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )
    with_probe = adjudicate(
        cell=empty,
        target_level=3,
        probes_used=1,
        seconds_remaining=PLENTY_OF_TIME,
        config=config,
    )

    assert without_probe.verdict == "CLARIFY"
    assert with_probe.verdict == "NONE"
    assert with_probe.gap_marker == "gap_not_assessable"
    assert with_probe.basis == "not_assessable"


# ---------------------------------------------------------------------------
# Distinct coverage markers (§5) — level 0 vs an empty assessments array
# ---------------------------------------------------------------------------


def test_level_zero_and_empty_assessments_are_distinct_coverage_markers(
    config: OrchestratorConfig,
) -> None:
    two_nodes = make_plan(competencies=[competency(NODE_A), competency(NODE_B)])
    tech = drive_to_tech(config, two_nodes)
    probing = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state

    evidence_backed_none = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 0, 0.9),),
        now=at(minutes=1, seconds=5),
    )
    not_assessable = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=(),
        now=at(minutes=1, seconds=5),
    )

    zero_cell = evidence_backed_none.tech.coverage[NODE_A]
    empty_cell = not_assessable.tech.coverage[NODE_A]

    assert zero_cell.latest_level == 0
    assert zero_cell.gap_not_assessable is False
    assert empty_cell.latest_level is None
    assert empty_cell.gap_not_assessable is True
    assert zero_cell != empty_cell


def test_budget_exhaustion_marks_the_cell_and_records_the_gap(
    config: OrchestratorConfig,
) -> None:
    tech = drive_to_tech(config)
    # Spend the whole probe budget without any assessment ever completing.
    state = tech
    turn = 1
    for probe in range(config.adjudication.max_probes_per_competency):
        state = transition(
            state,
            CandidateTurnReceived(
                turn_id=turn_uuid(turn), text="Відповідь", now=at(minutes=probe + 1)
            ),
            config,
        ).new_state
        state = deliver_reply(state, config, now=at(minutes=probe + 1, seconds=5))
        turn += 1

    result = transition(
        state,
        CandidateTurnReceived(turn_id=turn_uuid(turn), text="Ще відповідь", now=at(minutes=4)),
        config,
    )

    gaps = [command for command in result.commands if isinstance(command, RecordGap)]
    assert [gap.marker for gap in gaps] == ["gap_budget_exhausted"]
    assert result.new_state.tech.coverage[NODE_A].gap_budget_exhausted is True
    assert pending_interviewer(result.new_state).move == "close_competency"


# ---------------------------------------------------------------------------
# Multi-seed iteration (§4)
# ---------------------------------------------------------------------------


def test_answered_moves_to_the_next_seed_while_competency_time_remains(
    config: OrchestratorConfig,
) -> None:
    two_seeds = make_plan(
        competencies=[competency(NODE_A, seeds=("seed-1", "seed-2")), competency(NODE_B)]
    )
    tech = drive_to_tech(config, two_seeds)
    probing = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state
    scored = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 4, 0.9),),
        now=at(minutes=1, seconds=5),
    )
    ready = deliver_reply(scored, config, now=at(minutes=1, seconds=10))

    result = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Друга відповідь", now=at(minutes=2)),
        config,
    )

    assert result.new_state.tech.competency_index == 0  # same competency
    assert result.new_state.tech.seed_index == 1
    issued = pending_interviewer(result.new_state)
    assert issued.move == "acknowledge_and_transition"
    assert issued.move_context["next_seed_question_uk"] == "seed-2"
    assert issued.competency_node_id == NODE_A


def test_answered_skips_the_next_seed_when_competency_time_is_gone(
    config: OrchestratorConfig,
) -> None:
    two_seeds = make_plan(
        competencies=[
            competency(NODE_A, minutes=2, seeds=("seed-1", "seed-2")),
            competency(NODE_B),
        ]
    )
    tech = drive_to_tech(config, two_seeds)
    probing = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(seconds=30)),
        config,
    ).new_state
    scored = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 4, 0.9),),
        now=at(seconds=35),
    )
    ready = deliver_reply(scored, config, now=at(seconds=40))

    result = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Друга відповідь", now=at(minutes=3)),
        config,
    )

    assert result.new_state.tech.competency_index == 1
    assert result.new_state.tech.seed_index == 0


# ---------------------------------------------------------------------------
# §6.1 / §6.8 — the async assessor never blocks and is never too late
# ---------------------------------------------------------------------------


def test_pending_assessment_never_blocks_the_next_move(config: OrchestratorConfig) -> None:
    """§6.1 ``proceed_planned``: issue the planned probe, do not wait."""
    tech = drive_to_tech(config)

    result = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    )

    assert result.new_state.tech.pending_assessments == (turn_uuid(1),)
    assert pending_interviewer(result.new_state).move == "depth_probe"


def test_late_assessment_updates_coverage_after_the_phase_advanced(
    config: OrchestratorConfig,
) -> None:
    """§6.8: a late result lands in coverage even once the machine is in QA."""
    single = make_plan(competencies=[competency(NODE_A)])
    tech = drive_to_tech(config, single)
    probing = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state
    scored = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 4, 0.9),),
        now=at(minutes=1, seconds=5),
    )
    ready = deliver_reply(scored, config, now=at(minutes=1, seconds=10))
    in_qa = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Друга відповідь", now=at(minutes=2)),
        config,
    ).new_state
    assert in_qa.phase is Phase.QA
    assert in_qa.tech.pending_assessments == (turn_uuid(2),)

    late = complete_assessment(
        in_qa,
        config,
        turn_id=turn_uuid(2),
        competency_focus=NODE_A,
        levels=((NODE_A, 5, 0.95),),
        now=at(minutes=3),
    )

    assert late.phase is Phase.QA
    assert late.tech.coverage[NODE_A].best_level == 5
    assert late.tech.pending_assessments == ()


def test_unknown_assessment_results_are_ignored(config: OrchestratorConfig) -> None:
    """§6.8's guard: only turns still in ``pending_assessments`` are accepted."""
    tech = drive_to_tech(config)

    result = transition(
        tech,
        AssessmentFailed(for_turn_id=turn_uuid(99), error_kind="timeout", now=at(minutes=1)),
        config,
    )

    assert result.new_state == tech
    assert result.commands == ()


# ---------------------------------------------------------------------------
# §5 bullet 3 / §6.4 — flags are measurement, never routing
# ---------------------------------------------------------------------------


def test_cheat_flag_threshold_sets_flagged_for_review_without_changing_the_move(
    config: OrchestratorConfig,
) -> None:
    assert config.flags.cheat_flags_to_review == 1
    tech = drive_to_tech(config)
    probing = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    )
    move_without_flag = pending_interviewer(probing.new_state)

    flagged = complete_assessment(
        probing.new_state,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 3, 0.9),),
        red_flags=("LIKELY_CHEATING",),
        now=at(minutes=1, seconds=5),
    )

    assert flagged.flagged_for_review is True
    assert flagged.cheat_flag_count == 1
    assert flagged.tech.coverage[NODE_A].red_flags == ("LIKELY_CHEATING",)
    # The move that was already issued is never retracted (§6.1).
    assert pending_interviewer(flagged) == move_without_flag


def test_needs_manual_review_is_recorded_in_coverage_and_on_the_session(
    config: OrchestratorConfig,
) -> None:
    tech = drive_to_tech(config)
    probing = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state

    reviewed = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 2, 0.7),),
        needs_manual_review=True,
        now=at(minutes=1, seconds=5),
    )

    assert reviewed.needs_manual_review is True
    assert reviewed.tech.coverage[NODE_A].needs_manual_review is True
    assert reviewed.flagged_for_review is False  # measurement, not routing


def test_drift_threshold_flags_the_session_and_keeps_the_issued_move(
    config: OrchestratorConfig,
) -> None:
    """§6.4: the ISSUED move stays authoritative; drift only counts."""
    state = drive_to_tech(config)
    for index in range(config.flags.drift_to_review):
        state = transition(
            state,
            CandidateTurnReceived(
                turn_id=turn_uuid(index + 1), text="Відповідь", now=at(minutes=index + 1)
            ),
            config,
        ).new_state
        issued = pending_interviewer(state)
        assert issued.move == "depth_probe" or issued.move == "close_competency"
        state = transition(
            state,
            InterviewerReplyReady(
                turn_id=issued.turn_id,
                # The interviewer reports a DIFFERENT move than the one issued.
                output=interviewer_output("redirect"),
                now=at(minutes=index + 1, seconds=5),
            ),
            config,
        ).new_state
        assert state.last_issued_move == issued.move

    assert state.tech.drift_count == config.flags.drift_to_review
    assert state.flagged_for_review is True


@pytest.mark.parametrize("drifts", [1, 2])
def test_drift_below_the_threshold_does_not_flag(config: OrchestratorConfig, drifts: int) -> None:
    assert drifts < config.flags.drift_to_review
    state = drive_to_tech(config)
    for index in range(drifts):
        state = transition(
            state,
            CandidateTurnReceived(
                turn_id=turn_uuid(index + 1), text="Відповідь", now=at(minutes=index + 1)
            ),
            config,
        ).new_state
        issued = pending_interviewer(state)
        state = transition(
            state,
            InterviewerReplyReady(
                turn_id=issued.turn_id,
                output=interviewer_output("redirect"),
                now=at(minutes=index + 1, seconds=5),
            ),
            config,
        ).new_state

    assert state.tech.drift_count == drifts
    assert state.flagged_for_review is False


# ---------------------------------------------------------------------------
# §6.7 — tick priority
# ---------------------------------------------------------------------------


def test_candidate_timeout_beats_the_session_budget_on_one_tick(
    config: OrchestratorConfig,
) -> None:
    """Both conditions fire on the same tick; silence is the stronger signal."""
    short = make_plan(session_max_minutes=5)
    tech = drive_to_tech(config, short)

    result = transition(tech, TimerTick(now=at(minutes=11)), config)

    assert result.new_state.phase is Phase.ABORTED
    assert result.new_state.abort_reason == "candidate_timeout"


def test_session_budget_fires_when_the_candidate_is_active(
    config: OrchestratorConfig,
) -> None:
    """Same tick, no silence: the §6.5 budget transition is the one that runs."""
    short = make_plan(session_max_minutes=5)
    tech = drive_to_tech(config, short)

    result = transition(tech, TimerTick(now=at(minutes=6)), config)

    assert result.new_state.phase is Phase.QA
