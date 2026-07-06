"""Interviewer agent wrapper (T18) — typed adapter around ``call_model``.

The wrapper executes, it does not decide (constitution §2): the
orchestrator selects ``next_planned_move`` deterministically and this
module's single job is to produce the next Ukrainian utterance for that
move via one bounded model call.

Responsibilities:

- Assemble the system prompt at runtime from the pinned
  ``prompts/interviewer/<PROMPT_VERSION>/`` version directory:
  ``system.md`` + ``level-guide.md`` + ``prompts/shared/ukrainian-anchors.md``
  (system.md §5–6 declare both appendices as runtime appends).
- Serialize the typed inputs (system.md §3) into the ``user_payload``.
- Call :func:`app.backend.llm.call_model` with the committed
  ``schema.json`` contract and the §12 default caps.
- Validate ``result.parsed`` into :class:`InterviewerOutput`.
- Per-agent retry policy (the wrapper layer never retries schema misses,
  per Clarifications 2026-04-26): retry ONCE on a schema-class failure
  (:class:`VertexSchemaError` or parsed-output validation failure); on
  the second failure raise :class:`InterviewerOutputInvalid` chaining
  the cause. Every other wrapper error propagates untouched.

Pure: no DB access, no side effects beyond what ``call_model`` performs
through its injected ``sink`` / ``ledger`` collaborators.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.backend.llm import ModelCallRequest, ModelCallResult, VertexSchemaError, call_model
from app.backend.llm.cost_ledger import CostLedger
from app.backend.llm.trace import TraceSink
from app.backend.settings import Settings

PROMPT_VERSION: Final[str] = "v0001"
"""Pinned prompt version. Bumps arrive with a new ``prompts/interviewer/<v>/``
directory (never an in-place edit) and must stay in lockstep with the
``interviewer.prompt_version`` entry in ``configs/models.yaml``."""

_PROMPTS_ROOT: Final[Path] = Path(__file__).resolve().parents[3] / "prompts"
"""Repo-root ``prompts/`` tree. ``parents[3]`` resolves both in the repository
checkout and in the Docker image (WORKDIR ``/app``, ``COPY prompts ./prompts``)."""

InterviewerMove = Literal[
    "ask_seed",
    "depth_probe",
    "acknowledge_and_transition",
    "redirect",
    "close_competency",
]
"""The five moves of the system.md §3/§4 contract — mirrors the
``internal_move_executed`` enum in ``prompts/interviewer/v0001/schema.json``."""


class InterviewerOutputInvalid(Exception):
    """Interviewer output failed schema/contract validation twice in a row.

    Raised after the single per-agent retry has been consumed. The
    ``__cause__`` chain carries the second failure
    (:class:`VertexSchemaError` or :class:`pydantic.ValidationError`).
    The orchestrator (T20) owns the escalation policy for this state.
    """


class RecentTurn(BaseModel):
    """One prior dialogue turn as the Interviewer prompt consumes it."""

    model_config = ConfigDict(frozen=True)

    role: Literal["interviewer", "candidate"]
    text: str = Field(min_length=1)


class InterviewerTurnInputs(BaseModel):
    """Typed inputs mirroring system.md §3. Frozen — one turn, one payload.

    ``interview_plan_snapshot``, ``current_competency``, and
    ``move_context`` stay permissive ``dict[str, Any]`` on purpose: their
    concrete shapes are owned by the Planner/orchestrator contracts
    (T20 / Tier 4) and will be tightened there, not here.
    """

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    """Cost-ledger attribution + trace correlation. NOT serialized into the
    user payload — system.md §3 does not list it as a model input."""

    interview_plan_snapshot: dict[str, Any]
    current_competency: dict[str, Any]
    recent_turns: tuple[RecentTurn, ...] = Field(max_length=8)
    """Last ≤ 8 turns, chronological (system.md §3)."""

    next_planned_move: InterviewerMove
    move_context: dict[str, Any]
    candidate_first_name: str | None = None


class InterviewerOutput(BaseModel):
    """Typed mirror of ``prompts/interviewer/v0001/schema.json``.

    ``extra="forbid"`` mirrors ``additionalProperties: false``; the field
    constraints mirror ``minLength``/``maxLength`` and the move enum, so a
    payload that passes here is exactly a payload that satisfies the
    committed contract.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    utterance: str = Field(min_length=1, max_length=1200)
    """Ukrainian text the candidate reads next. Plain prose, no markdown.
    The prompt caps this at ~80 Ukrainian words; 1200 chars is the hard
    backstop."""

    internal_move_executed: InterviewerMove
    """Must equal ``next_planned_move`` unless a contradictory input forced
    a redirect. The orchestrator uses this to detect drift."""


@lru_cache(maxsize=1)
def _load_system_prompt() -> str:
    """Assemble the runtime system prompt (cached — version files are immutable).

    Order per system.md: the prompt body first, then §5's level guide,
    then §6's shared Ukrainian style anchors.
    """
    version_dir = _PROMPTS_ROOT / "interviewer" / PROMPT_VERSION
    parts = (
        (version_dir / "system.md").read_text(encoding="utf-8"),
        (version_dir / "level-guide.md").read_text(encoding="utf-8"),
        (_PROMPTS_ROOT / "shared" / "ukrainian-anchors.md").read_text(encoding="utf-8"),
    )
    return "\n\n".join(part.strip() for part in parts) + "\n"


@lru_cache(maxsize=1)
def _load_output_schema() -> dict[str, Any]:
    """Load the committed output contract (cached — immutable per version)."""
    schema_path = _PROMPTS_ROOT / "interviewer" / PROMPT_VERSION / "schema.json"
    loaded: Any = json.loads(schema_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{schema_path}: expected a JSON object, got {type(loaded).__name__}")
    return loaded


def _serialize_user_payload(inputs: InterviewerTurnInputs) -> str:
    """Serialize the §3 inputs to a deterministic JSON string.

    ``session_id`` is excluded — it drives tracing/cost attribution, not
    the model. ``sort_keys`` keeps the payload byte-stable for the mock
    backend's SHA-keyed fixtures; ``ensure_ascii=False`` keeps Ukrainian
    text readable in traces.
    """
    payload = inputs.model_dump(mode="json", exclude={"session_id"})
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _validate_result(result: ModelCallResult) -> InterviewerOutput:
    """Parse ``result.parsed`` into the typed output.

    ``result.parsed is None`` (impossible while ``json_schema`` is set,
    defensive nonetheless) fails ``model_validate`` with the same
    :class:`pydantic.ValidationError` class as an enum/caps violation, so
    both take the identical retry-then-raise path.
    """
    return InterviewerOutput.model_validate(result.parsed)


async def run_interviewer_turn(
    inputs: InterviewerTurnInputs,
    *,
    sink: TraceSink,
    ledger: CostLedger,
    settings: Settings,
) -> InterviewerOutput:
    """Produce the next Interviewer utterance for the orchestrator-chosen move.

    Args:
        inputs: Typed system.md §3 inputs for this turn.
        sink: Trace sink injected through to ``call_model``.
        ledger: Per-session cost ledger injected through to ``call_model``.
        settings: Runtime settings (backend selection, budget ceiling).

    Returns:
        The schema-valid :class:`InterviewerOutput` for this turn.

    Raises:
        InterviewerOutputInvalid: Both the initial call and the single
            retry produced schema-invalid output.
        WrapperError: Any non-schema ``call_model`` failure
            (timeout, upstream, budget, config, trace-write) propagates
            untouched — no agent-side retry for those classes.
    """
    request = ModelCallRequest(
        agent="interviewer",
        system_prompt=_load_system_prompt(),
        user_payload=_serialize_user_payload(inputs),
        json_schema=_load_output_schema(),
        session_id=inputs.session_id,
        # §12 default caps (timeout_s=30, max_output_tokens=4096) apply;
        # this wrapper never raises them.
    )

    try:
        return _validate_result(
            await call_model(request, sink=sink, ledger=ledger, settings=settings)
        )
    except (VertexSchemaError, ValidationError):
        # Per-agent policy: exactly one fresh retry on a schema-class miss.
        pass

    try:
        return _validate_result(
            await call_model(request, sink=sink, ledger=ledger, settings=settings)
        )
    except (VertexSchemaError, ValidationError) as second_failure:
        raise InterviewerOutputInvalid(
            "interviewer output failed schema validation twice "
            f"(session {inputs.session_id}, move {inputs.next_planned_move!r})"
        ) from second_failure
