"""Tests for the in-memory trace sink (T035).

Maps to FR-009 (trace persistence semantics).

Asserts:

- The sink accepts records up to its capacity bound.
- The capacity bound raises :class:`TraceWriteError` (not a generic
  exception) so the wrapper translates it correctly.
- ``records`` returns a defensive copy — mutating the returned list
  does not affect future writes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from app.backend.llm.errors import TraceWriteError
from app.backend.llm.trace import InMemoryTraceSink, TraceOutcome, TraceRecord


def _record(outcome: TraceOutcome = "ok") -> TraceRecord:
    return TraceRecord(
        id=uuid4(),
        created_at=datetime.now(UTC),
        agent="interviewer",
        session_id=uuid4(),
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
        prompt_sha256="0" * 64,
        outcome=outcome,
        attempts=1,
        latency_ms=10,
        input_tokens=1,
        output_tokens=1,
        cost_usd=Decimal("0.000001"),
        error_message=None if outcome == "ok" else "boom",
    )


async def test_sink_accepts_records_below_capacity() -> None:
    """N records → all recorded under capacity ≥ N."""
    sink = InMemoryTraceSink(capacity=5)
    records = [_record() for _ in range(5)]
    for r in records:
        await sink.write(r)
    assert len(sink.records) == 5


async def test_sink_capacity_overflow_raises_trace_write_error() -> None:
    """The (capacity + 1)th write raises ``TraceWriteError`` exactly."""
    sink = InMemoryTraceSink(capacity=2)
    await sink.write(_record())
    await sink.write(_record())
    with pytest.raises(TraceWriteError) as excinfo:
        await sink.write(_record())
    assert "capacity" in str(excinfo.value).lower()


async def test_sink_records_property_returns_defensive_copy() -> None:
    """Caller cannot mutate the sink by mutating the returned list."""
    sink = InMemoryTraceSink(capacity=10)
    await sink.write(_record())
    snapshot_a = sink.records
    snapshot_a.clear()
    snapshot_a.append(_record(outcome="schema_error"))
    snapshot_b = sink.records
    # Internal list still has exactly one record, the original.
    assert len(snapshot_b) == 1
    assert snapshot_b[0].outcome == "ok"
