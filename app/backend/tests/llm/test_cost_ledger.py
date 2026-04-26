"""Tests for the in-memory per-session cost ledger (T042).

Maps to FR-012 (per-session cost ceiling).

Asserts:

- ``session_total`` returns ``Decimal("0")`` for an unknown session.
- ``add`` then ``session_total`` round-trips exactly (no float drift).
- 100 concurrent ``add(s, 0.001)`` calls within one event loop sum to
  exactly ``Decimal("0.100")`` — the asyncio.Lock serialises the
  read-modify-write cycle so no increments are lost.
- A negative ``cost_usd`` raises ``ValueError`` (cost is monotonic
  non-decreasing per ``contracts/wrapper-contract.md`` §8).
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest

from app.backend.llm.cost_ledger import InMemoryCostLedger


async def test_unknown_session_returns_zero() -> None:
    """First call for a session id sees ``Decimal("0")`` — never raises."""
    ledger = InMemoryCostLedger()
    assert await ledger.session_total(uuid4()) == Decimal("0")


async def test_add_then_total_round_trips_exactly() -> None:
    """``add(0.001)`` → ``session_total`` returns ``Decimal("0.001")``."""
    ledger = InMemoryCostLedger()
    session_id = uuid4()
    await ledger.add(session_id, Decimal("0.001"))
    assert await ledger.session_total(session_id) == Decimal("0.001")


async def test_concurrent_adds_are_atomic() -> None:
    """100 × ``Decimal("0.001")`` adds → exactly ``Decimal("0.100")``.

    Inside one event loop the asyncio.Lock around the read-modify-write
    cycle prevents lost updates. Multi-process correctness is a T05
    concern (Postgres atomic UPDATE).
    """
    ledger = InMemoryCostLedger()
    session_id = uuid4()
    increments = [Decimal("0.001")] * 100
    await asyncio.gather(*(ledger.add(session_id, x) for x in increments))
    assert await ledger.session_total(session_id) == Decimal("0.100")


async def test_negative_cost_raises_value_error() -> None:
    """The ledger is monotonic — any negative ``add`` is a programmer error."""
    ledger = InMemoryCostLedger()
    with pytest.raises(ValueError):
        await ledger.add(uuid4(), Decimal("-1"))


async def test_zero_cost_add_is_accepted() -> None:
    """The wrapper passes ``Decimal("0")`` for failed-call traces.

    Per ``contracts/wrapper-contract.md`` §8: "the wrapper passes
    ``Decimal('0')`` for failed-call traces (so failures don't burn
    budget)." A zero-amount add must therefore be accepted (it's a
    no-op semantically but a contract-required call shape).
    """
    ledger = InMemoryCostLedger()
    session_id = uuid4()
    await ledger.add(session_id, Decimal("0"))
    assert await ledger.session_total(session_id) == Decimal("0")
