"""Durable Postgres trace sink — the T21 half of constitution §1/§3.

T04 shipped :class:`~app.backend.llm.trace.InMemoryTraceSink` and left a note
that "T05 will add the durable Postgres-backed implementation". This is that
implementation, arriving with T21 (T05 shipped the table + the §3 guard only).
It is a NEW module implementing the existing :class:`~app.backend.llm.trace.TraceSink`
protocol structurally — nothing inside :mod:`app.backend.llm.vertex` or
:mod:`app.backend.llm.trace` changes, and every existing caller keeps working
by swapping the injected sink.

Row shape: ``docs/contracts/turn-trace.schema.json`` (committed contract).

**Timing.** :meth:`PostgresTraceSink.write` performs a real, committed INSERT
before it returns, i.e. before ``call_model`` returns or raises — T04's
semantics unchanged: a call that escaped audit is a call that must fail
(§1). Any failure becomes :class:`~app.backend.llm.errors.TraceWriteError`.

**Transaction.** The INSERT runs on its own connection and commits
immediately, independent of whatever request transaction the caller is inside.
An audit row must survive a rolled-back request: the model call really did
happen and really did cost money.

**Two sources, no overlap.** The row is assembled from exactly two places and
each owns its columns outright:

- the :class:`~app.backend.llm.trace.TraceRecord` — everything only
  ``call_model`` can know, including (since the T21 seam extension) the raw
  ``response_text`` and the ``parsed`` object;
- a :class:`TurnTraceContext` bound by the caller for the duration of one agent
  call (:meth:`PostgresTraceSink.bind`) — everything only the CALLER can know:
  the orchestrator context (``turn_id``, ``transition``), the pinned
  ``prompt_version``, the assembled prompt and payload, and the wrapper verdict.

Nothing is writable from both sides, so there is no precedence rule to
remember and no way to record a reconstruction as if it were the raw bytes.
With no context bound (calibration runs, smoke scripts) the row is written from
the record alone — exactly the "non-session call" the contract describes.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backend.llm.errors import TraceWriteError
from app.backend.llm.trace import TraceRecord

WrapperOutcome = Literal["accepted", "contract_miss_retried", "rejected"]
"""Whether the AGENT WRAPPER accepted the model output, as distinct from
whether the model call itself succeeded (``TraceRecord.outcome``). The contract
calls this out because "trace says ok but the wrapper rejected the payload" was
an unrecorded seam through specs 031/032."""


class TransitionContext(BaseModel):
    """Orchestrator context for a call the state machine issued.

    ``state-machine.md`` §1: "Every transition is auditable:
    ``(state_before_hash, event, state_after_hash, commands)`` — T21 records
    these alongside turn_trace."
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: str = Field(min_length=1)
    issued_move: str | None = None
    state_before_sha: str = Field(min_length=64, max_length=64)
    state_after_sha: str = Field(min_length=64, max_length=64)


class TurnTraceContext(BaseModel):
    """The caller's half of the row — what ``TraceRecord`` cannot know.

    Bound to the sink for the duration of one agent call. Every field is
    optional-with-a-default so a caller can supply exactly as much as it
    actually knows; the sink never invents a value. The model's own answer
    (``response_text``, ``parsed``) is deliberately NOT here — it arrives on
    the record, straight from ``call_model``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    prompt_version: str = ""
    """The ``prompts/<agent>/<version>`` in force at call time — the pin from
    ``configs/models.yaml`` (never ``active.txt`` at runtime)."""

    turn_id: UUID | None = None
    """The orchestrator turn (uuid5, state-machine contract §6.9). ``None`` for
    non-session calls."""

    system_prompt: str = ""
    user_payload: str = ""

    wrapper_outcome: WrapperOutcome | None = None
    """The agent wrapper's verdict, when the caller can know it at write time.

    ``None`` is a legitimate, expected value, not a gap: the sink writes inside
    ``call_model``, before the wrapper has judged the output, and §3 forbids
    back-filling the row afterwards. The definitive verdict is derivable
    downstream from the session's coverage markers and its ``session_decision``
    stream (row contract, ``wrapper_outcome``)."""

    transition: TransitionContext | None = None


_EMPTY_CONTEXT: TurnTraceContext = TurnTraceContext()

_INSERT_SQL = text(
    """
    INSERT INTO turn_trace (
        id, created_at, interview_session_id, turn_id, transition,
        agent, prompt_version, model, model_version, outcome, wrapper_outcome,
        attempts, latency_ms, input_tokens, output_tokens, cost_usd, prompt_sha,
        error_message, system_prompt, user_payload, response_text, parsed
    ) VALUES (
        :id, :created_at, :interview_session_id, :turn_id, CAST(:transition AS JSONB),
        :agent, :prompt_version, :model, :model_version, :outcome, :wrapper_outcome,
        :attempts, :latency_ms, :input_tokens, :output_tokens, :cost_usd, :prompt_sha,
        :error_message, :system_prompt, :user_payload, :response_text,
        CAST(:parsed AS JSONB)
    )
    """
)


class PostgresTraceSink:
    """Durable :class:`~app.backend.llm.trace.TraceSink` backed by ``turn_trace``.

    One instance per session is the intended usage: the shell constructs it
    once and rebinds a fresh :class:`TurnTraceContext` around each agent call.
    Instances are cheap — they hold an engine reference and the current
    context, nothing else.
    """

    def __init__(self, engine: AsyncEngine, *, context: TurnTraceContext | None = None) -> None:
        """Create a sink bound to ``engine``.

        Args:
            engine: The async engine used for the audit INSERT. Each write
                takes its own connection and commits on its own.
            context: Optional initial context (mostly for one-shot callers
                that never rebind).
        """
        self._engine = engine
        self._context = context if context is not None else _EMPTY_CONTEXT
        self._written: list[UUID] = []

    @property
    def context(self) -> TurnTraceContext:
        """The context currently in force."""
        return self._context

    @property
    def written_trace_ids(self) -> tuple[UUID, ...]:
        """Ids of every row this sink has written, oldest first.

        Lets the caller correlate a finished agent call with the rows it
        produced (``ModelCallResult.trace_id`` is the same id).
        """
        return tuple(self._written)

    @contextmanager
    def bind(self, context: TurnTraceContext) -> Iterator[None]:
        """Bind ``context`` for the duration of the block, then restore.

        Args:
            context: The per-call context whose fields complete the row.

        Yields:
            ``None`` — the sink is bound for the body of the ``with``.
        """
        previous = self._context
        self._context = context
        try:
            yield
        finally:
            self._context = previous

    async def write(self, record: TraceRecord) -> None:
        """Persist one trace row synchronously.

        Args:
            record: The T04 trace record built by ``call_model``.

        Raises:
            TraceWriteError: The INSERT failed for any reason. Per T04's
                Clarifications the wrapper turns this into a failed call —
                auditability (§1) outranks a successful model response.
        """
        params = self._row(record)
        try:
            async with self._engine.begin() as conn:
                await conn.execute(_INSERT_SQL, params)
        except TraceWriteError:  # pragma: no cover — defensive, never raised here
            raise
        except Exception as exc:
            raise TraceWriteError(
                f"turn_trace insert failed for trace {record.id}: {type(exc).__name__}: {exc}"
            ) from exc
        self._written.append(record.id)

    def _row(self, record: TraceRecord) -> dict[str, Any]:
        """Project ``record`` + the bound context onto the contract row."""
        context = self._context
        transition = context.transition
        return {
            "id": record.id,
            "created_at": record.created_at,
            "interview_session_id": record.session_id,
            "turn_id": context.turn_id,
            "transition": (
                None if transition is None else json.dumps(transition.model_dump(mode="json"))
            ),
            "agent": record.agent,
            "prompt_version": context.prompt_version,
            "model": record.model,
            "model_version": record.model_version,
            "outcome": record.outcome,
            "wrapper_outcome": context.wrapper_outcome,
            "attempts": record.attempts,
            "latency_ms": record.latency_ms,
            "input_tokens": record.input_tokens,
            "output_tokens": record.output_tokens,
            "cost_usd": record.cost_usd,
            "prompt_sha": record.prompt_sha256,
            "error_message": record.error_message,
            "system_prompt": context.system_prompt,
            "user_payload": context.user_payload,
            # The model's answer comes from the record — `call_model` is the
            # only thing that ever holds the raw bytes. The column is NOT NULL
            # (transitional default), so a call that never reached the model
            # stores the empty string rather than a null.
            "response_text": record.response_text or "",
            "parsed": None if record.parsed is None else json.dumps(record.parsed),
        }


async def session_cost_total(engine: AsyncEngine, session_id: UUID) -> Decimal:
    """Sum ``turn_trace.cost_usd`` for one session.

    The single source of truth for a session's spend (spec Clarification 1 —
    no second table, no drift). Shared by
    :class:`app.backend.llm.persistent_cost.PostgresCostLedger` and by the
    dev-session view assembly.

    Args:
        engine: Async engine to read through.
        session_id: The session whose spend is wanted.

    Returns:
        The total in USD; ``Decimal("0")`` for a session with no calls yet.
    """
    async with engine.connect() as conn:
        result = await conn.execute(
            text(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM turn_trace "
                "WHERE interview_session_id = :sid"
            ),
            {"sid": session_id},
        )
        total = result.scalar_one()
    return Decimal(total)
