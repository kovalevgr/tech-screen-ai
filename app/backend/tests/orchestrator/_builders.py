"""Builders for orchestrator tests — plans, agent outputs, and driven states.

Everything here is deterministic: fixed ids, fixed timestamps, no clock. The
"drive" helpers reach a phase by replaying the real tabulated edges rather
than hand-assembling a state, so a test that asserts on TECH behaviour is
also asserting that the path into TECH still works.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from app.backend.agents.assessor import (
    AssessmentItem,
    AssessorOutput,
    RedFlagItem,
    RedFlagType,
)
from app.backend.agents.interviewer import InterviewerMove, InterviewerOutput
from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.state_machine import (
    AssessmentCompleted,
    CandidateTurnReceived,
    InterviewerReplyReady,
    RunInterviewer,
    SessionStarted,
    SessionState,
    initial_state,
    transition,
)

SESSION_ID: UUID = UUID("11111111-1111-5111-8111-111111111111")
"""Fixed session id — also the uuid5 namespace for derived command ids."""

T0: datetime = datetime(2026, 8, 3, 10, 0, 0, tzinfo=UTC)
"""Fixed session-start timestamp. Every other time in the suite is T0 + delta."""

NODE_A = "py.async"
NODE_B = "py.testing"

type AssessedLevel = Literal[0, 1, 2, 3, 4, 5]
type LevelTriple = tuple[str, AssessedLevel, float]
"""``(rubric_node_id, level, confidence)`` — the assessor's 0–5 scale (v0003)."""


def at(*, minutes: float = 0.0, seconds: float = 0.0) -> datetime:
    """Return ``T0`` shifted forward by ``minutes`` and ``seconds``."""
    return T0 + timedelta(minutes=minutes, seconds=seconds)


def turn_uuid(n: int) -> UUID:
    """Return a stable candidate-turn id for the ``n``-th candidate turn."""
    return UUID(f"22222222-2222-5222-8222-{n:012d}")


def competency(
    node_id: str,
    *,
    target_level: int = 3,
    minutes: int = 12,
    seeds: tuple[str, ...] = ("seed-1",),
    probes: tuple[str, ...] = ("probe-1", "probe-2"),
    label_uk: str = "Компетенція",
) -> dict[str, Any]:
    """Build one contract §7 competency entry."""
    return {
        "node_id": node_id,
        "label_uk": label_uk,
        "target_level": target_level,
        "minutes": minutes,
        "seed_questions_uk": list(seeds),
        "probe_branches_uk": list(probes),
    }


def make_plan(
    *,
    competencies: list[dict[str, Any]] | None = None,
    qa_minutes: int = 5,
    session_max_minutes: int = 60,
) -> dict[str, Any]:
    """Build a raw contract §7 plan payload (two competencies by default)."""
    return {
        "plan_version": 1,
        "competencies": competencies
        if competencies is not None
        else [competency(NODE_A), competency(NODE_B)],
        "qa_minutes": qa_minutes,
        "session_max_minutes": session_max_minutes,
    }


def interviewer_output(
    move: InterviewerMove, *, utterance: str = "Розкажіть, будь ласка, детальніше."
) -> InterviewerOutput:
    """Build a schema-valid interviewer reply for ``move``."""
    return InterviewerOutput(utterance=utterance, internal_move_executed=move)


def assessor_output(
    *,
    turn_id: UUID,
    competency_focus: str,
    levels: tuple[LevelTriple, ...] = (),
    red_flags: tuple[RedFlagType, ...] = (),
    needs_manual_review: bool = False,
) -> AssessorOutput:
    """Build a schema-valid assessor output.

    Args:
        turn_id: The candidate turn being scored.
        competency_focus: Rubric node the orchestrator asked about.
        levels: ``(rubric_node_id, level, confidence)`` triples; empty means
            "not assessable" (an empty ``assessments`` array).
        red_flags: Red-flag types to attach.
        needs_manual_review: The typed manual-review signal.
    """
    return AssessorOutput(
        turn_id=turn_id,
        session_id=SESSION_ID,
        competency_focus=competency_focus,
        assessments=[
            AssessmentItem(
                rubric_node_id=node_id,
                level=level,
                confidence=confidence,
                rationale_en="test rationale",
                evidence_spans=["evidence"],
            )
            for node_id, level, confidence in levels
        ],
        red_flags=[RedFlagItem(type=flag, description_en="test red flag") for flag in red_flags],
        needs_manual_review=needs_manual_review,
    )


def created_state(config: OrchestratorConfig, plan: dict[str, Any] | None = None) -> SessionState:
    """Return the ``CREATED`` state for the default (or given) plan."""
    return initial_state(
        session_id=SESSION_ID,
        plan_input=plan if plan is not None else make_plan(),
        config=config,
    )


def pending_interviewer(state: SessionState) -> RunInterviewer:
    """Return the outstanding ``RunInterviewer``, failing loudly if absent."""
    pending = state.pending_command
    assert isinstance(pending, RunInterviewer), (
        f"expected a pending RunInterviewer, got {pending!r}"
    )
    return pending


def drive_to_intro(config: OrchestratorConfig, plan: dict[str, Any] | None = None) -> SessionState:
    """Replay edge 1: ``CREATED`` → ``INTRO`` (scripted opening in flight)."""
    return transition(created_state(config, plan), SessionStarted(now=T0), config).new_state


def drive_to_tech(
    config: OrchestratorConfig,
    plan: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> SessionState:
    """Replay edges 1 → 3 → 4: TECH with the first seed asked and delivered.

    Returns:
        A TECH state ``awaiting`` the candidate, on competency 0 / seed 0.
    """
    when = now if now is not None else T0
    intro = drive_to_intro(config, plan)
    tech = transition(
        intro,
        CandidateTurnReceived(turn_id=turn_uuid(0), text="Готовий", now=when),
        config,
    ).new_state
    asked = pending_interviewer(tech)
    return transition(
        tech,
        InterviewerReplyReady(
            turn_id=asked.turn_id, output=interviewer_output(asked.move), now=when
        ),
        config,
    ).new_state


def deliver_reply(
    state: SessionState, config: OrchestratorConfig, *, now: datetime
) -> SessionState:
    """Complete the outstanding interviewer move (edge 4) and await the candidate."""
    issued = pending_interviewer(state)
    return transition(
        state,
        InterviewerReplyReady(
            turn_id=issued.turn_id, output=interviewer_output(issued.move), now=now
        ),
        config,
    ).new_state


def complete_assessment(
    state: SessionState,
    config: OrchestratorConfig,
    *,
    turn_id: UUID,
    competency_focus: str,
    levels: tuple[LevelTriple, ...] = (),
    red_flags: tuple[RedFlagType, ...] = (),
    needs_manual_review: bool = False,
    now: datetime,
) -> SessionState:
    """Apply edge 8 with a freshly built assessor output."""
    return transition(
        state,
        AssessmentCompleted(
            for_turn_id=turn_id,
            output=assessor_output(
                turn_id=turn_id,
                competency_focus=competency_focus,
                levels=levels,
                red_flags=red_flags,
                needs_manual_review=needs_manual_review,
            ),
            now=now,
        ),
        config,
    ).new_state
