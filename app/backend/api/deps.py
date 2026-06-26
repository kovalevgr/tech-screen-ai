"""FastAPI dependencies for the HTTP API (T13).

- :func:`get_db` — a request-scoped :class:`AsyncSession` (commit on success,
  rollback on error, always close).
- :func:`get_current_user` / :func:`require_roles` — the **authorization seam**.
  Real SSO + role claims are T07 (Identity Platform); until then
  ``get_current_user`` resolves no identity (401) and is overridden in tests.
  ``require_roles`` enforces the recruiter/admin gate (403).
- :func:`require_crud_enabled` — the §9 feature-flag gate (404 when the flag is
  off), checked before authorization so a disabled feature returns 404 to all.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.db.session import get_sessionmaker
from app.backend.services.feature_flags import is_enabled


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped session; commit on success, rollback on error."""
    session = get_sessionmaker()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


class Principal(BaseModel):
    """The authenticated staff identity produced by the auth seam."""

    user_id: uuid.UUID | None
    role: str


async def get_current_user() -> Principal:
    """Authorization seam — overridden in tests; real wiring is T07.

    Until T07 wires Identity Platform, no identity is resolved, so every request
    is unauthenticated. Returning 401 keeps the surface safely dark.
    """
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication is not configured yet (T07)",
    )


def require_roles(*roles: str) -> Callable[[Principal], Awaitable[Principal]]:
    """Build a dependency that admits only ``roles`` (else 403)."""
    allowed = frozenset(roles)

    async def _checker(
        principal: Annotated[Principal, Depends(get_current_user)],
    ) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"role {principal.role!r} may not manage position templates",
            )
        return principal

    return _checker


async def require_crud_enabled() -> None:
    """§9 gate: 404 when ``position_template_crud_enabled`` is off.

    The flag name is a string literal (not a constant) so the bidirectional
    feature-flag registration hook can detect this call site.
    """
    if not await is_enabled("position_template_crud_enabled"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


#: Reusable typed dependencies for routers.
SessionDep = Annotated[AsyncSession, Depends(get_db)]
ManagerDep = Annotated[Principal, Depends(require_roles("recruiter", "admin"))]
