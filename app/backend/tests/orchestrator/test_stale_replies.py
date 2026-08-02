"""Stale interviewer replies are untabulated events (contract §6.9a, v1.2).

The race: a `TimerTick` can preempt an in-flight interviewer call — edge 14
moves the session to Q&A and issues a fresh move — and the wrapper's reply for
the abandoned turn still lands afterwards. Without a guard the machine would
speak a superseded utterance to the candidate, and would corrupt the drift
(§6.4) and failure-ladder (§6.2) counters for a turn nobody is waiting on.

Per §6.9a such an event is a no-op: state unchanged, no commands. The genuine
reply, whose `turn_id` matches the outstanding command, is unaffected — every
edge test in `test_transition_table.py` uses matching ids and passes unchanged.
"""

from __future__ import annotations

from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.state_machine import (
    CandidateTurnReceived,
    DeliverUtterance,
    EmitScriptedClosing,
    InterviewerFailed,
    InterviewerReplyReady,
    Phase,
    RunInterviewer,
    SessionState,
    TimerTick,
    transition,
)

from ._builders import (
    at,
    drive_to_qa,
    drive_to_tech,
    interviewer_output,
    make_plan,
    pending_interviewer,
    turn_uuid,
)


def _preempted_probe(
    config: OrchestratorConfig,
) -> tuple[SessionState, RunInterviewer, RunInterviewer]:
    """Reproduce the §6.9a race and return ``(state, abandoned, outstanding)``.

    A ``depth_probe`` is in flight when the session budget runs out; edge 14
    jumps to Q&A and issues a new ``acknowledge_and_transition``. The probe's
    reply is now stale.
    """
    short = make_plan(session_max_minutes=5)
    probing = transition(
        drive_to_tech(config, short),
        CandidateTurnReceived(turn_id=turn_uuid(1), text="Відповідь", now=at(minutes=1)),
        config,
    ).new_state
    abandoned = pending_interviewer(probing)
    assert abandoned.move == "depth_probe"

    preempted = transition(probing, TimerTick(now=at(minutes=5)), config).new_state
    outstanding = pending_interviewer(preempted)

    assert preempted.phase is Phase.QA
    assert outstanding.turn_id != abandoned.turn_id
    return preempted, abandoned, outstanding


def test_a_stale_interviewer_reply_is_a_no_op(config: OrchestratorConfig) -> None:
    preempted, abandoned, outstanding = _preempted_probe(config)

    result = transition(
        preempted,
        InterviewerReplyReady(
            turn_id=abandoned.turn_id,
            output=interviewer_output("depth_probe", utterance="Застаріле питання."),
            now=at(minutes=5, seconds=5),
        ),
        config,
    )

    assert result.new_state == preempted
    assert result.commands == ()
    # No delivery, no drift accounting, and the real command is still pending.
    assert result.new_state.tech.drift_count == 0
    assert result.new_state.pending_command == outstanding


def test_the_genuine_reply_still_delivers_after_a_stale_one(
    config: OrchestratorConfig,
) -> None:
    preempted, abandoned, outstanding = _preempted_probe(config)
    ignored = transition(
        preempted,
        InterviewerReplyReady(
            turn_id=abandoned.turn_id,
            output=interviewer_output("depth_probe"),
            now=at(minutes=5, seconds=5),
        ),
        config,
    ).new_state

    result = transition(
        ignored,
        InterviewerReplyReady(
            turn_id=outstanding.turn_id,
            output=interviewer_output("acknowledge_and_transition", utterance="Переходимо."),
            now=at(minutes=5, seconds=10),
        ),
        config,
    )

    assert result.new_state.awaiting == "candidate"
    delivered = result.commands[0]
    assert isinstance(delivered, DeliverUtterance)
    assert delivered.turn_id == outstanding.turn_id
    assert delivered.utterance == "Переходимо."
    assert result.new_state.tech.drift_count == 0


def test_a_stale_interviewer_failure_does_not_advance_the_ladder(
    config: OrchestratorConfig,
) -> None:
    preempted, abandoned, outstanding = _preempted_probe(config)

    result = transition(
        preempted,
        InterviewerFailed(
            turn_id=abandoned.turn_id, error_kind="timeout", now=at(minutes=5, seconds=5)
        ),
        config,
    )

    assert result.new_state == preempted
    assert result.commands == ()
    assert result.new_state.interviewer_failure_streak == 0
    assert result.new_state.pending_command == outstanding


def test_the_ladder_still_advances_on_the_outstanding_turn(
    config: OrchestratorConfig,
) -> None:
    """A stale failure must not consume the single retry of the live turn."""
    preempted, abandoned, outstanding = _preempted_probe(config)
    ignored = transition(
        preempted,
        InterviewerFailed(
            turn_id=abandoned.turn_id, error_kind="timeout", now=at(minutes=5, seconds=5)
        ),
        config,
    ).new_state

    result = transition(
        ignored,
        InterviewerFailed(
            turn_id=outstanding.turn_id, error_kind="timeout", now=at(minutes=5, seconds=10)
        ),
        config,
    )

    assert result.new_state.phase is Phase.QA  # edge 5, not edge 6
    assert result.new_state.interviewer_failure_streak == 1
    retry = result.commands[0]
    assert isinstance(retry, RunInterviewer)
    assert retry.retry is True
    assert retry.turn_id == outstanding.turn_id


def test_a_stale_reply_on_the_qa_turn_path_is_a_no_op(config: OrchestratorConfig) -> None:
    """The edge-15 equivalent: a Q&A move supersedes the previous one."""
    in_qa = drive_to_qa(config)
    superseded = in_qa.pending_command
    assert isinstance(superseded, DeliverUtterance)  # the delivered QA-entry turn

    answering = transition(
        in_qa,
        CandidateTurnReceived(turn_id=turn_uuid(3), text="А яка команда?", now=at(minutes=3)),
        config,
    ).new_state
    outstanding = pending_interviewer(answering)

    result = transition(
        answering,
        InterviewerReplyReady(
            turn_id=superseded.turn_id,
            output=interviewer_output("acknowledge_and_transition", utterance="Застаріле."),
            now=at(minutes=3, seconds=5),
        ),
        config,
    )

    assert result.new_state == answering
    assert result.commands == ()
    assert result.new_state.awaiting == "interviewer"
    assert result.new_state.pending_command == outstanding


def test_a_stale_reply_in_close_does_not_complete_the_session(
    config: OrchestratorConfig,
) -> None:
    """Edge 17 answers the outstanding closing turn, not any stray reply."""
    in_close = transition(
        drive_to_qa(config, qa_minutes=1), TimerTick(now=at(minutes=4)), config
    ).new_state
    closing = in_close.pending_command
    assert isinstance(closing, EmitScriptedClosing)

    result = transition(
        in_close,
        InterviewerReplyReady(
            turn_id=turn_uuid(42),
            output=interviewer_output("acknowledge_and_transition"),
            now=at(minutes=4, seconds=5),
        ),
        config,
    )

    assert result.new_state == in_close
    assert result.commands == ()
    assert result.new_state.phase is Phase.CLOSE
