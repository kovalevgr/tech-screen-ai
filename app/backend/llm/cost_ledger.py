"""Per-session cost ledger types and the in-memory implementation.

The ledger underpins the per-session $5 USD cost ceiling (constitution §12,
spec FR-012). The wrapper consults :meth:`CostLedger.session_total` before
every backend call and short-circuits with
:class:`~app.backend.llm.errors.SessionBudgetExceeded` when the running
total has already reached the ceiling.

T04 ships only the in-memory implementation; the durable, multi-process
implementation backed by Postgres atomic increments lands with T05.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Protocol
from uuid import UUID


class CostLedger(Protocol):
    """Structural protocol for per-session cost aggregation."""

    async def session_total(self, session_id: UUID) -> Decimal:
        """Return the running USD total for the given session.

        For an unknown session id the implementation MUST return
        ``Decimal("0")`` — first call for a session sees zero.
        """
        ...

    async def add(self, session_id: UUID, cost_usd: Decimal) -> None:
        """Increment the running total. ``cost_usd`` MUST be non-negative."""
        ...


class InMemoryCostLedger:
    """In-process cost ledger used in tests and local dev.

    Concurrent ``add`` calls within one event loop are serialised via
    :class:`asyncio.Lock`. Multi-process correctness is a T05 concern
    (durable ledger uses Postgres atomic ``UPDATE ... SET total = total + $cost``).
    """

    def __init__(self) -> None:
        self._totals: dict[UUID, Decimal] = {}
        self._lock = asyncio.Lock()

    async def session_total(self, session_id: UUID) -> Decimal:
        return self._totals.get(session_id, Decimal("0"))

    async def add(self, session_id: UUID, cost_usd: Decimal) -> None:
        if cost_usd < 0:
            raise ValueError(f"cost_usd must be non-negative (got {cost_usd})")
        async with self._lock:
            self._totals[session_id] = self._totals.get(session_id, Decimal("0")) + cost_usd
