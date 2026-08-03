"""``PostgresCostLedger`` and the §12 ceiling matrix (T21).

DB-gated. The ledger has no store of its own — the total is
``SUM(turn_trace.cost_usd)`` — so every test here seeds real trace rows through
the real sink.

The matrix these tests lock in (spec SC-2):

======================  ==================  ==============================
running total           enforcement flag    guard behaviour
======================  ==================  ==============================
below the ceiling       either              returns, silent
at/over the ceiling     off (the default)   returns, structured warning
at/over the ceiling     on                  raises SessionBudgetExceeded
======================  ==================  ==============================
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from structlog.typing import EventDict

from app.backend.llm.errors import SessionBudgetExceeded
from app.backend.llm.persistent_cost import (
    SESSION_COST_METRIC,
    EnforcementPredicate,
    PostgresCostLedger,
)
from app.backend.llm.persistent_trace import PostgresTraceSink
from app.backend.llm.trace import TraceRecord

pytestmark = pytest.mark.asyncio

_CEILING = Decimal("5.00")


async def _new_session(engine: AsyncEngine) -> uuid.UUID:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("INSERT INTO interview_session DEFAULT VALUES RETURNING id")
        )
        created: uuid.UUID = result.scalar_one()
    return created


async def _charge(engine: AsyncEngine, session_id: uuid.UUID, amount: str) -> None:
    """Write one real trace row carrying ``amount`` USD."""
    await PostgresTraceSink(engine).write(
        TraceRecord(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            agent="assessor",
            session_id=session_id,
            model="gemini-2.5-flash",
            prompt_sha256="d" * 64,
            outcome="ok",
            attempts=1,
            latency_ms=10,
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal(amount),
        )
    )


def _enforcement(value: bool) -> EnforcementPredicate:
    """An enforcement predicate pinned to ``value`` (the flag, stubbed)."""

    async def _predicate() -> bool:
        return value

    return _predicate


# ---------------------------------------------------------------------------
# The ledger itself
# ---------------------------------------------------------------------------


async def test_session_total_derives_from_the_trace_rows(db_engine: AsyncEngine) -> None:
    session_id = await _new_session(db_engine)
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING)
    await _charge(db_engine, session_id, "0.400000")
    await _charge(db_engine, session_id, "1.100000")

    assert await ledger.session_total(session_id) == Decimal("1.500000")


async def test_session_total_for_an_unknown_session_is_zero(db_engine: AsyncEngine) -> None:
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING)

    assert await ledger.session_total(uuid.uuid4()) == Decimal("0")


async def test_add_does_not_double_count_the_trace_row(db_engine: AsyncEngine) -> None:
    """``add`` is a protocol no-op — the trace row already IS the entry."""
    session_id = await _new_session(db_engine)
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING)
    await _charge(db_engine, session_id, "0.250000")

    await ledger.add(session_id, Decimal("0.250000"))

    assert await ledger.session_total(session_id) == Decimal("0.250000")


async def test_add_rejects_a_negative_charge(db_engine: AsyncEngine) -> None:
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING)

    with pytest.raises(ValueError, match="non-negative"):
        await ledger.add(uuid.uuid4(), Decimal("-0.01"))


async def test_the_default_ceiling_comes_from_the_committed_config(
    db_engine: AsyncEngine,
) -> None:
    assert PostgresCostLedger(db_engine).ceiling_usd == Decimal("5.00")


# ---------------------------------------------------------------------------
# The ceiling matrix (SC-2)
# ---------------------------------------------------------------------------


async def test_a_total_below_the_ceiling_passes_the_guard_silently(
    db_engine: AsyncEngine, captured_logs: list[EventDict]
) -> None:
    session_id = await _new_session(db_engine)
    await _charge(db_engine, session_id, "4.990000")
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING, enforcement=_enforcement(True))

    total = await ledger.guard_session_budget(session_id)

    assert total == Decimal("4.990000")
    assert [event for event in captured_logs if "cost_ceiling" in str(event.get("message"))] == []


async def test_a_breach_with_the_flag_off_warns_and_continues(
    db_engine: AsyncEngine, captured_logs: list[EventDict]
) -> None:
    """§9 dark launch: enforcement is off by default, so the session survives."""
    session_id = await _new_session(db_engine)
    await _charge(db_engine, session_id, "5.500000")
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING, enforcement=_enforcement(False))

    total = await ledger.guard_session_budget(session_id)

    assert total == Decimal("5.500000")
    warning = next(
        event for event in captured_logs if event["message"] == "session_cost_ceiling_reached"
    )
    assert warning["enforced"] is False
    assert warning[SESSION_COST_METRIC] == "5.500000"


async def test_a_breach_with_the_flag_on_raises_session_budget_exceeded(
    db_engine: AsyncEngine, captured_logs: list[EventDict]
) -> None:
    session_id = await _new_session(db_engine)
    await _charge(db_engine, session_id, "5.500000")
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING, enforcement=_enforcement(True))

    with pytest.raises(SessionBudgetExceeded, match="ceiling"):
        await ledger.guard_session_budget(session_id)

    warning = next(
        event for event in captured_logs if event["message"] == "session_cost_ceiling_enforced"
    )
    assert warning["enforced"] is True
    assert warning["metric"] == SESSION_COST_METRIC


async def test_the_ceiling_boundary_counts_as_reached(db_engine: AsyncEngine) -> None:
    """ "Reached", not "exceeded" — the same inclusive reading as the budgets."""
    session_id = await _new_session(db_engine)
    await _charge(db_engine, session_id, "5.000000")
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING, enforcement=_enforcement(True))

    with pytest.raises(SessionBudgetExceeded):
        await ledger.guard_session_budget(session_id)


async def test_a_ledger_without_an_enforcement_predicate_never_raises(
    db_engine: AsyncEngine,
) -> None:
    """The §9-safe default for any caller that has not wired the flag."""
    session_id = await _new_session(db_engine)
    await _charge(db_engine, session_id, "9.000000")
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING)

    assert await ledger.guard_session_budget(session_id) == Decimal("9.000000")


async def test_the_guard_isolates_sessions_from_each_other(db_engine: AsyncEngine) -> None:
    spender = await _new_session(db_engine)
    newcomer = await _new_session(db_engine)
    await _charge(db_engine, spender, "6.000000")
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING, enforcement=_enforcement(True))

    assert await ledger.guard_session_budget(newcomer) == Decimal("0")
    with pytest.raises(SessionBudgetExceeded):
        await ledger.guard_session_budget(spender)


async def test_the_enforcement_predicate_is_only_consulted_on_a_breach(
    db_engine: AsyncEngine,
) -> None:
    """A per-call flag read on every model call would be pure overhead."""
    calls = 0

    async def _counting() -> bool:
        nonlocal calls
        calls += 1
        return False

    session_id = await _new_session(db_engine)
    ledger = PostgresCostLedger(db_engine, ceiling_usd=_CEILING, enforcement=_counting)

    await ledger.guard_session_budget(session_id)
    assert calls == 0

    await _charge(db_engine, session_id, "5.000000")
    await ledger.guard_session_budget(session_id)
    assert calls == 1
