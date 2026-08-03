"""Dev-only session API over the live orchestrator (T22).

Implements ``docs/contracts/dev-session-api.yaml`` exactly — four operations,
one per contract ``operationId``. This is the §9 exposure point the
orchestrator itself deliberately lacked (spec 032 Clarification 5), so two
gates sit in front of every route:

1. **Feature flag** ``enable_live_orchestrator`` (default ``false``). Off →
   404-as-if-absent, checked before authorization so a dark feature leaks
   nothing, not even its existence.
2. **Role**, but only when there is an identity to check: under
   ``AUTH_MODE=identity_platform`` the caller must be ``reviewer`` or
   ``admin``; under the default ``AUTH_MODE=disabled`` there is no verifier and
   the local dev surface is open, exactly like every other local-only tool.

This is NOT the candidate surface. The magic-link + WebSocket path is Tier 5
(T28/T29a) and will carry its own contract, its own flag and its own auth.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.backend.api.deps import Principal, get_optional_current_user
from app.backend.db.session import get_engine
from app.backend.orchestrator.config import OrchestratorConfig, load_orchestrator_config
from app.backend.services.dev_session import (
    DevSessionNotAwaitingCandidate,
    DevSessionNotFound,
    DevSessionPlanInvalid,
    DevSessionService,
    SessionView,
    TaskScheduler,
    TraceList,
    TurnResult,
)
from app.backend.services.feature_flags import is_enabled
from app.backend.settings import Settings

router = APIRouter(prefix="/api/dev/sessions", tags=["dev-sessions"])

_DEV_SESSION_ROLES: frozenset[str] = frozenset({"reviewer", "admin"})

_NOT_FOUND = {"description": "Unknown session (or flag disabled)."}
_CONFLICT = {"description": "Session is terminal or not awaiting a candidate turn."}
_PLAN_INVALID = {"description": "PlanInvalid — machine refused the plan (state-machine §7)."}


# ---------------------------------------------------------------------------
# Request bodies (contract: additionalProperties false)
# ---------------------------------------------------------------------------


class CreateSessionRequest(BaseModel):
    """``devCreateSession`` body — an inline plan, nothing else."""

    model_config = ConfigDict(extra="forbid")

    plan: dict[str, object]
    """Exactly ``state-machine.md`` §7. Validated by the machine, not here:
    an invalid plan must surface as the contract's 422, not as a shape error
    on a schema this router invented."""


class PostTurnRequest(BaseModel):
    """``devPostTurn`` body — the candidate's answer."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8000)


# ---------------------------------------------------------------------------
# Gates + wiring
# ---------------------------------------------------------------------------


async def require_live_orchestrator() -> None:
    """§9 gate: 404 when ``enable_live_orchestrator`` is off.

    The flag name is a string literal (not a constant) so the bidirectional
    feature-flag registration hook can detect this call site.
    """
    if not await is_enabled("enable_live_orchestrator"):
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)


async def require_dev_session_access(
    principal: Annotated[Principal | None, Depends(get_optional_current_user)],
) -> Principal | None:
    """Admit reviewers and admins; admit everyone when auth is switched off.

    Args:
        principal: ``None`` under ``AUTH_MODE=disabled`` (no verifier
            installed), otherwise the verified staff identity.

    Returns:
        The principal, or ``None`` when there is no identity layer at all.

    Raises:
        HTTPException: 403 for an authenticated non-reviewer.
    """
    if principal is None:
        return None
    if principal.role not in _DEV_SESSION_ROLES:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail=f"role {principal.role!r} may not drive dev interview sessions",
        )
    return principal


@lru_cache(maxsize=1)
def _config() -> OrchestratorConfig:
    """Process-lifetime cache of the committed thresholds (§16)."""
    return load_orchestrator_config()


@lru_cache(maxsize=1)
def _settings() -> Settings:
    """Process-lifetime cache of the runtime settings."""
    return Settings()


class _BackgroundTasksScheduler:
    """Adapter putting ``RunAssessor`` work on Starlette's background queue.

    The contract's "assessor scheduled in background" and the machine's §6.1
    ("never block the next interviewer move on a pending assessment") are the
    same requirement seen from two sides; this is where it is honoured.
    """

    def __init__(self, tasks: BackgroundTasks) -> None:
        self._tasks = tasks

    def schedule(self, task: object) -> None:
        self._tasks.add_task(task)  # type: ignore[arg-type]  # zero-arg async callable


def get_dev_session_service(background: BackgroundTasks) -> DevSessionService:
    """Build the shell for one request.

    Args:
        background: Starlette's per-request background queue.

    Returns:
        A :class:`DevSessionService` bound to the process engine.
    """
    scheduler: TaskScheduler = _BackgroundTasksScheduler(background)
    return DevSessionService(
        engine=get_engine(),
        settings=_settings(),
        config=_config(),
        scheduler=scheduler,
    )


ServiceDep = Annotated[DevSessionService, Depends(get_dev_session_service)]
AccessDep = Annotated[Principal | None, Depends(require_dev_session_access)]
FlagDep = Depends(require_live_orchestrator)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "",
    operation_id="devCreateSession",
    status_code=HTTPStatus.CREATED,
    response_model=SessionView,
    dependencies=[FlagDep],
    responses={HTTPStatus.UNPROCESSABLE_ENTITY: _PLAN_INVALID},
    summary="Create a session from an inline PlanSnapshot and run SessionStarted.",
)
async def create_session(
    body: CreateSessionRequest, _access: AccessDep, service: ServiceDep
) -> SessionView:
    try:
        return await service.create_session(body.plan)
    except DevSessionPlanInvalid as exc:
        raise HTTPException(status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.post(
    "/{session_id}/turns",
    operation_id="devPostTurn",
    response_model=TurnResult,
    dependencies=[FlagDep],
    responses={HTTPStatus.NOT_FOUND: _NOT_FOUND, HTTPStatus.CONFLICT: _CONFLICT},
    summary="Candidate turn → transition → interviewer reply.",
)
async def post_turn(
    session_id: uuid.UUID, body: PostTurnRequest, _access: AccessDep, service: ServiceDep
) -> TurnResult:
    try:
        return await service.post_turn(session_id, body.text)
    except DevSessionNotFound as exc:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from exc
    except DevSessionNotAwaitingCandidate as exc:
        raise HTTPException(status_code=HTTPStatus.CONFLICT, detail=str(exc)) from exc


@router.get(
    "/{session_id}",
    operation_id="devGetSession",
    response_model=SessionView,
    dependencies=[FlagDep],
    responses={HTTPStatus.NOT_FOUND: _NOT_FOUND},
    summary="Current state view (poll target for the dev UI).",
)
async def get_session(
    session_id: uuid.UUID, _access: AccessDep, service: ServiceDep
) -> SessionView:
    try:
        return await service.get_session(session_id)
    except DevSessionNotFound as exc:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from exc


@router.get(
    "/{session_id}/traces",
    operation_id="devListTraces",
    response_model=TraceList,
    dependencies=[FlagDep],
    responses={HTTPStatus.NOT_FOUND: _NOT_FOUND},
    summary="Turn-trace rows for the side panel, oldest first.",
)
async def list_traces(session_id: uuid.UUID, _access: AccessDep, service: ServiceDep) -> TraceList:
    try:
        return await service.list_traces(session_id)
    except DevSessionNotFound as exc:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND) from exc
