"""Stateful (DB-backed) validation for Position Templates (T12).

These rules need a database and therefore cannot live in the Pydantic boundary
schema. T13's endpoints call :func:`validate_position_template` and map
:class:`PositionTemplateValidationError` to HTTP 422.

The project's data access is SQLAlchemy Core over an :class:`AsyncConnection`
(see ``app/backend/tests/db``), not an ORM session — this validator follows that
convention so it composes with the existing connection/transaction handling.
"""

from __future__ import annotations

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.backend.schemas.position_template import PositionTemplateCreate

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
