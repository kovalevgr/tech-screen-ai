"""Trace record types and the in-memory sink implementation.

A :class:`TraceRecord` is the append-only audit row produced for every
wrapper invocation that reaches a terminal state (constitution §1, §3 +
spec FR-008 / FR-009). The wrapper writes the record synchronously before
returning a result or raising any other typed error — per Clarifications
2026-04-26 a "lost trace" equals a call that escaped audit, which the
constitution forbids.

T04 ships the in-memory implementation only. T05 will add the durable
Postgres-backed implementation; both implement :class:`TraceSink`
structurally and require no caller-side change.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal, Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.backend.llm.errors import TraceWriteError

TraceOutcome = Literal[
    "ok",
    "schema_error",
    "timeout",
    "upstream_unavailable",
    "budget_exceeded",
    "config_error",
    "trace_write_error",
]
"""Frozen at T04. Adding a new outcome touches data-model.md, errors.py, the
wrapper's outcome-mapping switch, and (in T05+) the durable sink schema."""


class TraceRecord(BaseModel):
    """Append-only audit record for a single wrapper invocation.

    Frozen — the type system half of constitution §3. The database half
    (``REVOKE UPDATE, DELETE`` on the durable table) lands with T05.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID
    """Stable trace identifier; mirrored in :attr:`ModelCallResult.trace_id`."""

    created_at: datetime
    """Timezone-aware UTC timestamp set at trace emission."""

    agent: str = Field(min_length=1)
    """The agent name as supplied to the wrapper.

    Held as a free string (rather than a 3-agent ``Literal``) because the
    wrapper is contractually obliged to write exactly one trace per
    invocation in every outcome scenario (FR-008) — INCLUDING the
    ``config_error`` outcome triggered by an unknown agent name. A
    Literal would block the trace write with a nested
    ``pydantic.ValidationError`` on top of the original error, which
    would in turn surface as a different exception class to the caller.
    The agent registry (``configs/models.yaml``) is the source of truth
    for which agents are valid; the trace simply records what was
    actually requested.
    """
    session_id: UUID
    model: str = Field(min_length=1)
    model_version: str | None = None
    """``None`` for failures that occurred before any backend response."""

    prompt_sha256: str = Field(min_length=64, max_length=64)
    """Canonical-prompt SHA-256 (64 hex chars) — see research §13."""

    outcome: TraceOutcome
    attempts: int = Field(ge=1, le=3)
    latency_ms: int = Field(ge=0)
    input_tokens: int = Field(ge=0)
    """``0`` on ``outcome != "ok"``."""
    output_tokens: int = Field(ge=0)
    """``0`` on ``outcome != "ok"``."""
    cost_usd: Decimal
    """``Decimal("0")`` on ``outcome in {"config_error", "budget_exceeded"}``."""
    error_message: str | None = None
    """Short PII-free summary on failure; ``None`` on ``outcome == "ok"``."""


class TraceSink(Protocol):
    """Structural protocol for trace persistence backends."""

    async def write(self, record: TraceRecord) -> None:
        """Persist one trace record. Raises :class:`TraceWriteError` on failure."""
        ...


class InMemoryTraceSink:
    """In-process trace sink used in tests and local dev.

    Capacity bound exists to surface programmer error in test suites
    (a forgotten teardown that lets traces accumulate across runs); the
    durable T05 sink raises :class:`TraceWriteError` on real DB failures
    instead.
    """

    def __init__(self, *, capacity: int = 10_000) -> None:
        self._records: list[TraceRecord] = []
        self._capacity = capacity

    async def write(self, record: TraceRecord) -> None:
        if len(self._records) >= self._capacity:
            raise TraceWriteError(
                f"in-memory trace sink at capacity ({self._capacity}); "
                "tests must reset the sink between cases"
            )
        self._records.append(record)

    @property
    def records(self) -> list[TraceRecord]:
        """Defensive copy — caller cannot mutate the internal list."""
        return list(self._records)
