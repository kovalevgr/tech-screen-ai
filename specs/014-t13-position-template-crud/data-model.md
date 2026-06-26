# Data Model: Position Template CRUD endpoints (T13)

**No schema change, no migration.** T13 reuses the T12 tables
(`position_template`, `position_template_stack`, `position_template_competency`)
and the T12 validator. It adds two *boundary* models and an auth principal.

## Reused (T12)

- **`position_template`** — `id`, `title`, `jd_text`, `level` (CHECK enum),
  `archived_at` (NULL = active), `created_by` (FK→`user`), `created_at`.
- **`position_template_stack`** / **`position_template_competency`** — selection
  association rows (the latter with `must_have`).
- **`PositionTemplateCreate` / `PositionTemplateRead` / `CompetencySelection`** —
  request/response schemas (`app/backend/schemas/position_template.py`).
- **`validate_position_template(conn, payload)`** — stateful rules (stack exists,
  competency-in-selected-stack), raising `PositionTemplateValidationError`.

## New boundary model — `PositionTemplateUpdate` (PATCH body)

All fields optional; only provided fields are applied (research §4).

| Field | Type | Notes |
| --- | --- | --- |
| `title` | `str` (1..200) \| absent | |
| `level` | `PositionLevel` \| absent | |
| `jd_text` | `str \| null` \| absent | |
| `stack_ids` | `list[uuid]` (≥1, unique) \| absent | if present → replace the stack set |
| `competency_ids` | `list[uuid]` (≥1, unique) \| absent | if present → replace the selected set |
| `must_have_competency_ids` | `list[uuid]` (unique) \| absent | must be ⊆ the resulting competency set |

Stateless validators mirror `PositionTemplateCreate` for any provided lists; the
"⊆" / "≥1" checks run against the **resulting** state (existing values merged with
the patch) before persisting, then `validate_position_template` re-checks the
stateful rules.

## New — auth principal (seam)

| Entity | Fields | Notes |
| --- | --- | --- |
| `Principal` | `user_id: uuid \| None`, `role: str` | Produced by `get_current_user` (seam). Until T07, default impl raises 401. `require_roles("recruiter","admin")` → 403 if role not allowed. |

## New — feature flag (§9, no schema change)

| Flag | Default | Gate | Notes |
| --- | --- | --- | --- |
| `position_template_crud_enabled` | `false` | `require_crud_enabled` dependency → **404** when off | Declared in `configs/feature-flags.yaml` (state active) + indexed in `docs/engineering/feature-flags.md`. No DB seed/migration — `is_enabled` falls back to the YAML default until flipped. Checked **before** auth so a disabled feature returns 404 to everyone. |

## Operation flows

Every endpoint first passes the **`require_crud_enabled`** gate (404 if the flag
is off), **then** the auth checks below.

| Verb / path | Flow | Status |
| --- | --- | --- |
| `POST /position-templates` | authz → validate (Pydantic + `validate_position_template` on `session.connection()`) → insert template + association rows in one tx → return Read | 201 / 422 / 401 / 403 |
| `GET /position-templates?include_archived=` | authz → select templates (`WHERE archived_at IS NULL` unless `include_archived`) → assemble Read[] | 200 / 401 / 403 |
| `GET /position-templates/{id}` | authz → select one (+ associations) → Read | 200 / 404 / 401 / 403 |
| `PATCH /position-templates/{id}` | authz → load → apply provided fields → (if selections provided) replace association sets → re-validate → commit → Read | 200 / 422 / 404 / 401 / 403 |
| `DELETE /position-templates/{id}` | authz → load → set `archived_at = now()` (no row removal) → return archived Read | 200 / 404 / 401 / 403 |

## Transaction boundary

One `AsyncSession` per request (`get_db`). Create/patch/archive happen in a single
transaction committed on success and rolled back on any error — so a mid-write
failure leaves no partial template (FR-010). Reads are non-mutating.

## Invariants preserved

- **Soft-delete only** (FR-007): DELETE sets `archived_at`; no `DELETE FROM`.
- **Default list excludes archived** (FR-005): `WHERE archived_at IS NULL` unless `?include_archived=true`.
- **Validation parity** (FR-003/006): create and patch run the same rule set.
