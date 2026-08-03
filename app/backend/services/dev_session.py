"""The imperative shell over the T20 orchestrator (dev-only surface, T22).

Normative design: ``docs/contracts/dev-session-api.yaml`` (the HTTP surface)
and ``docs/contracts/state-machine.md`` §9 (the shell's obligations). The pure
core lives in :mod:`app.backend.orchestrator.state_machine` and is NOT touched
from here — this module only executes the commands the core returns and feeds
results back as new events.

The three obligations §9 / spec-032 Clarification 4 place on the shell:

1. **Persist after EVERY transition, BEFORE issuing wrapper calls.** A crash
   then resumes at the last consistent point. ``PersistState`` commands are
   advisory markers; :meth:`DevSessionService._drive` persists regardless.
2. **Assessor calls never block the turn.** ``RunAssessor`` is handed to a
   :class:`TaskScheduler`; its ``AssessmentCompleted`` / ``AssessmentFailed``
   result re-enters through the same transition + persist path.
3. **Command ids are the machine's.** Re-issue after a resume is idempotent by
   construction (uuid5, §6.9), so the shell dedupes on ``turn_id`` rather than
   inventing ids of its own. Candidate turn ids are likewise derived, not
   random.

Two things the machine deliberately does not own and this module therefore
does:

- **Scripted opening / closing.** ``EmitScriptedOpening`` /
  ``EmitScriptedClosing`` carry a path into ``prompts/shared/candidate-facing/``;
  the text is read from that repo artefact and delivered as a ``role=system``
  transcript entry. No model call, and no candidate-facing prose is authored
  here (constitution §11 / spec Clarification 3).
- **The transcript.** ``SessionState`` forbids extra keys, so the shell keeps
  its own chronological log in ``interview_session.dev_transcript`` — mutable
  working state beside ``session_state``, under the same §3 carve-out.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from collections.abc import Awaitable, Callable, Coroutine, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, Literal, Protocol
from uuid import UUID, uuid5

import structlog
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backend.agents.assessor import (
    PROMPT_VERSION as ASSESSOR_PROMPT_VERSION,
)
from app.backend.agents.assessor import (
    AssessorOutputInvalid,
    AssessorTurnInput,
    run_assessor_turn,
)
from app.backend.agents.assessor import (
    load_system_prompt as load_assessor_system_prompt,
)
from app.backend.agents.interviewer import (
    PROMPT_VERSION as INTERVIEWER_PROMPT_VERSION,
)
from app.backend.agents.interviewer import (
    InterviewerOutputInvalid,
    InterviewerTurnInputs,
    RecentTurn,
    run_interviewer_turn,
)

# The Interviewer wrapper assembles its system prompt and user payload
# internally; the audit row contract (docs/contracts/turn-trace.schema.json)
# wants both verbatim. Re-implementing the assembly here would silently drift
# from the wrapper the moment either side changed, so the shell reuses the
# wrapper's own two helpers. They are module-private only because no caller
# needed them before T21; the Assessor's equivalents (load_system_prompt /
# AssessorTurnInput.to_user_payload) are already public.
from app.backend.agents.interviewer import (
    _load_system_prompt as load_interviewer_system_prompt,
)
from app.backend.agents.interviewer import (
    _serialize_user_payload as serialize_interviewer_payload,
)
from app.backend.llm.errors import SessionBudgetExceeded, WrapperError
from app.backend.llm.persistent_cost import PostgresCostLedger
from app.backend.llm.persistent_trace import (
    PostgresTraceSink,
    TransitionContext,
    TurnTraceContext,
)
from app.backend.orchestrator.config import OrchestratorConfig
from app.backend.orchestrator.persistence import (
    InterviewSessionNotFound,
    encode_session_state,
    load_session_state,
    save_session_state,
)
from app.backend.orchestrator.plan import PlannedCompetency, PlanSnapshot, plan_payload
from app.backend.orchestrator.state_machine import (
    AssessmentCompleted,
    AssessmentFailed,
    CandidateTurnReceived,
    Command,
    DeliverUtterance,
    EmitScriptedClosing,
    EmitScriptedOpening,
    EndSession,
    Event,
    FlagTurnDegraded,
    InterviewerFailed,
    InterviewerReplyReady,
    OperatorAbort,
    PersistState,
    Phase,
    RecordDecision,
    RecordGap,
    ReissuePendingCommand,
    RunAssessor,
    RunInterviewer,
    SessionStarted,
    SessionState,
    TimerTick,
    initial_state,
    transition,
)
from app.backend.services.feature_flags import is_enabled
from app.backend.settings import Settings

_LOGGER = structlog.get_logger("app.backend.services.dev_session")

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[3]

_MAX_DRIVE_STEPS: Final[int] = 64
"""Safety valve on the event/command loop. The tabulated edges terminate on
their own; a runaway means the machine and the shell disagree, and failing loudly
beats spinning while a candidate waits."""

_RECENT_TURNS_MAX: Final[int] = 8
"""Interviewer system.md §3 caps ``recent_turns`` at the last 8 exchanges."""

_PRIOR_TURNS_MAX: Final[int] = 4
"""Assessor system.md §3 asks for the last four exchanges in the competency."""

_SCRIPT_STRING_HEADING: Final[str] = "## string"

TranscriptRole = Literal["interviewer", "candidate", "system"]
ViewPhase = Literal["INTRO", "TECH", "QA", "CLOSE", "COMPLETED", "ABORTED"]

_VIEW_PHASES: Final[Mapping[Phase, ViewPhase]] = {
    Phase.INTRO: "INTRO",
    Phase.TECH: "TECH",
    Phase.QA: "QA",
    Phase.CLOSE: "CLOSE",
    Phase.COMPLETED: "COMPLETED",
    Phase.ABORTED: "ABORTED",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class DevSessionError(Exception):
    """Base for every failure this module raises."""


class DevSessionNotFound(DevSessionError):
    """No dev session exists with the requested id."""


class DevSessionPlanInvalid(DevSessionError):
    """The machine refused the plan at session start (contract §7, edge 2)."""


class DevSessionNotAwaitingCandidate(DevSessionError):
    """The session is terminal, or is not waiting for a candidate turn."""


class DevSessionRunawayError(DevSessionError):
    """The event/command loop exceeded :data:`_MAX_DRIVE_STEPS`."""


# ---------------------------------------------------------------------------
# Scheduling seam (obligation 2)
# ---------------------------------------------------------------------------


class TaskScheduler(Protocol):
    """Runs a coroutine outside the current request/response cycle."""

    def schedule(self, task: Callable[[], Coroutine[Any, Any, None]]) -> None:
        """Register ``task`` to run after the caller has finished."""
        ...


class ImmediateTaskScheduler:
    """Collects scheduled tasks and runs them on demand.

    Used by tests and by any caller that wants the assessor's effect to be
    observable before it returns. Never used by the HTTP layer — there, the
    contract's "never block the response" is what matters.
    """

    def __init__(self) -> None:
        self._tasks: list[Callable[[], Coroutine[Any, Any, None]]] = []

    def schedule(self, task: Callable[[], Coroutine[Any, Any, None]]) -> None:
        self._tasks.append(task)

    @property
    def pending(self) -> int:
        """How many tasks are queued."""
        return len(self._tasks)

    async def drain(self) -> None:
        """Run every queued task, in order, including ones they enqueue."""
        while self._tasks:
            task = self._tasks.pop(0)
            await task()


# ---------------------------------------------------------------------------
# View models (docs/contracts/dev-session-api.yaml components)
# ---------------------------------------------------------------------------


class TranscriptEntry(BaseModel):
    """One chronological message in the dev chat log."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: TranscriptRole
    text: str
    turn_id: UUID | None = None


class SessionView(BaseModel):
    """``SessionView`` from the dev-session contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: UUID
    phase: ViewPhase
    abort_reason: str | None = None
    awaiting: Literal["interviewer", "candidate"] | None
    competency_index: int | None
    coverage: dict[str, Any]
    flagged_for_review: bool
    cost_usd_total: str
    transcript: list[TranscriptEntry]


class TurnResult(BaseModel):
    """``devPostTurn``'s 200 body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    utterance: str | None
    session: SessionView


class TraceRow(BaseModel):
    """One ``turn_trace`` row, shaped by ``docs/contracts/turn-trace.schema.json``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: UUID
    created_at: datetime
    interview_session_id: UUID | None
    turn_id: UUID | None
    agent: str
    prompt_version: str
    model: str
    model_version: str | None
    outcome: str
    wrapper_outcome: str | None
    attempts: int
    latency_ms: int
    input_tokens: int
    output_tokens: int
    cost_usd: str
    prompt_sha: str
    system_prompt: str
    user_payload: str
    response_text: str
    parsed: dict[str, Any] | None
    error_message: str | None
    transition: dict[str, Any] | None


class TraceList(BaseModel):
    """``devListTraces``'s 200 body."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    traces: list[TraceRow]


# ---------------------------------------------------------------------------
# Scripted candidate-facing strings (spec Clarification 3)
# ---------------------------------------------------------------------------


def _extract_script(markdown: str) -> str:
    """Pull the Ukrainian blockquote out of a candidate-facing script file.

    The files under ``prompts/shared/candidate-facing/`` are documents: prose,
    then a ``## String (Ukrainian)`` section holding the deliverable text as a
    blockquote, then a variables table. Only the blockquote is candidate-facing.

    Args:
        markdown: The whole file contents.

    Returns:
        The blockquote with its ``>`` markers stripped, paragraphs preserved.

    Raises:
        DevSessionError: The file has no ``## String`` blockquote — a broken
            deploy, not a runtime condition.
    """
    collecting = False
    lines: list[str] = []
    for raw in markdown.splitlines():
        stripped = raw.strip()
        if stripped.lower().startswith(_SCRIPT_STRING_HEADING):
            collecting = True
            continue
        if not collecting:
            continue
        if stripped.startswith("## ") or (stripped.startswith("---") and lines):
            break
        if stripped.startswith(">"):
            lines.append(stripped.lstrip(">").strip())
    text_out = "\n".join(lines).strip()
    if not text_out:
        raise DevSessionError("candidate-facing script has no '## String' blockquote")
    return re.sub(r"\n{3,}", "\n\n", text_out)


def _render_script(script_path: str, variables: Mapping[str, str]) -> str:
    """Read a scripted string and substitute its ``{Placeholder}`` variables.

    Args:
        script_path: Repo-relative path carried by the machine's command.
        variables: Placeholder name (without braces) → replacement.

    Returns:
        The rendered Ukrainian text.

    Raises:
        DevSessionError: The artefact is missing or holds no blockquote.
    """
    path = _REPO_ROOT / script_path
    try:
        markdown = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DevSessionError(
            f"candidate-facing script {script_path} is unreadable: {exc}"
        ) from exc
    rendered = _extract_script(markdown)
    for name, value in variables.items():
        rendered = rendered.replace(f"{{{name}}}", value)
    return rendered


# ---------------------------------------------------------------------------
# Working state
# ---------------------------------------------------------------------------


@dataclass
class _Working:
    """The shell's in-flight view of one session: machine state + transcript."""

    session_id: UUID
    state: SessionState
    transcript: list[TranscriptEntry] = field(default_factory=list)

    def append(self, role: TranscriptRole, text_value: str, turn_id: UUID | None) -> None:
        self.transcript.append(TranscriptEntry(role=role, text=text_value, turn_id=turn_id))


def _state_sha(state: SessionState) -> str:
    """SHA-256 of the canonical ``SessionState`` JSON (contract §1)."""
    canonical = json.dumps(encode_session_state(state), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _candidate_turn_id(session_id: UUID, ordinal: int) -> UUID:
    """Derive a deterministic id for the ``ordinal``-th candidate turn.

    The machine derives its own command ids from ``uuid5(session_id, path)``
    (§6.9); candidate turns are the shell's to name, so they use the same
    recipe with a distinct path prefix. Deterministic ids keep a re-POSTed turn
    from being scheduled for assessment twice.
    """
    return uuid5(session_id, f"candidate-turn/{ordinal}")


# ---------------------------------------------------------------------------
# The service
# ---------------------------------------------------------------------------


class DevSessionService:
    """Executes orchestrator commands against the real agents and the database."""

    def __init__(
        self,
        *,
        engine: AsyncEngine,
        settings: Settings,
        config: OrchestratorConfig,
        scheduler: TaskScheduler,
        ceiling_usd: Decimal | None = None,
        enforcement: Callable[[], Awaitable[bool]] | None = None,
    ) -> None:
        """Wire the shell.

        Args:
            engine: Async engine for session state, transcript, traces and
                decisions.
            settings: Runtime settings passed through to the agent wrappers.
            config: The loaded ``configs/orchestrator.yaml`` thresholds.
            scheduler: Where ``RunAssessor`` work goes (obligation 2).
            ceiling_usd: Override for the §12 per-session ceiling (tests).
            enforcement: Predicate deciding whether a ceiling breach aborts.
                Defaults to the ``enforce_session_cost_ceiling`` feature flag.
        """
        self._engine = engine
        self._settings = settings
        self._config = config
        self._scheduler = scheduler
        self._ledger = PostgresCostLedger(
            engine,
            ceiling_usd=ceiling_usd,
            enforcement=enforcement if enforcement is not None else _ceiling_enforced,
        )

    # ---------- public API (one method per contract operation) ----------

    async def create_session(
        self, plan: Mapping[str, Any], *, session_id: UUID | None = None
    ) -> SessionView:
        """Create a session from an inline plan and run ``SessionStarted``.

        Args:
            plan: The raw contract §7 plan payload.
            session_id: Optional explicit id. The HTTP layer never supplies
                one; deterministic tests do, because uuid5 command ids (and
                therefore the mock backend's prompt SHAs) are derived from it.

        Returns:
            The post-start :class:`SessionView` (phase ``INTRO``).

        Raises:
            DevSessionPlanInvalid: The machine refused the plan (edge 2). The
                session row survives in ``ABORTED`` so the rejection is
                auditable.
        """
        created_id = await self._insert_session(session_id)
        working = _Working(
            session_id=created_id,
            state=initial_state(session_id=created_id, plan_input=plan, config=self._config),
        )
        await self._persist(working)
        await self._drive(working, SessionStarted(now=_now()))
        if working.state.phase is Phase.ABORTED and working.state.plan is None:
            raise DevSessionPlanInvalid(
                f"plan rejected by the orchestrator (state-machine contract §7); "
                f"session {created_id} recorded as ABORTED"
            )
        return await self._view(working)

    async def get_session(self, session_id: UUID) -> SessionView:
        """Return the current view of a session.

        Raises:
            DevSessionNotFound: No such session, or it has no orchestrator
                state (never started).
        """
        return await self._view(await self._load(session_id))

    async def post_turn(self, session_id: UUID, candidate_text: str) -> TurnResult:
        """Apply a candidate turn and run the machine until it waits again.

        Args:
            session_id: The session receiving the turn.
            candidate_text: The candidate's Ukrainian answer. NEVER inspected
                by the core (constitution §2) — it only travels to the wrappers.

        Returns:
            The interviewer's next utterance (``None`` when the session ended
            on this turn) plus the post-transition view.

        Raises:
            DevSessionNotFound: No such session.
            DevSessionNotAwaitingCandidate: Terminal, or a move is in flight.
        """
        working = await self._load(session_id)
        if working.state.phase in (Phase.COMPLETED, Phase.ABORTED):
            raise DevSessionNotAwaitingCandidate(f"session {session_id} is terminal")
        if working.state.phase is not Phase.INTRO and working.state.awaiting != "candidate":
            raise DevSessionNotAwaitingCandidate(
                f"session {session_id} is not awaiting a candidate turn"
            )

        ordinal = sum(1 for entry in working.transcript if entry.role == "candidate")
        turn_id = _candidate_turn_id(session_id, ordinal)
        working.append("candidate", candidate_text, turn_id)
        before = len(working.transcript)
        await self._drive(
            working, CandidateTurnReceived(turn_id=turn_id, text=candidate_text, now=_now())
        )
        utterance = next(
            (
                entry.text
                for entry in reversed(working.transcript[before:])
                if entry.role == "interviewer"
            ),
            None,
        )
        return TurnResult(utterance=utterance, session=await self._view(working))

    async def list_traces(self, session_id: UUID) -> TraceList:
        """Return every ``turn_trace`` row for a session, oldest first.

        Raises:
            DevSessionNotFound: No such session.
        """
        await self._load(session_id)
        async with self._engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT id, created_at, interview_session_id, turn_id, agent, "
                        "prompt_version, model, model_version, outcome, wrapper_outcome, "
                        "attempts, latency_ms, input_tokens, output_tokens, cost_usd, "
                        "prompt_sha, system_prompt, user_payload, response_text, parsed, "
                        "error_message, transition "
                        "FROM turn_trace WHERE interview_session_id = :sid "
                        "ORDER BY created_at, id"
                    ),
                    {"sid": session_id},
                )
            ).mappings()
            return TraceList(
                traces=[
                    TraceRow.model_validate({**row, "cost_usd": str(row["cost_usd"])})
                    for row in rows
                ]
            )

    # ---------- the drive loop (obligation 1) ----------

    async def _drive(self, working: _Working, event: Event) -> None:
        """Apply ``event`` and everything it cascades into.

        The ordering §9 mandates is the body of this loop: transition, PERSIST,
        then execute the commands (which is where wrapper calls happen), then
        fold the resulting events back in.
        """
        queue: deque[Event] = deque([event])
        steps = 0
        while queue:
            steps += 1
            if steps > _MAX_DRIVE_STEPS:
                raise DevSessionRunawayError(
                    f"session {working.session_id}: more than {_MAX_DRIVE_STEPS} events in one "
                    "turn — the shell and the machine disagree"
                )
            current = queue.popleft()
            before_sha = _state_sha(working.state)
            result = transition(working.state, current, self._config)
            working.state = result.new_state
            after_sha = _state_sha(working.state)
            await self._persist(working)
            transcript_mark = len(working.transcript)
            follow_ups = await self._execute(
                working, result.commands, before_sha=before_sha, after_sha=after_sha
            )
            if len(working.transcript) != transcript_mark:
                # Delivering an utterance or a scripted string is a durable
                # effect too: the state is unchanged, the chat log is not.
                await self._persist(working)
            queue.extend(follow_ups)

    async def _execute(
        self,
        working: _Working,
        commands: Sequence[Command],
        *,
        before_sha: str,
        after_sha: str,
    ) -> list[Event]:
        """Run one transition's commands in order; return the events they produce."""
        events: list[Event] = []
        for command in commands:
            events.extend(
                await self._execute_one(
                    working, command, before_sha=before_sha, after_sha=after_sha
                )
            )
        return events

    async def _execute_one(
        self,
        working: _Working,
        command: Command,
        *,
        before_sha: str,
        after_sha: str,
    ) -> list[Event]:
        """Execute a single command. Returns any follow-up events."""
        match command:
            case PersistState():
                # §9: advisory marker. _drive already persisted.
                return []
            case EmitScriptedOpening() | EmitScriptedClosing():
                working.append(
                    "system",
                    _render_script(command.script_path, self._script_variables(working)),
                    command.turn_id,
                )
                # The closing is the last thing the candidate reads; edge 17
                # completes the session without waiting for a model call.
                if isinstance(command, EmitScriptedClosing):
                    return [TimerTick(now=_now())]
                return []
            case DeliverUtterance():
                working.append("interviewer", command.utterance, command.turn_id)
                return []
            case RunInterviewer():
                return await self._run_interviewer(
                    working, command, before_sha=before_sha, after_sha=after_sha
                )
            case RunAssessor():
                self._schedule_assessor(
                    working, command, before_sha=before_sha, after_sha=after_sha
                )
                return []
            case ReissuePendingCommand():
                return await self._execute_one(
                    working, command.command, before_sha=before_sha, after_sha=after_sha
                )
            case RecordDecision():
                await self._record_decision(working, command)
                return []
            case RecordGap():
                _LOGGER.info(
                    "orchestrator_gap_recorded",
                    session_id=str(working.session_id),
                    node_id=command.node_id,
                    marker=command.marker,
                )
                return []
            case FlagTurnDegraded():
                _LOGGER.warning(
                    "orchestrator_turn_degraded",
                    session_id=str(working.session_id),
                    turn_id=str(command.turn_id),
                    error_kind=command.error_kind,
                )
                return []
            case EndSession():
                _LOGGER.info(
                    "orchestrator_session_ended",
                    session_id=str(working.session_id),
                    outcome=command.outcome,
                )
                return []
        # Unreachable while `Command` stays the eleven variants above; a new
        # variant must be handled here rather than silently ignored.
        raise DevSessionError(f"unhandled orchestrator command {type(command).__name__}")

    # ---------- agent calls ----------

    async def _run_interviewer(
        self,
        working: _Working,
        command: RunInterviewer,
        *,
        before_sha: str,
        after_sha: str,
    ) -> list[Event]:
        """Call the T18 wrapper for one move, and translate the outcome to an event."""
        try:
            await self._ledger.guard_session_budget(working.session_id)
        except SessionBudgetExceeded:
            return [OperatorAbort(reason="cost_ceiling", now=_now())]

        inputs = self._interviewer_inputs(working, command)
        sink = PostgresTraceSink(self._engine)
        context = TurnTraceContext(
            prompt_version=INTERVIEWER_PROMPT_VERSION,
            turn_id=command.turn_id,
            system_prompt=load_interviewer_system_prompt(),
            user_payload=serialize_interviewer_payload(inputs),
            transition=TransitionContext(
                phase=working.state.phase.value,
                issued_move=command.move,
                state_before_sha=before_sha,
                state_after_sha=after_sha,
            ),
        )
        try:
            with sink.bind(context):
                output = await run_interviewer_turn(
                    inputs, sink=sink, ledger=self._ledger, settings=self._settings
                )
        except InterviewerOutputInvalid:
            return [
                InterviewerFailed(
                    turn_id=command.turn_id, error_kind="interviewer_output_invalid", now=_now()
                )
            ]
        except WrapperError as exc:
            return [
                InterviewerFailed(
                    turn_id=command.turn_id, error_kind=type(exc).__name__, now=_now()
                )
            ]
        return [InterviewerReplyReady(turn_id=command.turn_id, output=output, now=_now())]

    def _schedule_assessor(
        self,
        working: _Working,
        command: RunAssessor,
        *,
        before_sha: str,
        after_sha: str,
    ) -> None:
        """Hand one ``RunAssessor`` to the scheduler (never awaited here, §6.1)."""
        session_id = working.session_id
        inputs = self._assessor_inputs(working, command)
        phase = working.state.phase.value

        async def _task() -> None:
            event = await self._run_assessor(
                session_id, command, inputs, phase=phase, before_sha=before_sha, after_sha=after_sha
            )
            reloaded = await self._load(session_id)
            await self._drive(reloaded, event)

        self._scheduler.schedule(_task)

    async def _run_assessor(
        self,
        session_id: UUID,
        command: RunAssessor,
        inputs: AssessorTurnInput,
        *,
        phase: str,
        before_sha: str,
        after_sha: str,
    ) -> Event:
        """Call the T19 wrapper and translate the outcome to an event (§6.3)."""
        try:
            await self._ledger.guard_session_budget(session_id)
        except SessionBudgetExceeded:
            return OperatorAbort(reason="cost_ceiling", now=_now())

        sink = PostgresTraceSink(self._engine)
        context = TurnTraceContext(
            prompt_version=ASSESSOR_PROMPT_VERSION,
            turn_id=command.turn_id,
            system_prompt=load_assessor_system_prompt(),
            user_payload=inputs.to_user_payload(),
            transition=TransitionContext(
                phase=phase,
                issued_move=None,
                state_before_sha=before_sha,
                state_after_sha=after_sha,
            ),
        )
        try:
            with sink.bind(context):
                output = await run_assessor_turn(
                    inputs, sink=sink, ledger=self._ledger, settings=self._settings
                )
        except AssessorOutputInvalid:
            return AssessmentFailed(
                for_turn_id=command.turn_id, error_kind="assessor_output_invalid", now=_now()
            )
        except WrapperError as exc:
            return AssessmentFailed(
                for_turn_id=command.turn_id, error_kind=type(exc).__name__, now=_now()
            )
        return AssessmentCompleted(for_turn_id=command.turn_id, output=output, now=_now())

    # ---------- agent input assembly ----------

    def _script_variables(self, working: _Working) -> Mapping[str, str]:
        """Placeholders for the candidate-facing scripts.

        A dev session has no candidate record, so ``FirstName`` takes the
        fallback the script file itself documents.
        """
        plan = working.state.plan
        area = plan.competencies[0].label_uk if plan is not None else "технічне інтерв'ю"
        minutes = str(plan.session_max_minutes) if plan is not None else "30"
        return {"FirstName": "колего", "Area": area, "ExpectedMinutes": minutes}

    def _competency(self, state: SessionState, node_id: str | None) -> PlannedCompetency | None:
        if node_id is None or state.plan is None:
            return None
        return next((c for c in state.plan.competencies if c.node_id == node_id), None)

    def _recent_turns(self, working: _Working) -> tuple[RecentTurn, ...]:
        """Last ≤ 8 exchanges as the Interviewer prompt consumes them.

        ``system`` entries are the scripted opening/closing — interviewer
        speech the candidate read, so they enter the model's view as
        ``interviewer`` turns (``RecentTurn`` has no third role).
        """
        tail = [entry for entry in working.transcript if entry.text][-_RECENT_TURNS_MAX:]
        return tuple(
            RecentTurn(
                role="candidate" if entry.role == "candidate" else "interviewer", text=entry.text
            )
            for entry in tail
        )

    def _interviewer_inputs(
        self, working: _Working, command: RunInterviewer
    ) -> InterviewerTurnInputs:
        state = working.state
        competency = self._competency(state, command.competency_node_id)
        return InterviewerTurnInputs(
            session_id=working.session_id,
            interview_plan_snapshot=plan_payload(state.plan) if state.plan is not None else {},
            current_competency={} if competency is None else competency.model_dump(mode="json"),
            recent_turns=self._recent_turns(working),
            next_planned_move=command.move,
            move_context=command.move_context,
            candidate_first_name=None,
        )

    def _assessor_inputs(self, working: _Working, command: RunAssessor) -> AssessorTurnInput:
        exchanges = [entry for entry in working.transcript if entry.text]
        answer = next(
            (entry.text for entry in reversed(exchanges) if entry.role == "candidate"), ""
        )
        question = next(
            (entry.text for entry in reversed(exchanges[:-1]) if entry.role != "candidate"), ""
        )
        return AssessorTurnInput(
            session_id=working.session_id,
            turn_id=command.turn_id,
            competency_focus=command.competency_focus,
            rubric_snapshot_subset=[],
            turn={"question": question, "answer": answer},
            prior_turns=[
                {"role": entry.role, "text": entry.text}
                for entry in exchanges[:-2][-_PRIOR_TURNS_MAX:]
            ],
            turn_metadata={},
        )

    # ---------- persistence ----------

    async def _insert_session(self, session_id: UUID | None) -> UUID:
        """Insert the ``interview_session`` row this dev session runs on."""
        async with self._engine.begin() as conn:
            if session_id is None:
                result = await conn.execute(
                    text("INSERT INTO interview_session DEFAULT VALUES RETURNING id")
                )
            else:
                result = await conn.execute(
                    text("INSERT INTO interview_session (id) VALUES (:sid) RETURNING id"),
                    {"sid": session_id},
                )
            created: UUID = result.scalar_one()
        return created

    async def _persist(self, working: _Working) -> None:
        """Write ``session_state`` + the transcript in one transaction (§9)."""
        payload = [entry.model_dump(mode="json") for entry in working.transcript]
        async with self._engine.begin() as conn:
            await save_session_state(conn, working.session_id, working.state)
            await conn.execute(
                text(
                    "UPDATE interview_session SET dev_transcript = CAST(:t AS JSONB) "
                    "WHERE id = :sid"
                ),
                {"t": json.dumps(payload, ensure_ascii=False), "sid": working.session_id},
            )

    async def _load(self, session_id: UUID) -> _Working:
        """Rehydrate machine state + transcript, or fail with a typed error."""
        async with self._engine.connect() as conn:
            try:
                state = await load_session_state(
                    conn, session_id, expected_version=self._config.state_schema_version
                )
            except InterviewSessionNotFound as exc:
                raise DevSessionNotFound(str(exc)) from exc
            if state is None:
                raise DevSessionNotFound(f"session {session_id} has no orchestrator state")
            raw = (
                await conn.execute(
                    text("SELECT dev_transcript FROM interview_session WHERE id = :sid"),
                    {"sid": session_id},
                )
            ).scalar_one()
        return _Working(session_id=session_id, state=state, transcript=_decode_transcript(raw))

    async def _record_decision(self, working: _Working, command: RecordDecision) -> None:
        """Append a ``session_decision`` row (§3 — insert only, never update).

        ``RecordDecision(operator)`` is emitted for every abort the operator
        path can raise, so the row records the state's own ``abort_reason``
        (``cost_ceiling`` for a §12 breach, ``operator_abort`` for a real
        operator) rather than the generic command reason.
        """
        reason: str = command.reason
        if command.reason == "operator" and working.state.abort_reason is not None:
            reason = working.state.abort_reason
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO session_decision (interview_session_id, decided_by, reason) "
                    "VALUES (:sid, NULL, :reason)"
                ),
                {"sid": working.session_id, "reason": reason},
            )
        _LOGGER.info(
            "session_decision_recorded",
            session_id=str(working.session_id),
            reason=reason,
        )

    # ---------- view assembly ----------

    async def _view(self, working: _Working) -> SessionView:
        state = working.state
        phase = _VIEW_PHASES.get(state.phase)
        if phase is None:
            raise DevSessionError(
                f"session {working.session_id} is still in {state.phase} — the shell always "
                "runs SessionStarted at creation, so this state is unreachable"
            )
        total = await self._ledger.session_total(working.session_id)
        return SessionView(
            session_id=working.session_id,
            phase=phase,
            abort_reason=state.abort_reason,
            awaiting=state.awaiting,
            competency_index=state.tech.competency_index if state.phase is Phase.TECH else None,
            coverage={
                node_id: cell.model_dump(mode="json")
                for node_id, cell in state.tech.coverage.items()
            },
            flagged_for_review=state.flagged_for_review,
            cost_usd_total=str(total),
            transcript=list(working.transcript),
        )


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    """The shell is the machine's only clock (contract §1)."""
    return datetime.now(UTC)


async def _ceiling_enforced() -> bool:
    """Whether the §12 ceiling is enforced right now (§9 dark launch)."""
    return await is_enabled("enforce_session_cost_ceiling")


def _decode_transcript(raw: object) -> list[TranscriptEntry]:
    """Parse the stored ``dev_transcript`` JSONB into typed entries."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise DevSessionError(f"dev_transcript must be a JSON array, got {type(raw).__name__}")
    entries: Iterable[Any] = raw
    return [TranscriptEntry.model_validate(entry) for entry in entries]


def validate_plan_shape(plan: Mapping[str, Any]) -> PlanSnapshot:
    """Validate a raw plan against contract §7 without touching the database.

    Exposed for callers (and tests) that want the ``PlanInvalid`` verdict
    before a session row exists.

    Args:
        plan: The raw plan payload.

    Returns:
        The typed :class:`PlanSnapshot`.

    Raises:
        app.backend.orchestrator.plan.PlanInvalid: The payload fails §7.
    """
    return PlanSnapshot.validate_plan(dict(plan))
