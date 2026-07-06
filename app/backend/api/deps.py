"""FastAPI dependencies for the HTTP API (T13, auth wired by T07).

- :func:`get_db` — a request-scoped :class:`AsyncSession` (commit on success,
  rollback on error, always close).
- :func:`get_current_user` / :func:`require_roles` — the **authorization seam**.
  T07 backs it with real Identity Platform JWT verification
  (:mod:`app.backend.services.auth`, contract
  ``docs/contracts/id-token-claims.json``) behind the §9 ``AUTH_MODE`` seam:
  with no verifier installed (``AUTH_MODE=disabled``, the default) every
  request is rejected 401 — the exact pre-T07 posture — and tests keep
  overriding this dependency. ``require_roles`` enforces the
  recruiter/admin gate (403) and is untouched by T07.
- :func:`require_crud_enabled` — the §9 feature-flag gate (404 when the flag is
  off), checked before authorization so a disabled feature returns 404 to all.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.db.session import get_sessionmaker
from app.backend.services.auth import (
    MissingRoleClaimError,
    TokenVerificationError,
    get_verifier,
)
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
    """The authenticated staff identity produced by the auth seam.

    ``user_id`` stays ``None`` until the task that owns the staff ``user``
    aggregate maps GCIP subjects to rows; ``sub``/``email`` arrive with T07
    (additive — pre-T07 call sites constructing ``Principal(user_id, role)``
    are unaffected).
    """

    user_id: uuid.UUID | None
    role: str
    sub: str | None = None
    email: str | None = None


#: OpenAPI-visible bearer scheme. ``auto_error=False`` so the missing-header
#: case flows through :func:`get_current_user`'s own 401 (with the §9
#: disabled-mode message taking precedence over the missing-token one).
_bearer_scheme = HTTPBearer(
    auto_error=False,
    bearerFormat="JWT",
    scheme_name="IdentityPlatformBearer",
    description=(
        "Identity Platform ID token for staff SSO; verified claims contract: "
        "docs/contracts/id-token-claims.json (T07, ADR-024)."
    ),
)


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> Principal:
    """Resolve the staff identity from the Identity Platform bearer token (T07).

    Dark-launch seam (§9): when ``AUTH_MODE=disabled`` (the default) no
    verifier is installed and every request is rejected 401 — the exact
    pre-T07 posture. Local dev and tests need no real tokens; tests override
    this dependency exactly as before T07.

    Args:
        request: The incoming request; ``request.state.user`` is populated
            with ``{sub, email, role}`` on success for downstream audit use.
        credentials: The parsed ``Authorization: Bearer`` header, if any.

    Returns:
        The verified :class:`Principal`.

    Raises:
        HTTPException: 401 for disabled auth, missing bearer token, or any
            token verification failure; 403 for a valid identity that
            carries no staff role claim.
    """
    verifier = get_verifier()
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication is disabled (AUTH_MODE=disabled; T07 dark launch)",
        )
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        identity = await verifier.verify(credentials.credentials)
    except MissingRoleClaimError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "authenticated, but this account has no staff role. Ask an "
                "operator to add the account to configs/auth-roles.yaml "
                "(role: admin | recruiter | reviewer) and sign in again."
            ),
        ) from exc
    except TokenVerificationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or unauthorized bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    request.state.user = {"sub": identity.sub, "email": identity.email, "role": identity.role}
    return Principal(user_id=None, role=identity.role, sub=identity.sub, email=identity.email)


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
