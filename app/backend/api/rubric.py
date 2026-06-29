"""Rubric read endpoints.

`GET /rubric/active` returns the active rubric version's full tree (the
`RubricSnapshot` shape, T15) for the `recruiter`/`admin` role. Read-only — the
rubric is edited only through the Git/YAML import path, never the API. Powers the
Position Template admin form (T14) and the future Rubric Browser (screen 15).
"""

from __future__ import annotations

from http import HTTPStatus

from fastapi import APIRouter, HTTPException

from app.backend.api.deps import ManagerDep, SessionDep
from app.backend.schemas.rubric_snapshot import RubricSnapshot
from app.backend.services.rubric_snapshot import get_active_rubric_snapshot

router = APIRouter(prefix="/rubric", tags=["rubric"])


@router.get("/active", response_model=RubricSnapshot)
async def read_active_rubric(_manager: ManagerDep, session: SessionDep) -> RubricSnapshot:
    result = await get_active_rubric_snapshot(await session.connection())
    if result is None:
        raise HTTPException(HTTPStatus.NOT_FOUND)
    return result
