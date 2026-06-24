# Data Model: Position Template schema + contract (T12)

Migration: `0004_position_template` (down_revision `0003_rubric_payload_hash`).
All DDL is **additive** — no `DROP`, no type-narrowing `ALTER` → `needs_adr=false`.

## Table: `position_template` (EXTEND existing T05 placeholder)

Existing columns (from T05 via mixins): `id UUID PK DEFAULT gen_random_uuid()`,
`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`.

| New column | Type | Null | Default | Notes / FR |
| --- | --- | --- | --- | --- |
| `title` | `TEXT` | NOT NULL | `''` (transitional) | Role title. Pydantic enforces non-empty at boundary. FR-001 |
| `jd_text` | `TEXT` | NULL | — | Optional job-description text. FR-001 |
| `level` | `TEXT` | NOT NULL | `'Middle'` (transitional) | `CHECK (level IN ('Junior','Middle','Senior','Tech Leader'))`. FR-002 |
| `archived_at` | `TIMESTAMPTZ` | NULL | — | Soft-delete marker; NULL = active. FR-007 |
| `created_by` | `UUID` | NULL | — | FK → `user.id`. Ownership for later authz (T13). FR-012 |

Constraints added:

- `ck_position_template_level` — `CHECK (level IN ('Junior','Middle','Senior','Tech Leader'))`.
- `fk_position_template_created_by_user` — `FOREIGN KEY (created_by) REFERENCES "user"(id)`.

> `position_template` is **not** an append-only table (§3 list excludes it).
> Recruiter edits are normal UPDATEs. Deletion is soft (set `archived_at`).

## Table: `position_template_stack` (NEW — stack selections)

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | NOT NULL | `gen_random_uuid()` | PK (UUIDPk mixin) |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | TimestampCreated mixin |
| `position_template_id` | `UUID` | NOT NULL | — | FK → `position_template.id` |
| `stack_id` | `UUID` | NOT NULL | — | FK → `stack.id` |

- `uq_position_template_stack` — `UNIQUE (position_template_id, stack_id)` (no duplicate stack per template).

## Table: `position_template_competency` (NEW — competency selections)

| Column | Type | Null | Default | Notes |
| --- | --- | --- | --- | --- |
| `id` | `UUID` | NOT NULL | `gen_random_uuid()` | PK |
| `created_at` | `TIMESTAMPTZ` | NOT NULL | `now()` | |
| `position_template_id` | `UUID` | NOT NULL | — | FK → `position_template.id` |
| `competency_id` | `UUID` | NOT NULL | — | FK → `competency.id` |
| `must_have` | `BOOLEAN` | NOT NULL | `false` | `true` = mandatory; `false` = nice-to-have. FR-001 |

- `uq_position_template_competency` — `UNIQUE (position_template_id, competency_id)`.

> The "selected (optional) set" = **all** rows for a template; the "must-have
> set" = rows with `must_have = true`. The must-have ⊆ selected rule (FR-004) is
> therefore structurally guaranteed at the DB level (a must-have row *is* a
> selected row) and additionally enforced at the request boundary, where the
> caller sends a selected list + a must-have list as separate id arrays.

## Validation rules → FR map

| Rule | Layer | FR | Test |
| --- | --- | --- | --- |
| `level ∈ {Junior, Middle, Senior, Tech Leader}` | Pydantic enum + DB CHECK | FR-002 | schema + migration |
| must-have ⊆ selected | Pydantic `model_validator` | FR-004 | schema |
| ≥ 1 selected competency | Pydantic `model_validator` | FR-005 | schema |
| no duplicate stack / competency ids in a request | Pydantic `model_validator` | edge case | schema |
| referenced stack exists | service validator (DB query) | FR-003 | service |
| referenced competency exists | service validator (DB query) | FR-003/006 | service |
| competency belongs to a selected stack | service validator (DB query) | FR-006 | service |
| deletion = set `archived_at`, row preserved | ORM/service (T13 uses it) | FR-007 | migration/service |

`validate_position_template(session, payload)` raises
`PositionTemplateValidationError` with a field-specific message (FR-011) on the
first stateful breach; returns normally when valid. T13's endpoints call it and
map the error to HTTP 422.

## Request / response shapes (Pydantic → JSON-schema contract)

**`PositionTemplateCreate`** (request): `title` (str, non-empty), `level`
(enum), `jd_text` (str | null), `stack_ids` (array<uuid>, ≥1, unique),
`competency_ids` (array<uuid>, ≥1, unique — the selected/optional set),
`must_have_competency_ids` (array<uuid>, unique, ⊆ `competency_ids`).

**`PositionTemplateRead`** (response): `id`, `title`, `level`, `jd_text`,
`archived_at`, `created_at`, `created_by`, `stack_ids`, and `competencies`
(array of `{competency_id, must_have}`).

These map 1:1 to `docs/contracts/position-template.schema.json`.

## Entity relationships (text)

```
user (existing) ──< position_template ──< position_template_stack >── stack (existing rubric)
                              │
                              └──< position_template_competency >── competency (existing rubric)
interview_session.position_template_id ──> position_template   (existing nullable FK, T05)
```

## Migration downgrade

Symmetric `downgrade()` for dev only (forward-only in prod, §10): drop the two
association tables, then drop the added constraints and columns with
`IF EXISTS`. Production never runs downgrade.
