---
description: "Task list for T12 — Position Template schema + contract"
---

# Tasks: Position Template schema + contract (T12)

**Input**: Design documents from `specs/013-t12-position-template-schema/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/position-template.schema.json, quickstart.md

**Tests**: T12 is a schema + contract task; tests ARE the deliverable's proof. "Tests" = pytest in the `docker-compose.test.yml` `db`-profile stack: stateless schema rules, stateful DB validator rules, the migration apply + additive-DDL + soft-delete, and the JSON-schema contract round-trip. Plus the 138-test regression baseline and `openapi --check` (no-op, Variant A).

**Agent / parallelism**: every task is `agent: backend-engineer`, executed sequentially in one PR (§18 — `parallel: false`). `[P]` marks tasks that touch *different files* with no incomplete dependency; NOT sub-agent fan-out. T12 **unlocks** the T13 ∥ T14 fan-out by committing the §14 contract (T008).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create the two new backend packages with empty `__init__.py`: `app/backend/schemas/__init__.py` and `app/backend/services/__init__.py`. No new dependency is added to `pyproject.toml` / `uv.lock`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The ORM models + migration underpin every schema, validator, and test. They must land before the user-story phases.

**⚠️ CRITICAL**: T004/T005 (schemas, validator) and all tests reference these.

- [ ] T002 Extend `app/backend/db/models/interview.py`: add the domain columns to `PositionTemplate` (`title`, `jd_text`, `level`, `archived_at`, `created_by` FK→`user.id`) and add two new association models — `PositionTemplateStack` (FK→`position_template`, FK→`stack`, UNIQUE pair) and `PositionTemplateCompetency` (FK→`position_template`, FK→`competency`, `must_have BOOLEAN NOT NULL DEFAULT false`, UNIQUE pair). Use the `UUIDPk` + `TimestampCreated` mixins. (data-model.md; FR-001/007/012)
- [ ] T003 Create `alembic/versions/0004_position_template.py` (`down_revision = "0003_rubric_payload_hash"`). Raw `op.execute(...)` additive DDL only (house style, see `0003`): `ALTER TABLE position_template ADD COLUMN` for the five columns (`title TEXT NOT NULL DEFAULT ''`, `jd_text TEXT`, `level TEXT NOT NULL DEFAULT 'Middle'`, `archived_at TIMESTAMPTZ`, `created_by UUID`); `ADD CONSTRAINT ck_position_template_level CHECK (level IN ('Junior','Middle','Senior','Tech Leader'))`; `ADD CONSTRAINT fk_position_template_created_by_user FOREIGN KEY (created_by) REFERENCES "user"(id)`; `CREATE TABLE position_template_stack` + `position_template_competency` with their FKs and `UNIQUE` constraints. Symmetric `downgrade()` with `IF EXISTS` (dev-only; forward-only in prod, §10). No DROP/type-narrowing → `needs_adr=false`. (data-model.md; FR-010)

**Checkpoint**: `alembic upgrade head` reaches `0004_position_template`; the schema is queryable.

---

## Phase 3: User Story 1 — Role definition captured with integrity (Priority: P1) 🎯 MVP

**Goal**: A Position Template's data is held with all four validation rules enforced.

**Independent Test**: Construct a valid template via the schema + validator → accepted; each invalid combination (bad level, unknown stack, must-have ⊄ selected, competency not in a selected stack) → rejected with a specific error. No HTTP endpoint needed.

### Implementation for User Story 1

- [ ] T004 [P] [US1] Create `app/backend/schemas/position_template.py`: `PositionLevel` StrEnum {Junior, Middle, Senior, Tech Leader}; `PositionTemplateCreate` (request) and `PositionTemplateRead` (response) Pydantic v2 models with `extra="forbid"` (+ `from_attributes=True` on Read). Stateless validators: `level` enum (FR-002), `must_have_competency_ids ⊆ competency_ids` (FR-004), `≥1 competency_id` (FR-005), de-duplicate `stack_ids`/`competency_ids` (edge case). Shapes match `contracts/position-template.schema.json`. (data-model.md; FR-001/002/004/005)
- [ ] T005 [P] [US1] Create `app/backend/services/position_template.py`: `PositionTemplateValidationError` (typed, field-specific message — FR-011) and `async def validate_position_template(session, payload)` running the stateful DB rules: every `stack_id` exists (FR-003), every `competency_id` exists, and every selected competency belongs to one of the selected stacks via `competency → competency_block → stack` (FR-006). Raises on the first breach; returns normally when valid. (research §5; FR-003/006/011)
- [ ] T006 [US1] Create `app/backend/tests/schemas/test_position_template_schema.py`: assert `level='Architect'` rejected; `must_have ⊄ selected` rejected; zero competencies rejected; duplicate ids de-duplicated/rejected; a fully-valid payload accepted. (SC-002)
- [ ] T007 [US1] Create `app/backend/tests/services/test_position_template_validate.py` (db profile): seed a rubric tree (stack/competency_block/competency), then assert unknown stack rejected, unknown competency rejected, competency-not-in-selected-stack rejected, and a valid selection passes. (SC-002; FR-003/006)

**Checkpoint**: all four validation rules provably reject their bad inputs and accept valid input.

---

## Phase 4: User Story 2 — Downstream layers build against a committed contract (Priority: P1)

**Goal**: The §14 contract is committed; OpenAPI stays a clean no-op (Variant A).

**Independent Test**: The JSON-schema contract validates a good example and rejects a bad-level example; `openapi --check` is clean with no Position Template paths (no routes added in T12).

### Implementation for User Story 2

- [ ] T008 [US2] Commit the canonical §14 contract to `docs/contracts/position-template.schema.json` (copy of `specs/013-t12-position-template-schema/contracts/position-template.schema.json`; `$id` already points at the `docs/contracts/` path). This is the artefact T13/T14 build against — it lands before any T13/T14 work (§14). (FR-009)
- [ ] T009 [US2] Create `app/backend/tests/contracts/test_position_template_contract.py`: load `docs/contracts/position-template.schema.json`, assert it is a valid Draft 2020-12 schema, validate a good `create` example, reject a `level='Architect'` example. (SC-003; FR-009)
- [ ] T010 [US2] Confirm Variant A: T12 registers **no** routes, so `python -m app.backend.generate_openapi --check` is a clean no-op and `test_openapi_regeneration` stays green unchanged. Record this in the PR description (no code change expected for `openapi.yaml`). (plan §Key design decision; FR-009)

**Checkpoint**: contract committed + provably valid; OpenAPI unchanged (paths deferred to T13).

---

## Phase 5: User Story 3 — Schema change is forward-only and auditable (Priority: P2)

**Goal**: The migration is additive, applies cleanly, and supports soft-delete.

**Independent Test**: Apply `0004` on a clean DB → success to head; rendered SQL contains no destructive DDL; archiving a template sets `archived_at` and preserves the row.

### Implementation for User Story 3

- [ ] T011 [US3] Create `app/backend/tests/db/test_position_template_migration.py` (db profile): assert head == `0004_position_template`; the new columns + association tables exist; the `level` CHECK rejects an invalid value; setting `archived_at` keeps the row (soft-delete, FR-007). Add an assertion (or quickstart-documented grep) that the `0003→0004 --sql` render has no `DROP COLUMN|DROP TABLE|ALTER COLUMN ... TYPE`. (FR-007/010; SC-005)

**Checkpoint**: a `DROP`-free, forward-only migration with soft-delete verified.

---

## Phase 6: Polish & Verification

- [ ] T012 Run the quickstart verification matrix: `alembic upgrade head` → `0004`; all four new test files pass; `generate_openapi --check` clean (no-op); the full `db`-profile suite (138 baseline + new T12 tests) green; `ruff check` + `ruff format --check` + `mypy --strict` clean; destructive-DDL grep over the `0003→0004` SQL render is additive-only. (quickstart.md §A–E)

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (Phase 1)** → T001 (`[P]`, new package files).
- **Foundational (Phase 2)** → T002 (ORM) then T003 (migration); both block the user stories.
- **US1 (Phase 3)** → T004 ∥ T005 (different files; both need T002/T003); T006 needs T004; T007 needs T005 + T003 (db).
- **US2 (Phase 4)** → T008 (contract; shape agreed with T004) → T009 (test needs the committed contract); T010 standalone (no routes).
- **US3 (Phase 5)** → T011 needs T003.
- **Polish (Phase 6)** → T012 after everything.

### Parallel opportunities (file-level, single committer)
- T004 (`schemas/position_template.py`) ∥ T005 (`services/position_template.py`).
- The four test files are independent of one another once their targets exist.
- Never parallel: any two edits to `interview.py` (T002) or to the single migration file (T003).

---

## Implementation Strategy

### MVP first (US1)
1. Foundational (ORM + migration) → US1 (schemas + validator + their tests).
2. **STOP and VALIDATE**: the four validation rules reject bad input and accept valid input on the test stack.

### Incremental delivery
1. Foundational → models + migration exist.
2. US1 → integrity (MVP — the validated entity).
3. US2 → the committed §14 contract (unlocks T13 ∥ T14).
4. US3 → migration safety + soft-delete proven.
5. Polish → full verification matrix + regression.

### Suggested commit grouping (manual commits, our norm)
- `feat(T12): PositionTemplate ORM models + association tables` (T002)
- `feat(T12): 0004_position_template migration (additive)` (T003)
- `feat(T12): Pydantic schemas + DB validator + tests` (T001, T004–T007)
- `feat(T12): position-template.schema.json contract + contract test` (T008–T010)
- `test(T12): migration + soft-delete test; verification matrix` (T011–T012)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- T12 ships no new dependency; the 138-test suite is the regression baseline.
- Variant A: no routes in T12 → `openapi.yaml` is a no-op; Position Template **paths** land in T13. The §14 contract is the JSON schema (T008).
- Migration `0004` is additive only → CI's destructive-DDL gate (T10) expects `needs_adr=false`.
