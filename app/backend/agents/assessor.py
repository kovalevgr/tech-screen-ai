"""Assessor agent wrapper — scores one candidate turn against the rubric snapshot.

Thin, typed adapter between the orchestrator (T20) and the sanctioned LLM
doorway :func:`app.backend.llm.call_model`. Responsibilities:

- Assemble the versioned system prompt from ``prompts/assessor/<version>/``.
  ``system.md`` §5 delegates the level semantics to ``level-guide.md``, so
  both files are concatenated at runtime; ``schema.json`` is the
  machine-readable output contract and travels as ``json_schema`` (it is
  never inlined into prompt text).
- Serialise the typed turn inputs into a JSON ``user_payload`` shaped
  exactly like ``system.md`` §3 INPUTS.
- Apply the Assessor's per-agent schema-retry policy (T04 Clarifications
  2026-04-26 + ``docs/engineering/vertex-integration.md``): exactly one
  fresh retry when the model output misses the contract — either a
  wrapper-side :class:`~app.backend.llm.VertexSchemaError` or a payload
  that passes the wrapper's structural check but violates the tighter
  bounds encoded on :class:`AssessorOutput` (level enum, confidence
  ceiling, span non-emptiness). A second miss raises
  :class:`AssessorOutputInvalid` chaining the cause. Every other wrapper
  error propagates untouched.

Invariants honoured:

- Constitution §2 — the Assessor SCORES; it never routes. Nothing here
  branches on model output; the orchestrator consumes the typed result.
- Constitution §12 — wrapper default caps (30 s timeout, 4096 output
  tokens) are left untouched; this module never raises them.
- ADR-007 (voice-readiness) — :func:`run_assessor_turn` is a plain
  awaitable coroutine with no blocking I/O on the event loop: prompt files
  are read once (first call) and cached at module level, because prompt
  files are immutable per version.
- Constitution §15 — :class:`AssessorOutputInvalid` messages carry no
  candidate text; payload detail lives only on the chained cause.

Pure: no DB access, no side effects beyond what ``call_model`` performs
through its injected ``sink`` / ``ledger`` collaborators. No provider SDK
imports — everything model-shaped comes from :mod:`app.backend.llm`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Final, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.backend.llm import ModelCallRequest, VertexSchemaError, call_model
from app.backend.llm.cost_ledger import CostLedger
from app.backend.llm.trace import TraceSink
from app.backend.settings import Settings

PROMPT_VERSION: Final[str] = "v0001"
"""Pinned prompt version — bumped only together with a new prompts/ tree."""

_AGENT_NAME: Final[str] = "assessor"

# Repo root is three levels above this file (app/backend/agents/); in the
# Docker image WORKDIR is /app and prompts/ is copied to /app/prompts, so
# the same expression resolves correctly in both environments.
_PROMPTS_ROOT: Final[Path] = Path(__file__).resolve().parents[3] / "prompts"
_PROMPT_DIR: Final[Path] = _PROMPTS_ROOT / _AGENT_NAME / PROMPT_VERSION


class AssessorOutputInvalid(Exception):
    """Assessor output missed the v0001 contract twice (initial call + one retry).

    The chained ``__cause__`` is the second miss — a
    :class:`~app.backend.llm.VertexSchemaError` (wrapper-side structural
    miss) or a :class:`pydantic.ValidationError` (bounds violation caught
    by :class:`AssessorOutput`). The message itself is PII-free
    (constitution §15): no candidate text, no raw payload.
    """


# ---------------------------------------------------------------------------
# Prompt assembly — module-level cache, files are immutable per version
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def load_system_prompt() -> str:
    """Assemble the runtime system prompt for ``prompts/assessor/v0001``.

    ``system.md`` §5 ("LEVEL PROMPTING GUIDE") defers to ``level-guide.md``,
    so the guide is appended after the main prompt. ``notes.md`` is a
    design-history document and is NOT part of the runtime prompt;
    ``schema.json`` travels separately as the ``json_schema`` argument.

    Returns:
        The concatenated prompt text (cached for the process lifetime —
        prompt files are immutable per version, see ADR-021 / §16).
    """
    system = (_PROMPT_DIR / "system.md").read_text(encoding="utf-8")
    level_guide = (_PROMPT_DIR / "level-guide.md").read_text(encoding="utf-8")
    return f"{system}\n\n{level_guide}"


@lru_cache(maxsize=1)
def _output_schema_text() -> str:
    """Raw ``schema.json`` text (cached — the file is immutable per version)."""
    return (_PROMPT_DIR / "schema.json").read_text(encoding="utf-8")


def load_output_schema() -> dict[str, Any]:
    """Return the committed Assessor output contract as a fresh dict.

    A fresh dict per call keeps the module-level cache immune to caller
    mutation; only the file read is cached (no I/O after first call).

    Returns:
        The parsed ``prompts/assessor/v0001/schema.json`` contract.
    """
    schema: dict[str, Any] = json.loads(_output_schema_text())
    return schema


# ---------------------------------------------------------------------------
# Input model — mirrors prompts/assessor/v0001/system.md §3 INPUTS
# ---------------------------------------------------------------------------


class AssessorTurnInput(BaseModel):
    """Typed input for one Assessor call, mirroring ``system.md`` §3 INPUTS.

    The ids from the §3 ``turn_metadata`` block are promoted to typed
    fields (``turn_id`` / ``session_id``); :meth:`to_user_payload` nests
    them back so the serialized payload matches the prompt contract
    key-for-key.
    """

    model_config = ConfigDict(frozen=True)

    session_id: UUID
    """Session the turn belongs to — echoed by the model for traceability."""

    turn_id: UUID
    """The candidate turn being assessed — echoed by the model."""

    competency_focus: str = Field(min_length=1)
    """Rubric node id the orchestrator wants this call to focus on."""

    rubric_snapshot_subset: list[dict[str, Any]]
    """Rubric nodes relevant to the turn (id, label, L1–L4 descriptors,
    definition). Permissive ``dict`` payloads — the typed rubric-node model
    does not exist in code yet; T20 / Tier-4 refines this."""

    turn: dict[str, Any]
    """The candidate's answer being assessed plus the preceding interviewer
    question. Permissive until the turn model lands (T20 / Tier-4)."""

    prior_turns: list[dict[str, Any]] = Field(default_factory=list)
    """The last four exchanges in this competency, for context. Permissive
    until the turn model lands (T20 / Tier-4)."""

    turn_metadata: dict[str, Any] = Field(default_factory=dict)
    """Timestamps and other per-turn metadata from ``system.md`` §3
    ``turn_metadata``; the ids from that block live in the typed
    ``turn_id`` / ``session_id`` fields above."""

    def to_user_payload(self) -> str:
        """Serialise to the JSON ``user_payload`` shape of ``system.md`` §3.

        Returns:
            A JSON object string with exactly the five §3 input keys;
            ``turn_metadata`` re-nests the typed ids. ``ensure_ascii=False``
            keeps Ukrainian candidate text readable (and token-cheap).
        """
        payload: dict[str, Any] = {
            "rubric_snapshot_subset": self.rubric_snapshot_subset,
            "turn": self.turn,
            "prior_turns": self.prior_turns,
            "competency_focus": self.competency_focus,
            "turn_metadata": {
                "turn_id": str(self.turn_id),
                "session_id": str(self.session_id),
                **self.turn_metadata,
            },
        }
        return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Output models — mirror prompts/assessor/v0001/schema.json exactly
# ---------------------------------------------------------------------------

RedFlagType = Literal[
    "FACTUALLY_WRONG",
    "CONTRADICTION",
    "FABRICATED_TECHNOLOGY",
    "LIKELY_CHEATING",
    "RED_FLAG_OTHER",
]
"""The five-value red-flag enum from ``schema.json`` ``red_flags[].type``."""


class AssessmentItem(BaseModel):
    """One per-rubric-node assessment (``schema.json`` ``assessments[]``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rubric_node_id: str
    level: Literal[1, 2, 3, 4]
    confidence: float = Field(ge=0, le=0.99)
    rationale_en: str = Field(min_length=1, max_length=600)
    evidence_spans: list[Annotated[str, Field(min_length=1)]] = Field(min_length=1)


class RedFlagItem(BaseModel):
    """One red flag (``schema.json`` ``red_flags[]``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: RedFlagType
    rubric_node_id: str | None = None
    description_en: str = Field(min_length=1, max_length=400)
    evidence_span: str | None = None


class AssessorOutput(BaseModel):
    """The Assessor's full per-turn output (``schema.json`` root object).

    Stricter than the wrapper's structural JSON-schema pass: the wrapper
    validates types / required keys / ``additionalProperties``, while this
    model also enforces the numeric enum on ``level``, the 0.99 confidence
    ceiling, string length bounds, and non-empty ``evidence_spans``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn_id: UUID
    session_id: UUID
    competency_focus: str
    assessments: list[AssessmentItem]
    red_flags: list[RedFlagItem]
    needs_manual_review: bool
    manual_review_reason_en: str | None = Field(default=None, max_length=400)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_assessor_turn(
    inputs: AssessorTurnInput,
    *,
    sink: TraceSink,
    ledger: CostLedger,
    settings: Settings,
) -> AssessorOutput:
    """Score one candidate turn via the Assessor agent.

    Plain awaitable coroutine — no blocking I/O on the event loop
    (ADR-007 voice-readiness): the Interviewer may produce turn N+1 while
    this call is still scoring turn N.

    Args:
        inputs: Typed turn inputs mirroring ``system.md`` §3.
        sink: Trace sink injected through to :func:`call_model`.
        ledger: Per-session cost ledger injected through to :func:`call_model`.
        settings: Runtime settings injected through to :func:`call_model`.

    Returns:
        The validated :class:`AssessorOutput` for the turn.

    Raises:
        AssessorOutputInvalid: The model output missed the v0001 contract
            twice (initial call + the single per-agent retry).
        app.backend.llm.WrapperError: Any non-schema wrapper failure
            (timeout, upstream unavailable, budget, config, trace write)
            propagates untouched — no retry at this layer.
    """
    request = ModelCallRequest(
        agent=_AGENT_NAME,
        system_prompt=load_system_prompt(),
        user_payload=inputs.to_user_payload(),
        json_schema=load_output_schema(),
        session_id=inputs.session_id,
        # timeout_s / max_output_tokens deliberately left at the wrapper
        # defaults — constitution §12 caps are never raised here.
    )
    try:
        return await _score_once(request, sink=sink, ledger=ledger, settings=settings)
    except (VertexSchemaError, ValidationError) as first_miss:
        # Per-agent policy: exactly ONE fresh retry on a schema miss.
        try:
            return await _score_once(request, sink=sink, ledger=ledger, settings=settings)
        except (VertexSchemaError, ValidationError) as second_miss:
            raise AssessorOutputInvalid(
                "assessor output failed the v0001 contract twice "
                f"(first miss: {type(first_miss).__name__}, "
                f"second miss: {type(second_miss).__name__}); "
                "payload detail is on the chained cause"
            ) from second_miss


async def _score_once(
    request: ModelCallRequest,
    *,
    sink: TraceSink,
    ledger: CostLedger,
    settings: Settings,
) -> AssessorOutput:
    """One ``call_model`` invocation + strict validation into the typed output."""
    result = await call_model(request, sink=sink, ledger=ledger, settings=settings)
    return AssessorOutput.model_validate(result.parsed)
