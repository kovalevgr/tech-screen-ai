"""The deterministic interview orchestrator — pure functional core (T20).

Normative design: ``docs/contracts/state-machine.md`` **v1.1**. Section
references in this module (§n) point at that document; every numbered
section there is binding and this module implements it, it does not extend
it.

Constitution §2 / ADR-005 in one sentence: *LLMs produce content, this
module produces every routing decision.* Nothing here branches on free-text
model output — only on typed, schema-validated fields (``level``,
``confidence``, ``internal_move_executed``, ``needs_manual_review``,
red-flag types) and on the thresholds in ``configs/orchestrator.yaml``.
``CandidateTurnReceived.text`` exists on the event because the shell passes
it through to the wrappers; the core never reads it, and
``tests/orchestrator/test_purity_guards.py`` proves that statically.

**Purity.** :func:`transition` is a total function of
``(state, event, config)``:

- no I/O — no database, no files, no network;
- no clock — every timestamp arrives ON an event (``event.now``);
- no randomness — command ``turn_id``s are ``uuid5(session_id, path)``
  over a structural counter (§6.9), so re-issuing after a resume is
  idempotent by construction (edge 21).

The imperative shell (T22/T23) executes the returned commands and feeds
results back as new events. Persisting ``new_state`` after every transition
— and *before* issuing wrapper calls — is the shell's obligation (§9, spec
Clarification 4); the ``PersistState`` command marks where the contract's
transition table asks for it explicitly.

**Move vocabulary** (§10 note): a competency/seed advance is ONE interviewer
call — ``acknowledge_and_transition`` (ANSWERED path) or ``close_competency``
(NONE path) — carrying the next seed question in ``move_context``. A bare
``ask_seed`` occurs only for the very first seed after INTRO.

``move_context`` keys produced here (the T18 wrapper's ``move_context`` is a
free-form ``dict[str, Any]``; these are the keys this machine emits):

===========================  =========================================
key                          meaning
===========================  =========================================
``seed_question_uk``         the seed to ask now (``ask_seed``)
``next_seed_question_uk``    the seed to ask after the transition
``seed_index``               zero-based seed position it refers to
``competency_node_id``       competency the move lands in
``next_competency_node_id``  same, on a competency advance
``next_competency_label_uk`` its Ukrainian label
``closing_competency_node_id`` competency being closed (``close_competency``)
``probe_branch_uk``          planned branch, or ``None`` → generic probe
``probe_index``              zero-based probe position within the competency
``phase``                    ``"qa"`` on the transition into Q&A
``qa_minutes``               the plan's Q&A budget
===========================  =========================================
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Annotated, Any, Final, Literal
from uuid import UUID, uuid5

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.backend.agents.assessor import AssessorOutput, RedFlagType
from app.backend.agents.interviewer import InterviewerMove, InterviewerOutput
from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.plan import PlanInvalid, PlannedCompetency, PlanSnapshot

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

OPENING_SCRIPT_PATH: Final[str] = "prompts/shared/candidate-facing/opening.md"
"""Fixed scripted opening (§2 INTRO) — NOT LLM-generated. The core only names
the artefact; reading and delivering it is the shell's job (T22/T29)."""

CLOSING_SCRIPT_PATH: Final[str] = "prompts/shared/candidate-facing/closing.md"
"""Fixed scripted closing (§2 CLOSE) — NOT LLM-generated."""

CHEAT_RED_FLAG: Final[RedFlagType] = "LIKELY_CHEATING"
"""The one red-flag type that feeds a session-level flag (§5 bullet 3)."""


class Phase(StrEnum):
    """Session phases (§2). ``COMPLETED`` and ``ABORTED`` are terminal sinks."""

    CREATED = "created"
    INTRO = "intro"
    TECH = "tech"
    QA = "qa"
    CLOSE = "close"
    COMPLETED = "completed"
    ABORTED = "aborted"


TERMINAL_PHASES: Final[frozenset[Phase]] = frozenset({Phase.COMPLETED, Phase.ABORTED})
"""Edge 20: in a terminal phase every event is an idempotent no-op."""

Awaiting = Literal["interviewer", "candidate"]
"""Whose move the machine is waiting for (§4, top level — all phases)."""

AbortReason = Literal["candidate_timeout", "cost_ceiling", "operator_abort", "fatal_agent_error"]
"""§2. ``cost_ceiling`` is reachable only via ``OperatorAbort`` — the ceiling
itself is enforced by T21, which raises the event (§11)."""

DecisionReason = Literal["plan_invalid", "agent_failure", "timeout", "operator", "completed"]
"""``RecordDecision`` reasons named by the §10 transition table; T21 maps them
onto ``session_decision`` rows."""

Verdict = Literal["ANSWERED", "CLARIFY", "NONE"]
"""The owner's 2/1/0 adjudication table (§5)."""

AdjudicationBasis = Literal["assessment", "pending", "failed", "not_assessable"]
"""What the verdict was computed from. ``pending`` is policy ``proceed_planned``
(§6.1); ``failed`` is §6.3 (treated as "no assessment available")."""

GapMarker = Literal["gap_not_assessable", "gap_budget_exhausted", "assessment_failed", "level_zero"]
"""Reviewer-visible gap kinds. The first three are the §4 ``CoverageCell``
markers; ``level_zero`` distinguishes an evidence-backed None (assessor level
0) from an empty ``assessments`` array (§5: both reach NONE, both are stored
distinctly)."""


class OrchestratorStateError(Exception):
    """A state the machine cannot reach by its own transitions was handed to it.

    Only raised for genuine invariant violations (e.g. a TECH state whose
    plan is ``None``, which edge 1 makes impossible) — never for candidate
    or model behaviour.
    """


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class CoverageCell(BaseModel):
    """Per-rubric-node coverage (§4, §5).

    Carries **both** aggregations §5 needs: ``best_*`` (max level; ties → the
    later assessment) drives the ANSWERED test, ``latest_*`` (most recently
    completed) drives the level-0 NONE trigger. The three boolean markers keep
    "assessor said level 0", "assessor returned no assessments" and "the
    assessment call failed" distinguishable for reviewers.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    best_level: int | None = None
    best_confidence: float | None = None
    latest_level: int | None = None
    latest_confidence: float | None = None
    gap_not_assessable: bool = False
    """An ``AssessorOutput`` arrived with ``assessments == []`` (§5)."""
    assessment_failed: bool = False
    """An ``AssessmentFailed`` event arrived for a turn focused on this node
    (§6.3). Never aborts the session — it becomes reviewer work."""
    gap_budget_exhausted: bool = False
    """NONE was recorded because the probe budget or competency time ran out."""
    needs_manual_review: bool = False
    red_flags: tuple[RedFlagType, ...] = ()
    """Red-flag types recorded against this node. Measurement, not routing —
    only the ``LIKELY_CHEATING`` count feeds a session flag (§5)."""


class TechState(BaseModel):
    """TECH sub-state (§4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    competency_index: int = 0
    seed_index: int = 0
    probes_used: int = 0
    drift_count: int = 0
    competency_started_at: AwareDatetime | None = None
    coverage: dict[str, CoverageCell] = Field(default_factory=dict)
    pending_assessments: tuple[UUID, ...] = ()
    assessment_focus: dict[UUID, str] = Field(default_factory=dict)
    """``turn_id -> rubric node id`` for every scheduled assessment. §4 lists
    ``pending_assessments`` as bare turn ids; ``AssessmentFailed`` carries no
    output, so the focus a turn was scheduled against is remembered here —
    otherwise a late failure could not be attributed to the right cell (§6.8).
    Entries are dropped together with the pending id."""


class RunInterviewer(BaseModel):
    """Ask the T18 wrapper for the next Ukrainian utterance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["run_interviewer"] = "run_interviewer"
    turn_id: UUID
    move: InterviewerMove
    competency_node_id: str | None = None
    move_context: dict[str, Any] = Field(default_factory=dict)
    retry: bool = False
    """Edge 5: the same move re-issued once after an interviewer failure. The
    ``turn_id`` is unchanged — it is the same interview turn, second attempt."""


class RunAssessor(BaseModel):
    """Schedule the T19 wrapper for a candidate turn. Never awaited (§6.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["run_assessor"] = "run_assessor"
    turn_id: UUID
    competency_focus: str


class DeliverUtterance(BaseModel):
    """Send the interviewer's utterance to the candidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["deliver_utterance"] = "deliver_utterance"
    turn_id: UUID
    utterance: str


class EmitScriptedOpening(BaseModel):
    """Deliver the fixed opening (§2 INTRO) — no model call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["emit_scripted_opening"] = "emit_scripted_opening"
    turn_id: UUID
    script_path: str = OPENING_SCRIPT_PATH


class EmitScriptedClosing(BaseModel):
    """Deliver the fixed closing (§2 CLOSE) — no model call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["emit_scripted_closing"] = "emit_scripted_closing"
    turn_id: UUID
    script_path: str = CLOSING_SCRIPT_PATH


class FlagTurnDegraded(BaseModel):
    """Mark a turn as degraded after an interviewer failure (§6.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["flag_turn_degraded"] = "flag_turn_degraded"
    turn_id: UUID
    error_kind: str


class RecordGap(BaseModel):
    """Record a coverage gap for a competency the machine is leaving (edge 12)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["record_gap"] = "record_gap"
    node_id: str
    marker: GapMarker


class RecordDecision(BaseModel):
    """Record a session-level decision (T21 writes ``session_decision``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["record_decision"] = "record_decision"
    reason: DecisionReason


class EndSession(BaseModel):
    """Close the session out (edge 17)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["end_session"] = "end_session"
    outcome: Literal["completed"] = "completed"


class PersistState(BaseModel):
    """Persist ``new_state`` (§9). Emitted exactly where the §10 table says."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["persist_state"] = "persist_state"


PendingCommand = Annotated[
    RunInterviewer | DeliverUtterance | EmitScriptedOpening | EmitScriptedClosing,
    Field(discriminator="kind"),
]
"""The outbound commands a resume may have to re-issue (§9, edge 21)."""


class ReissuePendingCommand(BaseModel):
    """Re-emit the outstanding outbound command after a resume (edge 21).

    Carries the command verbatim, ``turn_id`` included: because ids are
    ``uuid5`` over a structural counter (§6.9) the shell can dedupe by id and
    the re-issue is idempotent by construction.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["reissue_pending_command"] = "reissue_pending_command"
    command: PendingCommand


Command = Annotated[
    RunInterviewer
    | RunAssessor
    | DeliverUtterance
    | EmitScriptedOpening
    | EmitScriptedClosing
    | FlagTurnDegraded
    | RecordGap
    | RecordDecision
    | EndSession
    | PersistState
    | ReissuePendingCommand,
    Field(discriminator="kind"),
]
"""Everything the core can ask the shell to do. There is no no-op variant —
"ScheduleNothing" in edge 3 means the command is simply absent (§10 note)."""


class SessionState(BaseModel):
    """The whole persisted working state of one session (§4, §9).

    §4 sketches the essential fields; the bookkeeping the §6 policies need
    (failure streak, session flags, timestamps, the structural counter behind
    §6.9, the outstanding command behind edge 21) lives alongside them. The
    model is frozen — transitions build a new state, never mutate one.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    state_schema_version: int
    """Stamped from ``OrchestratorConfig.state_schema_version``; a load-time
    mismatch fails loudly in :mod:`.persistence` (no silent migration)."""

    session_id: UUID
    """Namespace for the ``uuid5`` command ids (§6.9)."""

    phase: Phase = Phase.CREATED
    awaiting: Awaiting | None = None
    last_issued_move: InterviewerMove | None = None
    """The move the machine ISSUED. Authoritative for state even when the
    interviewer reports a different ``internal_move_executed`` (§6.4)."""

    plan_input: dict[str, Any] = Field(default_factory=dict)
    """The raw plan frozen onto the session. Retained after validation so
    edge 2 (plan invalid) is representable and the shell can show exactly
    what was rejected."""

    plan: PlanSnapshot | None = None
    """The typed plan — populated by edge 1; authoritative from then on."""

    tech: TechState = Field(default_factory=TechState)
    abort_reason: AbortReason | None = None
    flagged_for_review: bool = False
    """Set by the cheat-flag and drift thresholds (§5, §6.4). Never changes
    the move sequence."""

    needs_manual_review: bool = False
    """Sticky session-level echo of ``AssessorOutput.needs_manual_review``."""

    cheat_flag_count: int = 0
    interviewer_failure_streak: int = 0
    """Consecutive failures for the move currently in flight (§6.2). Reset by
    a successful reply or by issuing a new move."""

    turn_seq: int = 0
    """Structural counter behind the ``uuid5`` command ids (§6.9). Advances
    once per NEW outbound turn; a retry (edge 5) reuses its turn."""

    session_started_at: AwareDatetime | None = None
    qa_started_at: AwareDatetime | None = None
    last_candidate_activity: AwareDatetime | None = None
    pending_command: PendingCommand | None = None
    """The outbound command a resume re-issues (edge 21); ``None`` when the
    machine is waiting on the candidate's side of an already-delivered turn."""


class SessionStarted(BaseModel):
    """Session create/start (§3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["session_started"] = "session_started"
    now: AwareDatetime


class CandidateTurnReceived(BaseModel):
    """A candidate turn arrived (§3).

    ``text`` is carried for the shell's pass-through to the wrappers and is
    NEVER inspected by the core (§3, constitution §2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["candidate_turn_received"] = "candidate_turn_received"
    turn_id: UUID
    text: str
    now: AwareDatetime


class InterviewerReplyReady(BaseModel):
    """The T18 wrapper returned a valid utterance (§3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["interviewer_reply_ready"] = "interviewer_reply_ready"
    turn_id: UUID
    output: InterviewerOutput
    now: AwareDatetime


class InterviewerFailed(BaseModel):
    """The T18 wrapper raised a typed error (§3, §6.2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["interviewer_failed"] = "interviewer_failed"
    turn_id: UUID
    error_kind: str
    now: AwareDatetime


class AssessmentCompleted(BaseModel):
    """The T19 wrapper returned a scored turn (§3) — asynchronously."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["assessment_completed"] = "assessment_completed"
    for_turn_id: UUID
    output: AssessorOutput
    now: AwareDatetime


class AssessmentFailed(BaseModel):
    """The T19 wrapper raised a typed error (§3, §6.3)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["assessment_failed"] = "assessment_failed"
    for_turn_id: UUID
    error_kind: str
    now: AwareDatetime


class TimerTick(BaseModel):
    """Coarse cadence tick (≥ ``timing.tick_seconds``) — the only time source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["timer_tick"] = "timer_tick"
    now: AwareDatetime


class Reconnected(BaseModel):
    """Resume/rehydrate completed (§3, §9, edge 21)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["reconnected"] = "reconnected"
    now: AwareDatetime


class OperatorAbort(BaseModel):
    """Admin abort (§3, edge 19).

    ``reason`` is typed as the full §2 abort set so T21 can raise
    ``cost_ceiling`` through this event — the §11 hook the machine exposes
    without owning ceiling enforcement.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["operator_abort"] = "operator_abort"
    reason: AbortReason = "operator_abort"
    now: AwareDatetime


Event = Annotated[
    SessionStarted
    | CandidateTurnReceived
    | InterviewerReplyReady
    | InterviewerFailed
    | AssessmentCompleted
    | AssessmentFailed
    | TimerTick
    | Reconnected
    | OperatorAbort,
    Field(discriminator="kind"),
]
"""The input alphabet (§3)."""


class Adjudication(BaseModel):
    """The result of the §5 turn-adjudication table for one competency."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    verdict: Verdict
    basis: AdjudicationBasis
    gap_marker: GapMarker | None = None
    """Set only for NONE — what the machine records against the node."""


class TransitionResult(BaseModel):
    """``(new_state, commands)`` — the whole output of one transition (§1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    new_state: SessionState
    commands: tuple[Command, ...] = ()


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def _evolve[M: BaseModel](model: M, /, **changes: Any) -> M:
    """Return a copy of a frozen model with ``changes`` applied.

    ``model_copy`` skips validation, so a mistyped field name would silently
    graft an unknown attribute onto the state. The key check turns that class
    of typo into a loud failure while keeping transitions allocation-cheap.

    Args:
        model: The frozen pydantic model to evolve.
        **changes: Field values to replace.

    Returns:
        A new model instance of the same type.

    Raises:
        OrchestratorStateError: A key is not a field of ``model``'s type.
    """
    unknown = set(changes) - set(type(model).model_fields)
    if unknown:
        raise OrchestratorStateError(
            f"cannot evolve {type(model).__name__}: unknown field(s) {sorted(unknown)}"
        )
    return model.model_copy(update=changes)


def derive_turn_id(session_id: UUID, path: str) -> UUID:
    """Derive a deterministic command ``turn_id`` (§6.9).

    ``uuid5`` over the session id and a structural-counter path — never
    ``uuid4`` — so a re-issue after resume (edge 21) produces the identical
    id and the shell can dedupe.

    Args:
        session_id: Used as the uuid5 namespace.
        path: Structural counter path, e.g. ``"turn/3"``.

    Returns:
        The derived turn id.
    """
    return uuid5(session_id, path)


def _turn_path(turn_seq: int) -> str:
    """Structural-counter path for the ``turn_seq``-th outbound turn."""
    return f"turn/{turn_seq}"


def _require_plan(state: SessionState) -> PlanSnapshot:
    """Return the validated plan, or fail loudly.

    Every phase past ``CREATED`` is entered through edge 1, which sets the
    plan; ``None`` here means a hand-built state, not a reachable one.
    """
    if state.plan is None:
        raise OrchestratorStateError(f"phase {state.phase} reached without a validated plan")
    return state.plan


def _current_competency(state: SessionState) -> PlannedCompetency:
    """Return the competency the TECH loop is currently on."""
    plan = _require_plan(state)
    competency = plan.competency(state.tech.competency_index)
    if competency is None:
        raise OrchestratorStateError(
            f"competency_index {state.tech.competency_index} is outside the plan"
        )
    return competency


def _seconds_remaining(
    competency: PlannedCompetency, started_at: datetime | None, now: datetime
) -> float:
    """Seconds left in the current competency's budget (§6.5).

    Args:
        competency: The competency being timed.
        started_at: When the machine entered it; ``None`` (not yet entered)
            reads as "the full budget remains".
        now: The timestamp carried by the event being handled.

    Returns:
        Remaining seconds; negative once the budget is overspent.
    """
    budget = float(competency.minutes) * 60.0
    if started_at is None:
        return budget
    return budget - (now - started_at).total_seconds()


def _ignore(state: SessionState) -> TransitionResult:
    """No tabulated edge matches: the event is a no-op (§10, edge 20 style)."""
    return TransitionResult(new_state=state, commands=())


def _answers_pending_command(state: SessionState, turn_id: UUID) -> bool:
    """Whether an agent reply belongs to the OUTSTANDING command (§6.9a).

    A `TimerTick` can preempt an in-flight interviewer call (edge 14 moves the
    session to Q&A and issues a fresh move), and the wrapper's reply for the
    abandoned turn may still land afterwards. Such a reply is an untabulated
    event: delivering it would speak a superseded utterance to the candidate,
    and counting it would corrupt the drift (§6.4) and failure-ladder (§6.2)
    accounting for a turn nobody is waiting on.

    Args:
        state: The current session state.
        turn_id: The ``turn_id`` carried by the reply/failure event.

    Returns:
        ``True`` when a command is outstanding and the ids match.
    """
    return state.pending_command is not None and state.pending_command.turn_id == turn_id


# ---------------------------------------------------------------------------
# Adjudication — the owner's 2/1/0 table (§5)
# ---------------------------------------------------------------------------


def _basis(cell: CoverageCell | None) -> AdjudicationBasis:
    """Classify what evidence the adjudication has for a node."""
    if cell is None:
        return "pending"
    if cell.best_level is not None:
        return "assessment"
    if cell.gap_not_assessable:
        return "not_assessable"
    if cell.assessment_failed:
        return "failed"
    return "pending"


def adjudicate(
    *,
    cell: CoverageCell | None,
    target_level: int,
    probes_used: int,
    seconds_remaining: float,
    config: OrchestratorConfig,
) -> Adjudication:
    """Apply the owner's 2/1/0 table (§5) to one competency.

    Evaluation order is fixed (and is what resolves §5's deliberately
    overlapping rows):

    1. **ANSWERED** — ``best_level >= target_level`` AND that assessment's
       ``confidence >= confidence_min`` (boundary inclusive).
    2. **level-0 short-circuit** — the LATEST completed assessment scored 0
       ("не володіє", evidence-backed): NONE, even with probe budget left.
    3. **budget / time exhausted** — no probe left, or not enough time to
       hear a probe out: NONE.
    4. **not assessable** — an assessor output came back with an empty
       ``assessments`` array and at least one probe has been spent: NONE.
    5. **CLARIFY** — everything else, which is exactly where policy
       ``proceed_planned`` (§6.1, no assessment completed yet) and §6.3 (the
       assessment call failed) land: keep probing the planned branch.

    Args:
        cell: Coverage for the competency's rubric node, if any exists yet.
        target_level: The plan's ``target_level`` for this competency.
        probes_used: Probes already spent inside this competency.
        seconds_remaining: Competency budget left, from the event timestamp.
        config: The loaded thresholds.

    Returns:
        The verdict, what it was based on, and (for NONE) the gap marker.
    """
    thresholds = config.adjudication
    basis = _basis(cell)

    # 1. ANSWERED (2)
    if (
        cell is not None
        and cell.best_level is not None
        and cell.best_confidence is not None
        and cell.best_level >= target_level
        and cell.best_confidence >= thresholds.confidence_min
    ):
        return Adjudication(verdict="ANSWERED", basis=basis)

    # 2. Evidence-backed None short-circuits the probe budget.
    if cell is not None and cell.latest_level == 0:
        return Adjudication(verdict="NONE", basis=basis, gap_marker="level_zero")

    # 3. Probe budget or competency time exhausted → close the competency.
    if (
        probes_used >= thresholds.max_probes_per_competency
        or seconds_remaining <= thresholds.min_probe_seconds
    ):
        return Adjudication(verdict="NONE", basis=basis, gap_marker="gap_budget_exhausted")

    # 4. "Not assessable" only counts once we have actually probed for depth.
    if cell is not None and cell.gap_not_assessable and probes_used >= 1:
        return Adjudication(verdict="NONE", basis=basis, gap_marker="gap_not_assessable")

    # 5. CLARIFY (1) — includes `pending` (§6.1) and `failed` (§6.3).
    return Adjudication(verdict="CLARIFY", basis=basis)


# ---------------------------------------------------------------------------
# move_context builders
# ---------------------------------------------------------------------------


def _first_seed_context(competency: PlannedCompetency) -> dict[str, Any]:
    """Context for the one bare ``ask_seed`` of the session (edge 3)."""
    return {
        "competency_node_id": competency.node_id,
        "seed_index": 0,
        "seed_question_uk": competency.seed_questions_uk[0],
    }


def _next_seed_context(competency: PlannedCompetency, seed_index: int, seed: str) -> dict[str, Any]:
    """Context for moving to the next seed inside the same competency (§4)."""
    return {
        "competency_node_id": competency.node_id,
        "seed_index": seed_index,
        "next_seed_question_uk": seed,
    }


def _probe_context(competency: PlannedCompetency, probe_index: int) -> dict[str, Any]:
    """Context for a ``depth_probe`` (edge 11); branch may be ``None`` (§7)."""
    return {
        "competency_node_id": competency.node_id,
        "probe_index": probe_index,
        "probe_branch_uk": competency.probe_branch(probe_index),
    }


def _advance_context(
    closing: PlannedCompetency | None, following: PlannedCompetency
) -> dict[str, Any]:
    """Context for a ONE-call competency advance (edges 10 and 12)."""
    return {
        "closing_competency_node_id": None if closing is None else closing.node_id,
        "competency_node_id": following.node_id,
        "next_competency_node_id": following.node_id,
        "next_competency_label_uk": following.label_uk,
        "seed_index": 0,
        "next_seed_question_uk": following.seed_questions_uk[0],
    }


def _qa_context(plan: PlanSnapshot) -> dict[str, Any]:
    """Context for the transition into Q&A (edges 13/14)."""
    return {"phase": "qa", "qa_minutes": plan.qa_minutes}


# ---------------------------------------------------------------------------
# State constructors
# ---------------------------------------------------------------------------


def initial_state(
    *,
    session_id: UUID,
    plan_input: Mapping[str, Any],
    config: OrchestratorConfig,
) -> SessionState:
    """Build the pre-start state the shell persists at session creation.

    Args:
        session_id: The session's id — also the ``uuid5`` namespace (§6.9).
        plan_input: The raw plan payload frozen onto the session (§7). It is
            validated by ``SessionStarted`` (edges 1/2), not here: an invalid
            plan must be observable as ``ABORTED``, not as a construction
            error.
        config: The loaded thresholds, for the state schema version stamp.

    Returns:
        A ``CREATED`` state.
    """
    return SessionState(
        state_schema_version=config.state_schema_version,
        session_id=session_id,
        plan_input=dict(plan_input),
    )


def _issue_interviewer(
    state: SessionState,
    *,
    move: InterviewerMove,
    competency_node_id: str | None,
    move_context: dict[str, Any],
) -> tuple[SessionState, RunInterviewer]:
    """Issue a NEW interviewer move: bump the counter, record it as pending.

    Args:
        state: The state the move is issued from (already carrying every
            other change of this transition).
        move: The move the machine chose — always the machine's decision.
        competency_node_id: Competency the move lands in, if any.
        move_context: The §10 move context for the T18 wrapper.

    Returns:
        The state with turn counter, ``awaiting``, ``last_issued_move`` and
        ``pending_command`` updated, plus the command to emit.
    """
    command = RunInterviewer(
        turn_id=derive_turn_id(state.session_id, _turn_path(state.turn_seq)),
        move=move,
        competency_node_id=competency_node_id,
        move_context=move_context,
    )
    return (
        _evolve(
            state,
            turn_seq=state.turn_seq + 1,
            awaiting="interviewer",
            last_issued_move=move,
            interviewer_failure_streak=0,
            pending_command=command,
        ),
        command,
    )


def _abort(
    state: SessionState,
    reason: AbortReason,
    decision: DecisionReason,
    *,
    persist: bool,
) -> TransitionResult:
    """Enter ``ABORTED`` (§2) with the reason the tabulated edge names.

    Args:
        state: Current state.
        reason: The §2 abort reason recorded on the state.
        decision: The ``RecordDecision`` reason from the §10 table.
        persist: Whether the tabulated edge asks for ``PersistState`` (edge 2
            does not; edges 6, 18 and 19 do).

    Returns:
        The terminal state plus its commands.
    """
    commands: tuple[Command, ...] = (RecordDecision(reason=decision),)
    if persist:
        commands = (*commands, PersistState())
    return TransitionResult(
        new_state=_evolve(
            state,
            phase=Phase.ABORTED,
            abort_reason=reason,
            awaiting=None,
            pending_command=None,
        ),
        commands=commands,
    )


def _enter_close(state: SessionState) -> TransitionResult:
    """Edge 16: enter CLOSE and emit the scripted closing."""
    closing = EmitScriptedClosing(
        turn_id=derive_turn_id(state.session_id, _turn_path(state.turn_seq))
    )
    return TransitionResult(
        new_state=_evolve(
            state,
            phase=Phase.CLOSE,
            awaiting="interviewer",
            last_issued_move=None,
            turn_seq=state.turn_seq + 1,
            pending_command=closing,
        ),
        commands=(closing, PersistState()),
    )


def _complete(state: SessionState) -> TransitionResult:
    """Edge 17: CLOSE → COMPLETED."""
    return TransitionResult(
        new_state=_evolve(
            state,
            phase=Phase.COMPLETED,
            awaiting=None,
            pending_command=None,
        ),
        commands=(EndSession(), RecordDecision(reason="completed")),
    )


def _enter_qa(state: SessionState, now: datetime) -> tuple[SessionState, RunInterviewer]:
    """Edges 13/14: leave TECH for Q&A with one ``acknowledge_and_transition``.

    No assessment is scheduled in QA (§2), and the QA budget clock starts at
    the event timestamp.
    """
    plan = _require_plan(state)
    return _issue_interviewer(
        _evolve(state, phase=Phase.QA, qa_started_at=now),
        move="acknowledge_and_transition",
        competency_node_id=None,
        move_context=_qa_context(plan),
    )


# ---------------------------------------------------------------------------
# Budget predicates (§6.5–6.7) — all evaluated against the event timestamp
# ---------------------------------------------------------------------------


def _candidate_timed_out(state: SessionState, now: datetime, config: OrchestratorConfig) -> bool:
    """§6.6: silence longer than ``candidate_timeout_minutes`` (strict ``>``)."""
    if state.last_candidate_activity is None:
        return False
    limit = timedelta(minutes=config.timing.candidate_timeout_minutes)
    return (now - state.last_candidate_activity) > limit


def _session_budget_exhausted(state: SessionState, now: datetime) -> bool:
    """§6.5: the session has reached ``plan.session_max_minutes``."""
    if state.session_started_at is None or state.plan is None:
        return False
    limit = timedelta(minutes=state.plan.session_max_minutes)
    return (now - state.session_started_at) >= limit


def _qa_budget_exhausted(state: SessionState, now: datetime) -> bool:
    """Edge 16: the Q&A budget from the plan has been reached."""
    if state.qa_started_at is None or state.plan is None:
        return True
    limit = timedelta(minutes=state.plan.qa_minutes)
    return (now - state.qa_started_at) >= limit


# ---------------------------------------------------------------------------
# Coverage updates (§5, §6.3, §6.8)
# ---------------------------------------------------------------------------


def _record_levels(
    coverage: dict[str, CoverageCell], output: AssessorOutput
) -> dict[str, CoverageCell]:
    """Fold one assessor output's per-node levels into coverage.

    ``best_*`` keeps the maximum level, ties resolved toward the later
    assessment; ``latest_*`` always takes the most recent one (§4).
    """
    updated = dict(coverage)
    if not output.assessments:
        # "Not assessable" — distinct from an evidence-backed level 0 (§5).
        cell = updated.get(output.competency_focus, CoverageCell())
        updated[output.competency_focus] = _evolve(cell, gap_not_assessable=True)
        return updated
    for item in output.assessments:
        cell = updated.get(item.rubric_node_id, CoverageCell())
        best_level = cell.best_level
        best_confidence = cell.best_confidence
        if best_level is None or item.level >= best_level:
            best_level = item.level
            best_confidence = item.confidence
        updated[item.rubric_node_id] = _evolve(
            cell,
            best_level=best_level,
            best_confidence=best_confidence,
            latest_level=item.level,
            latest_confidence=item.confidence,
        )
    return updated


def _record_review_signals(
    coverage: dict[str, CoverageCell], output: AssessorOutput
) -> dict[str, CoverageCell]:
    """Fold ``needs_manual_review`` and red flags onto the focus cell (§5)."""
    updated = dict(coverage)
    cell = updated.get(output.competency_focus, CoverageCell())
    updated[output.competency_focus] = _evolve(
        cell,
        needs_manual_review=cell.needs_manual_review or output.needs_manual_review,
        red_flags=(*cell.red_flags, *(flag.type for flag in output.red_flags)),
    )
    return updated


def _drop_pending(tech: TechState, turn_id: UUID) -> TechState:
    """Remove a completed/failed assessment from the pending bookkeeping."""
    return _evolve(
        tech,
        pending_assessments=tuple(t for t in tech.pending_assessments if t != turn_id),
        assessment_focus={k: v for k, v in tech.assessment_focus.items() if k != turn_id},
    )


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------


def _on_session_started(
    state: SessionState, event: SessionStarted, config: OrchestratorConfig
) -> TransitionResult:
    """Edges 1/2: validate the plan, then open with the scripted opening."""
    del config  # thresholds are not consulted at session start
    try:
        plan = PlanSnapshot.validate_plan(state.plan_input)
    except PlanInvalid:
        # Edge 2 — the tabulated command tuple is RecordDecision only.
        return _abort(state, "operator_abort", "plan_invalid", persist=False)

    opening = EmitScriptedOpening(
        turn_id=derive_turn_id(state.session_id, _turn_path(state.turn_seq))
    )
    return TransitionResult(
        new_state=_evolve(
            state,
            phase=Phase.INTRO,
            # The scripted opening is an interviewer action in flight; edge 3
            # accepts the candidate's readiness turn from exactly this state.
            awaiting="interviewer",
            plan=plan,
            session_started_at=event.now,
            last_candidate_activity=event.now,
            turn_seq=state.turn_seq + 1,
            pending_command=opening,
        ),
        commands=(opening, PersistState()),
    )


def _on_intro_candidate_turn(state: SessionState, event: CandidateTurnReceived) -> TransitionResult:
    """Edge 3: readiness confirmed → TECH, ask the first seed.

    The only bare ``ask_seed`` of the session (§10 note). No assessment is
    scheduled for an INTRO turn ("ScheduleNothing" = the command is absent).
    """
    plan = _require_plan(state)
    competency = plan.competencies[0]
    entered = _evolve(
        state,
        phase=Phase.TECH,
        last_candidate_activity=event.now,
        tech=_evolve(
            state.tech,
            competency_index=0,
            seed_index=0,
            probes_used=0,
            competency_started_at=event.now,
        ),
    )
    new_state, command = _issue_interviewer(
        entered,
        move="ask_seed",
        competency_node_id=competency.node_id,
        move_context=_first_seed_context(competency),
    )
    return TransitionResult(new_state=new_state, commands=(command, PersistState()))


def _on_tech_candidate_turn(
    state: SessionState, event: CandidateTurnReceived, config: OrchestratorConfig
) -> TransitionResult:
    """Edge 7 (+10/11/12/13): schedule the assessor, then pick the next move.

    Adjudication runs against the coverage the machine has RIGHT NOW — the
    assessment just scheduled has by definition not completed, which is
    exactly policy ``proceed_planned`` (§6.1). A late result updates coverage
    and influences only future decisions; an issued move is never retracted.
    """
    plan = _require_plan(state)
    competency = _current_competency(state)

    # 1. Schedule the assessor for this turn (never in INTRO/QA).
    assessor = RunAssessor(turn_id=event.turn_id, competency_focus=competency.node_id)
    tech = _evolve(
        state.tech,
        pending_assessments=(*state.tech.pending_assessments, event.turn_id),
        assessment_focus={**state.tech.assessment_focus, event.turn_id: competency.node_id},
    )

    # 2. Adjudicate (§5).
    remaining = _seconds_remaining(competency, tech.competency_started_at, event.now)
    verdict = adjudicate(
        cell=tech.coverage.get(competency.node_id),
        target_level=competency.target_level,
        probes_used=tech.probes_used,
        seconds_remaining=remaining,
        config=config,
    )

    gap: RecordGap | None = None
    if verdict.verdict == "CLARIFY":
        # Edge 11 — probe the planned branch inside the same competency.
        probe_index = tech.probes_used
        tech = _evolve(tech, probes_used=probe_index + 1)
        staged = _evolve(state, last_candidate_activity=event.now, tech=tech)
        new_state, interviewer = _issue_interviewer(
            staged,
            move="depth_probe",
            competency_node_id=competency.node_id,
            move_context=_probe_context(competency, probe_index),
        )
        commands: tuple[Command, ...] = (assessor, interviewer, PersistState())
        return TransitionResult(new_state=new_state, commands=commands)

    if verdict.verdict == "NONE":
        # Edge 12 — record the gap, then leave the competency in ONE call.
        if verdict.gap_marker == "gap_budget_exhausted":
            cell = tech.coverage.get(competency.node_id, CoverageCell())
            tech = _evolve(
                tech,
                coverage={
                    **tech.coverage,
                    competency.node_id: _evolve(cell, gap_budget_exhausted=True),
                },
            )
        marker: GapMarker = verdict.gap_marker or "gap_budget_exhausted"
        gap = RecordGap(node_id=competency.node_id, marker=marker)

    if verdict.verdict == "ANSWERED":
        next_seed = competency.seed_question(tech.seed_index + 1)
        if next_seed is not None and remaining > 0:
            # §4 multi-seed rule — stay on the competency, advance the seed.
            tech = _evolve(tech, seed_index=tech.seed_index + 1)
            staged = _evolve(state, last_candidate_activity=event.now, tech=tech)
            new_state, interviewer = _issue_interviewer(
                staged,
                move="acknowledge_and_transition",
                competency_node_id=competency.node_id,
                move_context=_next_seed_context(competency, tech.seed_index, next_seed),
            )
            return TransitionResult(
                new_state=new_state, commands=(assessor, interviewer, PersistState())
            )

    # ANSWERED with no seed/time left, or NONE: leave this competency.
    following = plan.competency(tech.competency_index + 1)
    advance_move: InterviewerMove = (
        "acknowledge_and_transition" if verdict.verdict == "ANSWERED" else "close_competency"
    )

    if following is None:
        # Edge 13 — the last competency exits (any verdict) → QA.
        staged = _evolve(state, last_candidate_activity=event.now, tech=tech)
        new_state, interviewer = _enter_qa(staged, event.now)
    else:
        tech = _evolve(
            tech,
            competency_index=tech.competency_index + 1,
            seed_index=0,
            probes_used=0,
            competency_started_at=event.now,
        )
        staged = _evolve(state, last_candidate_activity=event.now, tech=tech)
        new_state, interviewer = _issue_interviewer(
            staged,
            move=advance_move,
            competency_node_id=following.node_id,
            move_context=_advance_context(competency, following),
        )

    tail: tuple[Command, ...] = () if gap is None else (gap,)
    return TransitionResult(
        new_state=new_state, commands=(assessor, interviewer, *tail, PersistState())
    )


def _on_qa_candidate_turn(state: SessionState, event: CandidateTurnReceived) -> TransitionResult:
    """Edges 15/16: answer the candidate's question, or close when time is up."""
    heard = _evolve(state, last_candidate_activity=event.now)
    if _qa_budget_exhausted(state, event.now):
        return _enter_close(heard)
    plan = _require_plan(state)
    new_state, interviewer = _issue_interviewer(
        heard,
        move="acknowledge_and_transition",
        competency_node_id=None,
        move_context=_qa_context(plan),
    )
    # Edge 15 tabulates exactly one command — and never a RunAssessor (§2 QA).
    return TransitionResult(new_state=new_state, commands=(interviewer,))


def _on_candidate_turn(
    state: SessionState, event: CandidateTurnReceived, config: OrchestratorConfig
) -> TransitionResult:
    """Route a candidate turn by phase (edges 3, 7, 15/16)."""
    if state.phase is Phase.INTRO:
        return _on_intro_candidate_turn(state, event)
    if state.phase is Phase.TECH:
        if state.awaiting != "candidate":
            # Edge 7's guard: no answer is expected while a move is in flight.
            return _ignore(state)
        return _on_tech_candidate_turn(state, event, config)
    if state.phase is Phase.QA:
        return _on_qa_candidate_turn(state, event)
    return _ignore(state)


def _on_interviewer_reply(
    state: SessionState, event: InterviewerReplyReady, config: OrchestratorConfig
) -> TransitionResult:
    """Edge 4 (and edge 17 in CLOSE): deliver the utterance, note any drift."""
    if not _answers_pending_command(state, event.turn_id):
        # §6.9a — a reply for a superseded turn is untabulated.
        return _ignore(state)
    if state.phase is Phase.CLOSE:
        return _complete(state)
    if state.phase not in (Phase.TECH, Phase.QA) or state.awaiting != "interviewer":
        return _ignore(state)

    tech = state.tech
    flagged = state.flagged_for_review
    if (
        state.last_issued_move is not None
        and event.output.internal_move_executed != state.last_issued_move
    ):
        # §6.4 — count the drift; the ISSUED move stays authoritative.
        tech = _evolve(tech, drift_count=tech.drift_count + 1)
        flagged = flagged or tech.drift_count >= config.flags.drift_to_review
    delivery = DeliverUtterance(turn_id=event.turn_id, utterance=event.output.utterance)
    return TransitionResult(
        new_state=_evolve(
            state,
            awaiting="candidate",
            interviewer_failure_streak=0,
            tech=tech,
            flagged_for_review=flagged,
            pending_command=delivery,
        ),
        commands=(delivery, PersistState()),
    )


def _on_interviewer_failed(state: SessionState, event: InterviewerFailed) -> TransitionResult:
    """Edges 5/6: repeat the move once, then abort on a second consecutive miss."""
    if not _answers_pending_command(state, event.turn_id):
        # §6.9a — a failure for a superseded turn never advances the ladder.
        return _ignore(state)
    if state.phase not in (Phase.TECH, Phase.QA) or state.awaiting != "interviewer":
        return _ignore(state)
    pending = state.pending_command
    if not isinstance(pending, RunInterviewer):
        return _ignore(state)
    if state.interviewer_failure_streak >= 1:
        # Edge 6 — second consecutive failure.
        return _abort(state, "fatal_agent_error", "agent_failure", persist=True)
    # Edge 5 — same move, same turn (second attempt), retry flag set.
    retry = _evolve(pending, retry=True)
    return TransitionResult(
        new_state=_evolve(
            state,
            interviewer_failure_streak=state.interviewer_failure_streak + 1,
            pending_command=retry,
        ),
        commands=(
            retry,
            FlagTurnDegraded(turn_id=event.turn_id, error_kind=event.error_kind),
            PersistState(),
        ),
    )


def _on_assessment_completed(
    state: SessionState, event: AssessmentCompleted, config: OrchestratorConfig
) -> TransitionResult:
    """Edge 8: fold a completed assessment into coverage, in any live phase (§6.8)."""
    if event.for_turn_id not in state.tech.pending_assessments:
        return _ignore(state)
    output = event.output
    coverage = _record_review_signals(_record_levels(state.tech.coverage, output), output)
    tech = _evolve(_drop_pending(state.tech, event.for_turn_id), coverage=coverage)

    cheat_flags = sum(1 for flag in output.red_flags if flag.type == CHEAT_RED_FLAG)
    cheat_total = state.cheat_flag_count + cheat_flags
    return TransitionResult(
        new_state=_evolve(
            state,
            tech=tech,
            cheat_flag_count=cheat_total,
            needs_manual_review=state.needs_manual_review or output.needs_manual_review,
            flagged_for_review=(
                state.flagged_for_review or cheat_total >= config.flags.cheat_flags_to_review
            ),
        ),
        commands=(PersistState(),),
    )


def _on_assessment_failed(state: SessionState, event: AssessmentFailed) -> TransitionResult:
    """Edge 9: mark the cell failed (§6.3). Never aborts — it becomes reviewer work."""
    if event.for_turn_id not in state.tech.pending_assessments:
        return _ignore(state)
    node_id = state.tech.assessment_focus.get(event.for_turn_id)
    tech = _drop_pending(state.tech, event.for_turn_id)
    if node_id is not None:
        cell = tech.coverage.get(node_id, CoverageCell())
        tech = _evolve(
            tech, coverage={**tech.coverage, node_id: _evolve(cell, assessment_failed=True)}
        )
    return TransitionResult(new_state=_evolve(state, tech=tech), commands=(PersistState(),))


def _on_timer_tick(
    state: SessionState, event: TimerTick, config: OrchestratorConfig
) -> TransitionResult:
    """Edges 14/16/17/18 with the §6.7 priority order applied on one tick."""
    # 1. §6.7 — candidate silence beats every budget.
    if _candidate_timed_out(state, event.now, config):
        return _abort(state, "candidate_timeout", "timeout", persist=True)

    # 2. Edge 14 — the session budget.
    if state.phase is Phase.TECH and _session_budget_exhausted(state, event.now):
        new_state, interviewer = _enter_qa(state, event.now)
        return TransitionResult(new_state=new_state, commands=(interviewer,))
    if state.phase is Phase.QA and _session_budget_exhausted(state, event.now):
        return _enter_close(state)

    # 3. Edge 16 — the Q&A budget.
    if state.phase is Phase.QA and _qa_budget_exhausted(state, event.now):
        return _enter_close(state)

    # 4. Edge 17 — CLOSE completes without waiting for a model call.
    if state.phase is Phase.CLOSE:
        return _complete(state)

    return _ignore(state)


def _on_reconnected(state: SessionState) -> TransitionResult:
    """Edge 21: re-issue the outstanding command; ids make it idempotent (§6.9)."""
    if state.pending_command is None:
        return TransitionResult(new_state=state, commands=(PersistState(),))
    return TransitionResult(
        new_state=state,
        commands=(ReissuePendingCommand(command=state.pending_command), PersistState()),
    )


# ---------------------------------------------------------------------------
# The transition function
# ---------------------------------------------------------------------------


def transition(state: SessionState, event: Event, config: OrchestratorConfig) -> TransitionResult:
    """Apply one event to the session state (§10, the normative table).

    Pure: no I/O, no clock, no randomness. Events not tabulated for the
    current phase are no-ops — the machine never guesses.

    Args:
        state: The current session state.
        event: The event to apply.
        config: The loaded ``configs/orchestrator.yaml`` thresholds.

    Returns:
        The new state and the commands the shell must execute, in order.

    Raises:
        OrchestratorStateError: The state is internally inconsistent (e.g. a
            TECH state with no validated plan) — an invariant violation, not
            a runtime condition.
    """
    # Edge 20 — terminal states are idempotent sinks for every event.
    if state.phase in TERMINAL_PHASES:
        return _ignore(state)

    # Edges 8/9 — late assessments are accepted in ANY non-terminal phase
    # while their turn is still pending (§6.8).
    if isinstance(event, AssessmentCompleted):
        return _on_assessment_completed(state, event, config)
    if isinstance(event, AssessmentFailed):
        return _on_assessment_failed(state, event)

    # Edge 19 — operator abort from any non-terminal phase.
    if isinstance(event, OperatorAbort):
        return _abort(state, event.reason, "operator", persist=True)

    # Edge 21 — resume.
    if isinstance(event, Reconnected):
        return _on_reconnected(state)

    # Edges 14/16/17/18 — every clock-driven transition, §6.7 priority inside.
    if isinstance(event, TimerTick):
        return _on_timer_tick(state, event, config)

    if state.phase is Phase.CREATED:
        # Edges 1/2 are the only way out of `created`.
        if isinstance(event, SessionStarted):
            return _on_session_started(state, event, config)
        return _ignore(state)

    if isinstance(event, CandidateTurnReceived):
        return _on_candidate_turn(state, event, config)
    if isinstance(event, InterviewerReplyReady):
        return _on_interviewer_reply(state, event, config)
    if isinstance(event, InterviewerFailed):
        return _on_interviewer_failed(state, event)
    return _ignore(state)
