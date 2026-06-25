"""Position Template CRUD endpoints (T13).

`POST/GET(list)/GET(one)/PATCH/DELETE` over `/position-templates`. Every route is
gated by the §9 feature flag (`require_crud_enabled` → 404 when off, checked
before auth) and requires the `recruiter`/`admin` role (`ManagerDep`). Deletion
is a soft archive — no row is ever removed. Persistence + validation live in
`app.backend.services.position_template`.
"""

from __future__ import annotations

import uuid
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, status

from app.backend.api.deps import ManagerDep, SessionDep, require_crud_enabled
from app.backend.schemas.position_template import (
    PositionTemplateCreate,
    PositionTemplateRead,
    PositionTemplateUpdate,
)
from app.backend.services import position_template as svc
from app.backend.services.position_template import PositionTemplateValidationError

router = APIRouter(
    prefix="/position-templates",
    tags=["position-templates"],
    dependencies=[Depends(require_crud_enabled)],
)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PositionTemplateRead)
async def create_position_template(
    payload: PositionTemplateCreate, manager: ManagerDep, session: SessionDep
) -> PositionTemplateRead:
    try:
        return await svc.create_position_template(session, payload, created_by=manager.user_id)
    except PositionTemplateValidationError as exc:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.get("", response_model=list[PositionTemplateRead])
async def list_position_templates(
    _manager: ManagerDep, session: SessionDep, include_archived: bool = False
) -> list[PositionTemplateRead]:
    return await svc.list_position_templates(session, include_archived=include_archived)


@router.get("/{template_id}", response_model=PositionTemplateRead)
async def get_position_template(
    template_id: uuid.UUID, _manager: ManagerDep, session: SessionDep
) -> PositionTemplateRead:
    result = await svc.get_position_template(session, template_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return result


@router.patch("/{template_id}", response_model=PositionTemplateRead)
async def update_position_template(
    template_id: uuid.UUID,
    patch: PositionTemplateUpdate,
    _manager: ManagerDep,
    session: SessionDep,
) -> PositionTemplateRead:
    try:
        result = await svc.update_position_template(session, template_id, patch)
    except PositionTemplateValidationError as exc:
        raise HTTPException(HTTPStatus.UNPROCESSABLE_ENTITY, str(exc)) from exc
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return result


@router.delete("/{template_id}", response_model=PositionTemplateRead)
async def archive_position_template(
    template_id: uuid.UUID, _manager: ManagerDep, session: SessionDep
) -> PositionTemplateRead:
    result = await svc.archive_position_template(session, template_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return result
