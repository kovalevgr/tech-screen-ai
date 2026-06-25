"""Stateful (DB-backed) validation for Position Templates (T12).

These rules need a database and therefore cannot live in the Pydantic boundary
schema. T13's endpoints call :func:`validate_position_template` and map
:class:`PositionTemplateValidationError` to HTTP 422.

The project's data access is SQLAlchemy Core over an :class:`AsyncConnection`
(see ``app/backend/tests/db``), not an ORM session — this validator follows that
convention so it composes with the existing connection/transaction handling.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import bindparam, delete, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.backend.db.models.interview import (
    PositionTemplate,
    PositionTemplateCompetency,
    PositionTemplateStack,
)
from app.backend.schemas.position_template import (
    CompetencySelection,
    PositionLevel,
    PositionTemplateCreate,
    PositionTemplateRead,
    PositionTemplateUpdate,
)

_STACKS_EXIST = text("SELECT id FROM stack WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)
_COMPETENCIES_EXIST = text("SELECT id FROM competency WHERE id IN :ids").bindparams(
    bindparam("ids", expanding=True)
)
_COMPETENCIES_IN_STACKS = text(
    "SELECT c.id FROM competency c "
    "JOIN competency_block cb ON c.competency_block_id = cb.id "
    "WHERE c.id IN :cids AND cb.stack_id IN :sids"
).bindparams(bindparam("cids", expanding=True), bindparam("sids", expanding=True))


class PositionTemplateValidationError(ValueError):
    """A Position Template failed a stateful (DB-backed) validation rule."""


async def validate_position_template(
    conn: AsyncConnection, payload: PositionTemplateCreate
) -> None:
    """Raise :class:`PositionTemplateValidationError` on the first stateful breach.

    Rules: every ``stack_id`` exists (FR-003); every ``competency_id`` exists and
    belongs to one of the selected stacks via
    ``competency → competency_block → stack`` (FR-006). The error message names
    the offending ids (FR-011). Returns ``None`` when the payload is valid.
    """
    found_stacks = set(
        (await conn.execute(_STACKS_EXIST, {"ids": list(payload.stack_ids)})).scalars().all()
    )
    missing_stacks = set(payload.stack_ids) - found_stacks
    if missing_stacks:
        raise PositionTemplateValidationError(
            f"unknown stack id(s): {sorted(str(s) for s in missing_stacks)}"
        )

    in_selected_stacks = set(
        (
            await conn.execute(
                _COMPETENCIES_IN_STACKS,
                {"cids": list(payload.competency_ids), "sids": list(payload.stack_ids)},
            )
        )
        .scalars()
        .all()
    )
    invalid = set(payload.competency_ids) - in_selected_stacks
    if invalid:
        existing = set(
            (await conn.execute(_COMPETENCIES_EXIST, {"ids": list(payload.competency_ids)}))
            .scalars()
            .all()
        )
        unknown = invalid - existing
        wrong_stack = invalid - unknown
        problems: list[str] = []
        if unknown:
            problems.append(f"unknown competency id(s): {sorted(str(c) for c in unknown)}")
        if wrong_stack:
            problems.append(
                f"competency id(s) not in any selected stack: {sorted(str(c) for c in wrong_stack)}"
            )
        raise PositionTemplateValidationError("; ".join(problems))


# ---------------------------------------------------------------------------
# Persistence (T13). One AsyncSession per request; the router's get_db owns the
# commit. Helpers flush (not commit) so generated ids are available for the
# response while the transaction boundary stays with the caller.
# ---------------------------------------------------------------------------


async def _assemble_read(session: AsyncSession, tmpl: PositionTemplate) -> PositionTemplateRead:
    """Build the read shape for a template from its association rows."""
    stack_ids = (
        (
            await session.execute(
                select(PositionTemplateStack.stack_id).where(
                    PositionTemplateStack.position_template_id == tmpl.id
                )
            )
        )
        .scalars()
        .all()
    )
    comp_rows = (
        await session.execute(
            select(
                PositionTemplateCompetency.competency_id,
                PositionTemplateCompetency.must_have,
            ).where(PositionTemplateCompetency.position_template_id == tmpl.id)
        )
    ).all()
    return PositionTemplateRead(
        id=tmpl.id,
        title=tmpl.title,
        level=PositionLevel(tmpl.level),
        jd_text=tmpl.jd_text,
        archived_at=tmpl.archived_at,
        created_at=tmpl.created_at,
        created_by=tmpl.created_by,
        stack_ids=list(stack_ids),
        competencies=[
            CompetencySelection(competency_id=cid, must_have=must) for cid, must in comp_rows
        ],
    )


async def create_position_template(
    session: AsyncSession,
    payload: PositionTemplateCreate,
    *,
    created_by: uuid.UUID | None = None,
) -> PositionTemplateRead:
    """Validate + persist a new template and its selections (single transaction)."""
    await validate_position_template(await session.connection(), payload)
    tmpl = PositionTemplate(
        title=payload.title,
        jd_text=payload.jd_text,
        level=payload.level.value,
        created_by=created_by,
    )
    session.add(tmpl)
    await session.flush()
    must_have = set(payload.must_have_competency_ids)
    for stack_id in payload.stack_ids:
        session.add(PositionTemplateStack(position_template_id=tmpl.id, stack_id=stack_id))
    for competency_id in payload.competency_ids:
        session.add(
            PositionTemplateCompetency(
                position_template_id=tmpl.id,
                competency_id=competency_id,
                must_have=competency_id in must_have,
            )
        )
    await session.flush()
    return await _assemble_read(session, tmpl)


async def get_position_template(
    session: AsyncSession, template_id: uuid.UUID
) -> PositionTemplateRead | None:
    """Return one template (with selections), or None if it does not exist."""
    tmpl = await session.get(PositionTemplate, template_id)
    if tmpl is None:
        return None
    return await _assemble_read(session, tmpl)


async def list_position_templates(
    session: AsyncSession, *, include_archived: bool = False
) -> list[PositionTemplateRead]:
    """List templates, excluding archived ones unless ``include_archived``."""
    stmt = select(PositionTemplate)
    if not include_archived:
        stmt = stmt.where(PositionTemplate.archived_at.is_(None))
    stmt = stmt.order_by(PositionTemplate.created_at)
    templates = (await session.execute(stmt)).scalars().all()
    return [await _assemble_read(session, tmpl) for tmpl in templates]


async def _current_selection(
    session: AsyncSession, template_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID], list[uuid.UUID]]:
    """Return ``(stack_ids, competency_ids, must_have_ids)`` for a template."""
    stack_ids = list(
        (
            await session.execute(
                select(PositionTemplateStack.stack_id).where(
                    PositionTemplateStack.position_template_id == template_id
                )
            )
        )
        .scalars()
        .all()
    )
    comp_rows = (
        await session.execute(
            select(
                PositionTemplateCompetency.competency_id,
                PositionTemplateCompetency.must_have,
            ).where(PositionTemplateCompetency.position_template_id == template_id)
        )
    ).all()
    competency_ids = [cid for cid, _ in comp_rows]
    must_have_ids = [cid for cid, must in comp_rows if must]
    return stack_ids, competency_ids, must_have_ids


async def update_position_template(
    session: AsyncSession, template_id: uuid.UUID, patch: PositionTemplateUpdate
) -> PositionTemplateRead | None:
    """Apply a partial update; replace selection sets wholesale; re-validate."""
    tmpl = await session.get(PositionTemplate, template_id)
    if tmpl is None:
        return None

    fields = patch.model_fields_set
    if "must_have_competency_ids" in fields and patch.competency_ids is None:
        raise PositionTemplateValidationError(
            "must_have_competency_ids requires competency_ids in the same update"
        )

    cur_stacks, cur_comps, cur_must = await _current_selection(session, template_id)
    resulting_title = patch.title if patch.title is not None else tmpl.title
    resulting_level = patch.level if patch.level is not None else PositionLevel(tmpl.level)
    resulting_jd = patch.jd_text if "jd_text" in fields else tmpl.jd_text
    resulting_stacks = patch.stack_ids if patch.stack_ids is not None else cur_stacks
    resulting_comps = patch.competency_ids if patch.competency_ids is not None else cur_comps
    resulting_must = (
        (patch.must_have_competency_ids or []) if patch.competency_ids is not None else cur_must
    )

    # Re-run the full rule set against the resulting state (stateless via the
    # create model + stateful via the validator).
    try:
        resulting = PositionTemplateCreate(
            title=resulting_title,
            level=resulting_level,
            jd_text=resulting_jd,
            stack_ids=resulting_stacks,
            competency_ids=resulting_comps,
            must_have_competency_ids=resulting_must,
        )
    except ValueError as exc:  # pydantic ValidationError is a ValueError
        raise PositionTemplateValidationError(str(exc)) from exc
    await validate_position_template(await session.connection(), resulting)

    tmpl.title = resulting_title
    tmpl.level = resulting_level.value
    tmpl.jd_text = resulting_jd

    if patch.stack_ids is not None:
        await session.execute(
            delete(PositionTemplateStack).where(
                PositionTemplateStack.position_template_id == tmpl.id
            )
        )
        for stack_id in resulting_stacks:
            session.add(PositionTemplateStack(position_template_id=tmpl.id, stack_id=stack_id))
    if patch.competency_ids is not None:
        await session.execute(
            delete(PositionTemplateCompetency).where(
                PositionTemplateCompetency.position_template_id == tmpl.id
            )
        )
        must_set = set(resulting_must)
        for competency_id in resulting_comps:
            session.add(
                PositionTemplateCompetency(
                    position_template_id=tmpl.id,
                    competency_id=competency_id,
                    must_have=competency_id in must_set,
                )
            )
    await session.flush()
    return await _assemble_read(session, tmpl)


async def archive_position_template(
    session: AsyncSession, template_id: uuid.UUID
) -> PositionTemplateRead | None:
    """Soft-delete: set ``archived_at`` (idempotent); never remove the row."""
    tmpl = await session.get(PositionTemplate, template_id)
    if tmpl is None:
        return None
    if tmpl.archived_at is None:
        tmpl.archived_at = datetime.now(UTC)
    await session.flush()
    return await _assemble_read(session, tmpl)
