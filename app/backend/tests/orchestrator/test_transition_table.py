"""Contract §10 transition table — one named test per numbered edge.

``docs/contracts/state-machine.md`` §10 is normative: 21 edges, each with the
state it leaves, the guard, the state it enters, and the exact command tuple.
These tests pin all four. Command tuples are asserted **exactly as tabulated**
— including where the table omits ``PersistState`` (edges 2, 15, 17, 20 and
the ``as #13`` tuple of edge 14). Blanket persistence after every transition
remains the shell's obligation (§9, spec Clarification 4); the command marks
only where the table asks for it.
"""

from __future__ import annotations

from typing import Any

from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.state_machine import (
    AssessmentFailed,
    CandidateTurnReceived,
    Command,
    CoverageCell,
    DeliverUtterance,
    EmitScriptedOpening,
    InterviewerFailed,
    InterviewerReplyReady,
    OperatorAbort,
    Phase,
    Reconnected,
    RecordDecision,
    RecordGap,
    ReissuePendingCommand,
    RunAssessor,
    RunInterviewer,
    SessionStarted,
    SessionState,
    TimerTick,
    derive_turn_id,
    initial_state,
    transition,
)

from ._builders import (
    NODE_A,
    NODE_B,
    SESSION_ID,
    T0,
    LevelTriple,
    at,
    competency,
    complete_assessment,
    created_state,
    deliver_reply,
    drive_to_intro,
    drive_to_tech,
    interviewer_output,
    make_plan,
    pending_interviewer,
    turn_uuid,
)


def kinds(commands: tuple[Command, ...]) -> list[str]:
    """Return the ``kind`` discriminator of each command, in order."""
    return [command.kind for command in commands]


def only_decision(command: Command) -> RecordDecision:
    """Narrow a command to :class:`RecordDecision`, failing loudly otherwise."""
    assert isinstance(command, RecordDecision), f"expected RecordDecision, got {command!r}"
    return command


# ---------------------------------------------------------------------------
# Edges 1–2 — session start
# ---------------------------------------------------------------------------


def test_edge_01_session_started_with_valid_plan_opens_intro(config: OrchestratorConfig) -> None:
    result = transition(created_state(config), SessionStarted(now=T0), config)

    assert result.new_state.phase is Phase.INTRO
    assert result.new_state.awaiting == "interviewer"
    assert result.new_state.plan is not None
    assert result.new_state.session_started_at == T0
    assert kinds(result.commands) == ["emit_scripted_opening", "persist_state"]
    opening = result.commands[0]
    assert isinstance(opening, EmitScriptedOpening)
    assert opening.turn_id == derive_turn_id(SESSION_ID, "turn/0")
    assert opening.script_path == "prompts/shared/candidate-facing/opening.md"


def test_edge_02_session_started_with_invalid_plan_aborts(config: OrchestratorConfig) -> None:
    broken = initial_state(
        session_id=SESSION_ID,
        plan_input={"plan_version": 1, "competencies": [], "qa_minutes": 5},
        config=config,
    )

    result = transition(broken, SessionStarted(now=T0), config)

    assert result.new_state.phase is Phase.ABORTED
    assert result.new_state.abort_reason == "operator_abort"
    # Tabulated exactly: RecordDecision(plan_invalid), and nothing else.
    assert kinds(result.commands) == ["record_decision"]
    assert only_decision(result.commands[0]).reason == "plan_invalid"


# ---------------------------------------------------------------------------
# Edge 3 — INTRO exits on the candidate's readiness turn
# ---------------------------------------------------------------------------


def test_edge_03_intro_candidate_turn_enters_tech_with_first_seed(
    config: OrchestratorConfig,
) -> None:
    intro = drive_to_intro(config)

    result = transition(
        intro, CandidateTurnReceived(turn_id=turn_uuid(0), text="Готовий", now=T0), config
    )

    assert result.new_state.phase is Phase.TECH
    assert result.new_state.awaiting == "interviewer"
    assert result.new_state.tech.competency_started_at == T0
    # "ScheduleNothing" == the command is simply absent (§10 note); no assessor
    # runs for an INTRO turn.
    assert kinds(result.commands) == ["run_interviewer", "persist_state"]
    issued = pending_interviewer(result.new_state)
    assert issued.move == "ask_seed"
    assert issued.competency_node_id == NODE_A
    assert issued.move_context["seed_question_uk"] == "seed-1"


# ---------------------------------------------------------------------------
# Edges 4–6 — the interviewer round trip and its failure ladder
# ---------------------------------------------------------------------------


def _tech_awaiting_interviewer(config: OrchestratorConfig) -> SessionState:
    """TECH with the first ``ask_seed`` in flight (the state edges 4–6 leave)."""
    intro = drive_to_intro(config)
    return transition(
        intro, CandidateTurnReceived(turn_id=turn_uuid(0), text="Готовий", now=T0), config
    ).new_state


def test_edge_04_interviewer_reply_delivers_and_awaits_candidate(
    config: OrchestratorConfig,
) -> None:
    tech = _tech_awaiting_interviewer(config)
    issued = pending_interviewer(tech)

    result = transition(
        tech,
        InterviewerReplyReady(
            turn_id=issued.turn_id,
            output=interviewer_output("ask_seed", utterance="Питання перше."),
            now=T0,
        ),
        config,
    )

    assert result.new_state.phase is Phase.TECH
    assert result.new_state.awaiting == "candidate"
    assert kinds(result.commands) == ["deliver_utterance", "persist_state"]
    delivered = result.commands[0]
    assert isinstance(delivered, DeliverUtterance)
    assert delivered.utterance == "Питання перше."


def test_edge_05_first_interviewer_failure_repeats_the_same_move(
    config: OrchestratorConfig,
) -> None:
    tech = _tech_awaiting_interviewer(config)
    issued = pending_interviewer(tech)

    result = transition(
        tech, InterviewerFailed(turn_id=issued.turn_id, error_kind="timeout", now=T0), config
    )

    assert result.new_state.phase is Phase.TECH
    assert result.new_state.awaiting == "interviewer"
    assert result.new_state.interviewer_failure_streak == 1
    assert kinds(result.commands) == ["run_interviewer", "flag_turn_degraded", "persist_state"]
    retry = result.commands[0]
    assert isinstance(retry, RunInterviewer)
    assert retry.retry is True
    assert retry.move == issued.move
    # Same interview turn, second attempt — the id must not move.
    assert retry.turn_id == issued.turn_id


def test_edge_06_second_consecutive_interviewer_failure_aborts(
    config: OrchestratorConfig,
) -> None:
    tech = _tech_awaiting_interviewer(config)
    issued = pending_interviewer(tech)
    after_first = transition(
        tech, InterviewerFailed(turn_id=issued.turn_id, error_kind="timeout", now=T0), config
    ).new_state

    result = transition(
        after_first,
        InterviewerFailed(turn_id=issued.turn_id, error_kind="timeout", now=at(seconds=30)),
        config,
    )

    assert result.new_state.phase is Phase.ABORTED
    assert result.new_state.abort_reason == "fatal_agent_error"
    assert kinds(result.commands) == ["record_decision", "persist_state"]
    assert only_decision(result.commands[0]).reason == "agent_failure"


# ---------------------------------------------------------------------------
# Edge 7 — the TECH candidate turn (assessor scheduled + move selected)
# ---------------------------------------------------------------------------


def test_edge_07_tech_candidate_turn_schedules_assessor_and_next_move(
    config: OrchestratorConfig,
) -> None:
    tech = drive_to_tech(config)

    result = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Моя відповідь", now=at(minutes=1)),
        config,
    )

    assert kinds(result.commands) == ["run_assessor", "run_interviewer", "persist_state"]
    scheduled = result.commands[0]
    assert isinstance(scheduled, RunAssessor)
    assert scheduled.turn_id == turn_uuid(1)
    assert scheduled.competency_focus == NODE_A
    assert result.new_state.tech.pending_assessments == (turn_uuid(1),)
    assert result.new_state.tech.assessment_focus == {turn_uuid(1): NODE_A}
    assert result.new_state.awaiting == "interviewer"


# ---------------------------------------------------------------------------
# Edges 8–9 — asynchronous assessment results
# ---------------------------------------------------------------------------


def _answered_once(config: OrchestratorConfig) -> SessionState:
    """TECH after one candidate turn — one assessment scheduled and pending."""
    return transition(
        drive_to_tech(config),
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state


def test_edge_08_assessment_completed_updates_coverage(config: OrchestratorConfig) -> None:
    pending = _answered_once(config)

    updated = complete_assessment(
        pending,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=((NODE_A, 4, 0.8),),
        now=at(minutes=1, seconds=5),
    )

    assert updated.phase is Phase.TECH
    assert updated.tech.pending_assessments == ()
    assert updated.tech.assessment_focus == {}
    assert updated.tech.coverage[NODE_A] == CoverageCell(
        best_level=4, best_confidence=0.8, latest_level=4, latest_confidence=0.8
    )


def test_edge_08_assessment_completed_emits_persist_state(config: OrchestratorConfig) -> None:
    from app.backend.orchestrator.state_machine import AssessmentCompleted

    from ._builders import assessor_output

    pending = _answered_once(config)

    result = transition(
        pending,
        AssessmentCompleted(
            for_turn_id=turn_uuid(1),
            output=assessor_output(
                turn_id=turn_uuid(1), competency_focus=NODE_A, levels=((NODE_A, 4, 0.8),)
            ),
            now=at(minutes=1, seconds=5),
        ),
        config,
    )

    assert kinds(result.commands) == ["persist_state"]


def test_edge_09_assessment_failed_marks_the_cell(config: OrchestratorConfig) -> None:
    pending = _answered_once(config)

    result = transition(
        pending,
        AssessmentFailed(
            for_turn_id=turn_uuid(1), error_kind="upstream_unavailable", now=at(minutes=1)
        ),
        config,
    )

    assert result.new_state.phase is Phase.TECH  # never aborts (§6.3)
    assert result.new_state.tech.pending_assessments == ()
    assert result.new_state.tech.coverage[NODE_A].assessment_failed is True
    assert kinds(result.commands) == ["persist_state"]


# ---------------------------------------------------------------------------
# Edges 10–13 — adjudication outcomes inside edge 7
# ---------------------------------------------------------------------------


def _tech_with_coverage(
    config: OrchestratorConfig,
    *,
    levels: tuple[LevelTriple, ...],
    plan: dict[str, Any] | None = None,
) -> SessionState:
    """Drive TECH to "one probe spent, one assessment completed, awaiting answer"."""
    probing = transition(
        drive_to_tech(config, plan),
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Перша відповідь", now=at(minutes=1)),
        config,
    ).new_state
    scored = complete_assessment(
        probing,
        config,
        turn_id=turn_uuid(1),
        competency_focus=NODE_A,
        levels=levels,
        now=at(minutes=1, seconds=10),
    )
    return deliver_reply(scored, config, now=at(minutes=1, seconds=20))


def test_edge_10_answered_advances_to_the_next_competency_in_one_call(
    config: OrchestratorConfig,
) -> None:
    ready = _tech_with_coverage(config, levels=((NODE_A, 4, 0.8),))

    result = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Друга відповідь", now=at(minutes=2)),
        config,
    )

    assert kinds(result.commands) == ["run_assessor", "run_interviewer", "persist_state"]
    issued = pending_interviewer(result.new_state)
    assert issued.move == "acknowledge_and_transition"
    assert result.new_state.tech.competency_index == 1
    assert result.new_state.tech.probes_used == 0
    assert issued.move_context["next_competency_node_id"] == NODE_B
    assert issued.move_context["next_seed_question_uk"] == "seed-1"


def test_edge_11_clarify_issues_a_depth_probe_and_spends_budget(
    config: OrchestratorConfig,
) -> None:
    tech = drive_to_tech(config)

    result = transition(
        tech,
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Часткова відповідь", now=at(minutes=1)),
        config,
    )

    issued = pending_interviewer(result.new_state)
    assert issued.move == "depth_probe"
    assert issued.move_context["probe_branch_uk"] == "probe-1"
    assert result.new_state.tech.probes_used == 1
    assert result.new_state.tech.competency_index == 0


def test_edge_12_none_records_a_gap_and_closes_the_competency(
    config: OrchestratorConfig,
) -> None:
    ready = _tech_with_coverage(config, levels=((NODE_A, 0, 0.9),))

    result = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Не знаю", now=at(minutes=2)),
        config,
    )

    assert kinds(result.commands) == [
        "run_assessor",
        "run_interviewer",
        "record_gap",
        "persist_state",
    ]
    issued = pending_interviewer(result.new_state)
    assert issued.move == "close_competency"
    assert issued.move_context["closing_competency_node_id"] == NODE_A
    assert issued.move_context["next_competency_node_id"] == NODE_B
    gap = result.commands[2]
    assert isinstance(gap, RecordGap)
    assert gap.node_id == NODE_A
    assert gap.marker == "level_zero"
    assert result.new_state.tech.competency_index == 1


def test_edge_13_last_competency_exit_enters_qa(config: OrchestratorConfig) -> None:
    single = make_plan(competencies=[competency(NODE_A)])
    ready = _tech_with_coverage(config, levels=((NODE_A, 4, 0.8),), plan=single)

    result = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Друга відповідь", now=at(minutes=2)),
        config,
    )

    assert result.new_state.phase is Phase.QA
    assert result.new_state.qa_started_at == at(minutes=2)
    issued = pending_interviewer(result.new_state)
    assert issued.move == "acknowledge_and_transition"
    assert issued.move_context == {"phase": "qa", "qa_minutes": 5}


# ---------------------------------------------------------------------------
# Edge 14 — the session budget
# ---------------------------------------------------------------------------


def test_edge_14_session_max_exceeded_jumps_from_tech_to_qa(config: OrchestratorConfig) -> None:
    short = make_plan(session_max_minutes=5)
    tech = drive_to_tech(config, short)

    result = transition(tech, TimerTick(now=at(minutes=6)), config)

    assert result.new_state.phase is Phase.QA
    # "as #13": the single acknowledge_and_transition into Q&A.
    assert kinds(result.commands) == ["run_interviewer"]
    assert pending_interviewer(result.new_state).move_context["phase"] == "qa"


def test_edge_14_session_max_exceeded_in_qa_goes_to_close(config: OrchestratorConfig) -> None:
    short = make_plan(competencies=[competency(NODE_A)], qa_minutes=30, session_max_minutes=5)
    tech = drive_to_tech(config, short)
    in_qa = transition(tech, TimerTick(now=at(minutes=6)), config).new_state

    result = transition(in_qa, TimerTick(now=at(minutes=7)), config)

    assert result.new_state.phase is Phase.CLOSE
    assert kinds(result.commands) == ["emit_scripted_closing", "persist_state"]


# ---------------------------------------------------------------------------
# Edges 15–17 — Q&A and the close-out
# ---------------------------------------------------------------------------


def _drive_to_qa(config: OrchestratorConfig, *, qa_minutes: int = 5) -> SessionState:
    """Reach QA ``awaiting`` the candidate via the tabulated edges 13 + 4."""
    single = make_plan(competencies=[competency(NODE_A)], qa_minutes=qa_minutes)
    ready = _tech_with_coverage(config, levels=((NODE_A, 4, 0.8),), plan=single)
    in_qa = transition(
        ready,
        CandidateTurnReceived(turn_id=turn_uuid(2), text="Друга відповідь", now=at(minutes=2)),
        config,
    ).new_state
    return deliver_reply(in_qa, config, now=at(minutes=2, seconds=10))


def test_edge_15_qa_turn_answers_without_scheduling_an_assessor(
    config: OrchestratorConfig,
) -> None:
    in_qa = _drive_to_qa(config)

    result = transition(
        in_qa,
        CandidateTurnReceived(turn_id=turn_uuid(3), text="А яка команда?", now=at(minutes=3)),
        config,
    )

    assert result.new_state.phase is Phase.QA
    # Exactly one tabulated command, and never a RunAssessor in QA (§2).
    assert kinds(result.commands) == ["run_interviewer"]
    assert pending_interviewer(result.new_state).move == "acknowledge_and_transition"


def test_edge_16_qa_budget_exhausted_enters_close(config: OrchestratorConfig) -> None:
    in_qa = _drive_to_qa(config, qa_minutes=1)

    result = transition(in_qa, TimerTick(now=at(minutes=4)), config)

    assert result.new_state.phase is Phase.CLOSE
    assert kinds(result.commands) == ["emit_scripted_closing", "persist_state"]


def test_edge_16_qa_budget_exhausted_on_a_candidate_turn_enters_close(
    config: OrchestratorConfig,
) -> None:
    in_qa = _drive_to_qa(config, qa_minutes=1)

    result = transition(
        in_qa,
        CandidateTurnReceived(turn_id=turn_uuid(3), text="Останнє питання", now=at(minutes=4)),
        config,
    )

    assert result.new_state.phase is Phase.CLOSE
    assert kinds(result.commands) == ["emit_scripted_closing", "persist_state"]


def test_edge_17_close_completes_the_session(config: OrchestratorConfig) -> None:
    in_close = transition(
        _drive_to_qa(config, qa_minutes=1), TimerTick(now=at(minutes=4)), config
    ).new_state
    closing = in_close.pending_command
    assert closing is not None

    result = transition(
        in_close,
        InterviewerReplyReady(
            turn_id=closing.turn_id,
            output=interviewer_output("acknowledge_and_transition"),
            now=at(minutes=4, seconds=10),
        ),
        config,
    )

    assert result.new_state.phase is Phase.COMPLETED
    assert kinds(result.commands) == ["end_session", "record_decision"]
    assert only_decision(result.commands[1]).reason == "completed"


def test_edge_17_close_completes_on_the_next_tick_without_a_model_call(
    config: OrchestratorConfig,
) -> None:
    """The table's "``InterviewerReplyReady`` / immediate" alternative."""
    in_close = transition(
        _drive_to_qa(config, qa_minutes=1), TimerTick(now=at(minutes=4)), config
    ).new_state

    result = transition(in_close, TimerTick(now=at(minutes=4, seconds=30)), config)

    assert result.new_state.phase is Phase.COMPLETED
    assert kinds(result.commands) == ["end_session", "record_decision"]


# ---------------------------------------------------------------------------
# Edges 18–19 — the two abort paths
# ---------------------------------------------------------------------------


def test_edge_18_candidate_timeout_aborts_the_session(config: OrchestratorConfig) -> None:
    tech = drive_to_tech(config)

    result = transition(tech, TimerTick(now=at(minutes=11)), config)

    assert result.new_state.phase is Phase.ABORTED
    assert result.new_state.abort_reason == "candidate_timeout"
    assert kinds(result.commands) == ["record_decision", "persist_state"]
    assert only_decision(result.commands[0]).reason == "timeout"


def test_edge_19_operator_abort_aborts_from_any_live_phase(config: OrchestratorConfig) -> None:
    tech = drive_to_tech(config)

    result = transition(tech, OperatorAbort(reason="operator_abort", now=at(minutes=1)), config)

    assert result.new_state.phase is Phase.ABORTED
    assert result.new_state.abort_reason == "operator_abort"
    assert kinds(result.commands) == ["record_decision", "persist_state"]
    assert only_decision(result.commands[0]).reason == "operator"


def test_edge_19_operator_abort_carries_the_cost_ceiling_hook(
    config: OrchestratorConfig,
) -> None:
    """§11: the machine exposes ABORTED(cost_ceiling); T21 raises the event."""
    tech = drive_to_tech(config)

    result = transition(tech, OperatorAbort(reason="cost_ceiling", now=at(minutes=1)), config)

    assert result.new_state.abort_reason == "cost_ceiling"


# ---------------------------------------------------------------------------
# Edges 20–21 — sinks and resume
# ---------------------------------------------------------------------------


def test_edge_20_terminal_states_are_idempotent_sinks(config: OrchestratorConfig) -> None:
    tech = drive_to_tech(config)
    aborted = transition(tech, OperatorAbort(now=at(minutes=1)), config).new_state

    events: tuple[Any, ...] = (
        TimerTick(now=at(minutes=20)),
        CandidateTurnReceived(turn_id=turn_uuid(9), text="Алло?", now=at(minutes=21)),
        Reconnected(now=at(minutes=22)),
        OperatorAbort(now=at(minutes=23)),
        AssessmentFailed(for_turn_id=turn_uuid(1), error_kind="timeout", now=at(minutes=24)),
        SessionStarted(now=at(minutes=25)),
    )
    for event in events:
        result = transition(aborted, event, config)
        assert result.new_state == aborted
        assert result.commands == ()


def test_edge_21_reconnect_reissues_the_pending_command_idempotently(
    config: OrchestratorConfig,
) -> None:
    tech = _tech_awaiting_interviewer(config)
    issued = pending_interviewer(tech)

    first = transition(tech, Reconnected(now=at(minutes=1)), config)
    second = transition(first.new_state, Reconnected(now=at(minutes=2)), config)

    assert first.new_state == tech  # state unchanged
    assert kinds(first.commands) == ["reissue_pending_command", "persist_state"]
    reissued = first.commands[0]
    assert isinstance(reissued, ReissuePendingCommand)
    assert reissued.command == issued
    # Idempotent by construction: uuid5 over the structural counter (§6.9).
    assert second.commands == first.commands


def test_edge_21_reconnect_without_a_pending_command_only_persists(
    config: OrchestratorConfig,
) -> None:
    tech = drive_to_tech(config)
    waiting = tech.model_copy(update={"pending_command": None})

    result = transition(waiting, Reconnected(now=at(minutes=1)), config)

    assert kinds(result.commands) == ["persist_state"]
