"""Durable per-session cost ledger + the §12 ceiling guard (T21).

T04 shipped :class:`~app.backend.llm.cost_ledger.InMemoryCostLedger` and left
the durable, multi-process implementation to a later task. This is it — a NEW
module implementing the existing :class:`~app.backend.llm.cost_ledger.CostLedger`
protocol structurally; nothing inside the existing ``llm`` modules changes.

**One source of truth.** The running total is ``SUM(turn_trace.cost_usd)`` for
the session (spec Clarification 1). There is no second table and therefore no
drift: the trace row the wrapper writes before returning IS the ledger entry.
:meth:`PostgresCostLedger.add` is consequently a no-op — see its docstring.

**The ceiling is dark-launched.** :meth:`PostgresCostLedger.guard_session_budget`
is the pre-call guard the shell runs before every agent call. It raises
:class:`~app.backend.llm.errors.SessionBudgetExceeded` only when the injected
:data:`EnforcementPredicate` answers ``True``; otherwise it emits a structured
warning and lets the session continue. The predicate is injected rather than
read here so this module stays inside its layer (``llm`` never imports
``services``): the shell supplies the ``enforce_session_cost_ceiling`` feature
flag, and the default — no predicate — is the §9-safe "warn, never enforce".
The ceiling value comes from ``configs/llm-limits.yaml`` (§16), never a literal.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Final
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backend.llm.errors import SessionBudgetExceeded
from app.backend.llm.limits_config import load_llm_limits
from app.backend.llm.persistent_trace import session_cost_total

_LOGGER = structlog.get_logger("app.backend.llm.persistent_cost")

SESSION_COST_METRIC: Final[str] = "techscreen_session_cost_usd"
"""Observed-metric name for the per-session spend (constitution §12).

Emitted as a structured log field on every ceiling check so T38's dashboards
have a stable key to scrape long before a metrics client exists."""

type EnforcementPredicate = Callable[[], Awaitable[bool]]
"""Answers "is the §12 ceiling being ENFORCED right now?". The shell binds this
to the ``enforce_session_cost_ceiling`` feature flag."""


class PostgresCostLedger:
    """Per-session USD ledger derived from the append-only ``turn_trace`` table."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        ceiling_usd: Decimal | None = None,
        enforcement: EnforcementPredicate | None = None,
    ) -> None:
        """Create a ledger over ``engine``.

        Args:
            engine: Async engine used for the aggregate read.
            ceiling_usd: Override for the ``configs/llm-limits.yaml`` ceiling.
                Tests pass a small value; production leaves it ``None``.
            enforcement: Predicate deciding whether a breach raises. ``None``
                means "never enforce" — the §9-safe default for any caller that
                has not wired the feature flag.
        """
        self._engine = engine
        self._ceiling: Decimal = (
            ceiling_usd if ceiling_usd is not None else load_llm_limits().session_cost_ceiling_usd
        )
        self._enforcement = enforcement

    @property
    def ceiling_usd(self) -> Decimal:
        """The per-session ceiling this ledger guards against."""
        return self._ceiling

    async def session_total(self, session_id: UUID) -> Decimal:
        """Return the running USD total for ``session_id``.

        Args:
            session_id: The session to total.

        Returns:
            ``SUM(turn_trace.cost_usd)``; ``Decimal("0")`` for an unknown
            session, as the :class:`CostLedger` protocol requires.
        """
        return await session_cost_total(self._engine, session_id)

    async def add(self, session_id: UUID, cost_usd: Decimal) -> None:
        """Protocol-required increment — intentionally a no-op.

        The durable total is derived from ``turn_trace``, and the wrapper
        writes that row (synchronously, via the trace sink) in the same
        invocation that calls this method. Incrementing a second store here
        would create exactly the drift spec Clarification 1 rules out.

        Args:
            session_id: The session being charged (unused).
            cost_usd: The charge (validated, then discarded).

        Raises:
            ValueError: ``cost_usd`` is negative — the protocol forbids it, and
                a negative charge would silently corrupt the ceiling maths of
                any ledger that DID store it.
        """
        del session_id
        if cost_usd < 0:
            raise ValueError(f"cost_usd must be non-negative (got {cost_usd})")

    async def guard_session_budget(self, session_id: UUID) -> Decimal:
        """Pre-call ceiling guard (constitution §12, dark-launched per §9).

        Args:
            session_id: The session about to issue a model call.

        Returns:
            The running total, so the caller can surface it without a second
            round trip.

        Raises:
            SessionBudgetExceeded: The total has reached the ceiling AND the
                injected predicate says enforcement is on. The shell maps this
                onto ``ABORTED(cost_ceiling)`` (state-machine contract §2) plus
                a ``session_decision`` row.
        """
        total = await self.session_total(session_id)
        if total < self._ceiling:
            return total

        enforced = False if self._enforcement is None else await self._enforcement()
        _LOGGER.warning(
            "session_cost_ceiling_enforced" if enforced else "session_cost_ceiling_reached",
            session_id=str(session_id),
            enforced=enforced,
            ceiling_usd=str(self._ceiling),
            metric=SESSION_COST_METRIC,
            **{SESSION_COST_METRIC: str(total)},
        )
        if enforced:
            raise SessionBudgetExceeded(
                f"session {session_id} at {total} USD has reached the "
                f"{self._ceiling} USD per-session ceiling"
            )
        return total
