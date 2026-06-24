# Research: Position Template schema + contract (T12)

Phase 0 decisions. Each resolves an unknown surfaced by the Technical Context.

## §1 — `level` representation: TEXT + CHECK (not a native PG enum)

- **Decision**: Store `level` as `TEXT` with a `CHECK (level IN ('Junior','Middle','Senior','Tech Leader'))` constraint. Mirror the allowed set as a Python `StrEnum` (`PositionLevel`) used by the Pydantic schemas.
- **Rationale**: A native Postgres `ENUM` type is painful to evolve — adding/removing a value needs `ALTER TYPE`, which is exactly the kind of non-trivial DDL §10 wants to avoid later (and `ALTER TYPE ... ` is awkward to make zero-downtime). A `TEXT + CHECK` column extends cleanly: a future level is a one-line `CHECK` swap in an additive migration. The rubric tree already stores its enumerable text as `TEXT` (`stack.name`, `level.descriptor`), so this matches house style.
- **Alternatives considered**: (a) native PG `ENUM` — rejected (evolution cost, §10 friction); (b) a lookup table `position_level` with an FK — rejected as over-engineered for a fixed 4-value set that the product owner controls.

## §2 — Contract strategy: JSON schema is the §14 artefact; OpenAPI paths land in T13

- **Decision**: Publish `docs/contracts/position-template.schema.json` as the committed §14 contract describing the request/response JSON shape and validation rules. Do **not** add routes in T12; `app/backend/openapi.yaml` is regenerated as a **no-op** (no drift) and `test_openapi_regeneration` stays green unchanged.
- **Rationale**: FastAPI derives `openapi.yaml` from registered routes (`app.openapi()`); with no endpoints there is nothing to emit. §14 explicitly accepts "an OpenAPI spec **or** JSON schema" — the JSON schema fully satisfies the contract-first gate that unblocks T13 ∥ T14. Keeping routes out preserves the clean T12 (schema) / T13 (endpoints) boundary.
- **Alternatives considered**:
  - **Option B — register read-only endpoint stubs in T12** so OpenAPI paths appear now. Rejected: bleeds T13's endpoint surface into T12, requires stub handlers (501/NotImplemented), and the OpenAPI paths would then change again in T13 anyway. Documented in plan.md so the user can opt into it at the gate.
  - Hand-editing `openapi.yaml` — rejected: the file is generated + drift-checked; manual edits would fail `test_openapi_regeneration`.

## §3 — Additive migration safety on an existing populated-in-dev table

- **Decision**: `0004_position_template` uses raw `op.execute("ALTER TABLE position_template ADD COLUMN ...")` strings (house style, see `0003`). New non-null columns get a transitional `DEFAULT`: `title TEXT NOT NULL DEFAULT ''`. `archived_at TIMESTAMPTZ` and `created_by UUID` are nullable. Association tables are `CREATE TABLE`. A `CHECK` constraint and `UNIQUE` constraints are `ADD CONSTRAINT`.
- **Rationale**: §10 zero-downtime: adding a `NOT NULL` column to a table that may already hold dev/probe rows requires a default to avoid a failing/locking backfill. `0003` set the exact precedent (`payload_hash TEXT NOT NULL DEFAULT ''`). The empty-string default is transitional only — Pydantic enforces a non-empty title at the boundary, so no real row is ever created with `title=''`.
- **Alternatives considered**: `op.add_column()` SQLAlchemy ops — rejected: house style is raw `op.execute` SQL strings (it makes the rendered `--sql` in T10's CI review literal and greppable by the destructive-DDL detector).

## §4 — Stacks/competencies as association tables, not JSON columns

- **Decision**: Model the selections as two association tables — `position_template_stack` and `position_template_competency` (the latter carries `must_have BOOLEAN`). FKs to `stack.id` / `competency.id`; `UNIQUE` on `(position_template_id, <ref>_id)`.
- **Rationale**: FR-003 (stacks must exist) and FR-006 (competency belongs to a selected stack) require referential integrity. Real FKs give DB-enforced existence + cascade-safe archival; a `JSONB` array of ids would push every integrity check into app code and lose the FK guarantee. The rubric tree already models parent/child via FK rows, so this matches house style.
- **Alternatives considered**: `JSONB` arrays of ids on `position_template` — rejected (no referential integrity, harder validation, no UNIQUE).

## §5 — Where stateful validation lives (no endpoints yet)

- **Decision**: Split validation by what it needs:
  - **Stateless (Pydantic v2 validators in `schemas/position_template.py`)**: `level` enum, must-have ⊆ selected, ≥1 selected competency, de-duplicate repeated ids.
  - **Stateful (a `services/position_template.py::validate_position_template(session, payload)` function)**: stack existence (FR-003), competency existence, competency-belongs-to-a-selected-stack (FR-006). These need a DB query.
- **Rationale**: Pydantic is stateless and runs at the boundary; DB-dependent rules cannot live there. A standalone validator function is directly unit/integration-testable now (US1's "no HTTP endpoint needed") and is the exact seam T13's `POST/PATCH` handlers call later. Raising a typed domain error (`PositionTemplateValidationError`) keeps FR-011 (specific messages) and lets T13 map it to HTTP 422.
- **Alternatives considered**: doing everything in a FastAPI dependency — rejected (no endpoints in T12); DB CHECK/trigger for the cross-stack rule — rejected (too rigid; the rule spans three tables and is clearer in Python with a precise error message).

## §6 — Pydantic v2 + async SQLAlchemy patterns

- **Decision**: Pydantic v2 `BaseModel` with `model_config = ConfigDict(extra="forbid")`; `field_validator`/`model_validator` for the stateless rules; `PositionTemplateRead.model_config = ConfigDict(from_attributes=True)` for ORM serialization. The validator service uses the existing async session pattern from T05/T08.
- **Rationale**: Matches the existing LLM/config Pydantic models and the async DB code already in the repo. `extra="forbid"` mirrors the contract's `additionalProperties: false`.
- **Alternatives considered**: dataclasses — rejected (Pydantic is the project standard for boundary models).

## Open follow-ups (out of T12 scope, noted for later tiers)

- §16 Git-promotion + drift-checker for position templates (export DB → `configs/`) — belongs with the Admin UI tier (T14+), not T12.
- OpenAPI **paths** for Position Template endpoints — T13.
- Rubric-version pinning / immutable snapshot of a template's selections onto a session — T15.
