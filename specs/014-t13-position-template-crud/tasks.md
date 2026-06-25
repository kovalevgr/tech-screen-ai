---
description: "Task list for T13 — Position Template CRUD endpoints"
---

# Tasks: Position Template CRUD endpoints (T13)

**Input**: Design documents from `specs/014-t13-position-template-crud/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/endpoints.md, quickstart.md

**Tests**: Integration tests against real Postgres (`docker-compose.test.yml` db profile) ARE the deliverable's proof — all five verbs, archived filter, validation→422, authz→401/403, flag-off→404, atomicity. Plus the 159-test regression baseline and the OpenAPI drift check.

**Agent / parallelism**: every task is `agent: backend-engineer`, executed sequentially in one PR (§18 — `parallel: false`). `[P]` marks tasks that touch *different files* with no incomplete dependency; NOT sub-agent fan-out. **No schema change / no migration** (reuses T12 tables + validator). T13's regenerated `openapi.yaml` unblocks T14.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 [P] Create the API package: `app/backend/api/__init__.py` and the test package `app/backend/tests/api/__init__.py`. No new dependency.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The request-scoped DB session, the auth seam, the §9 flag gate, the PATCH schema, and the persistence helpers all underpin the router. They land before any endpoint.

- [ ] T002 Create `app/backend/api/deps.py`: `get_db` (async generator yielding an `AsyncSession` from `db.session.get_sessionmaker()`, commit on success / rollback on exception / always close); `Principal` model + `get_current_user` seam (resolves no identity → raises 401 today; overridable in tests — real SSO is T07); `require_roles(*roles)` (depends on `get_current_user`, raises 403 if role not allowed); `require_crud_enabled` (`await is_enabled("position_template_crud_enabled")` → raise 404 when off). (research §2/§3/§7)
- [ ] T003 [P] Register the §9 flag: add `position_template_crud_enabled` (state `active`, `default: false`, `owner`, `description`) to `configs/feature-flags.yaml`, and add its row to the `docs/engineering/feature-flags.md` index. Pairs with the `is_enabled(...)` call site in T002 so the `feature-flag-registered` hook passes. (research §7)
- [ ] T004 [P] Extend `app/backend/schemas/position_template.py` with `PositionTemplateUpdate` (all fields optional; reuse the stateless validators — dedupe, level enum, and a must-have ⊆ resulting-selected check applied when the relevant lists are present). (data-model.md)
- [ ] T005 Extend `app/backend/services/position_template.py` with persistence helpers callable by the router (single-transaction): `create` (insert template + association rows after `validate_position_template`), `get_one`, `list_templates(include_archived: bool)`, `update` (apply provided fields; replace selection sets wholesale; re-validate), `archive` (set `archived_at`, never delete). Reuse `validate_position_template(await session.connection(), ...)`. (data-model.md; research §1/§4)

**Checkpoint**: deps + flag + schema + service exist; the router can be assembled.

---

## Phase 3: User Story 1 — Create and retrieve a template (Priority: P1) 🎯 MVP

**Goal**: A recruiter can create a validated template and fetch it back.

**Independent Test**: POST a valid body → 201 + stored template; POST invalid bodies → 422, nothing stored; GET by id → 200 round-trip, unknown id → 404.

### Implementation for User Story 1

- [ ] T006 [US1] Create `app/backend/api/position_templates.py` — `APIRouter(prefix="/position-templates", tags=["position-templates"])` with `POST` (create → 201 `PositionTemplateRead`) and `GET /{id}` (read → 200 / 404). All routes depend on `require_crud_enabled` then `require_roles("recruiter","admin")`; map `PositionTemplateValidationError` → 422. Wire `app.include_router(...)` in `app/backend/main.py`. (data-model.md; research §3/§5)
- [ ] T007 [US1] Create `app/backend/tests/api/test_position_templates.py` (db profile, TestClient with `get_current_user` + `require_crud_enabled` overridden to an enabled recruiter): assert create valid → 201 + round-trip; create with bad level / unknown stack / competency-not-in-stack / must-have⊄selected → 422 and no row written; GET one → 200; unknown id → 404. (SC-001/002)

**Checkpoint**: create + read work and reject invalid input.

---

## Phase 4: User Story 2 — List, edit, and archive (Priority: P1)

**Goal**: Lifecycle management with soft-delete; archived excluded by default.

**Independent Test**: list hides archived by default and shows them with `?include_archived=true`; PATCH edits + re-validates; DELETE soft-archives (row preserved, gone from default list).

### Implementation for User Story 2

- [ ] T008 [US2] Add to `app/backend/api/position_templates.py`: `GET /` (list; `include_archived: bool = False` query → `WHERE archived_at IS NULL` unless set), `PATCH /{id}` (partial update via `PositionTemplateUpdate`; replace selection sets wholesale; re-validate; 200 / 422 / 404), `DELETE /{id}` (soft-archive: set `archived_at`, return archived `PositionTemplateRead`; 200 / 404). (data-model.md; research §4)
- [ ] T009 [US2] Extend `tests/api/test_position_templates.py`: list excludes archived by default + includes with `?include_archived=true`; PATCH updates fields + replaces selections + invalid edit → 422 leaves row unchanged; DELETE → `archived_at` set, row still retrievable (include-archived), absent from default list. (SC-003)

**Checkpoint**: full lifecycle; no row is ever removed.

---

## Phase 5: User Story 3 — Authorized staff only (+ flag gate) (Priority: P2)

**Goal**: Only recruiter/admin may use the endpoints; a disabled flag hides them.

**Independent Test**: recruiter/admin → allowed; other role → 403; anonymous → 401; flag off → 404 (before auth).

### Implementation for User Story 3

- [ ] T010 [US3] Extend `tests/api/test_position_templates.py` with authorization + flag cases: with `get_current_user` overridden to a non-privileged role → every verb 403; with no identity (seam default) → 401; with `require_crud_enabled` overridden to "off" → every verb 404 (and 404 wins over auth). (SC-004; §9)

**Checkpoint**: the authz gate and the kill-switch are proven.

---

## Phase 6: Polish & Verification

- [ ] T011 Regenerate the contract: `python -m app.backend.generate_openapi` to write `app/backend/openapi.yaml` with the `/position-templates` paths + component schemas; confirm `generate_openapi --check` and `test_openapi_regeneration` are green; commit the regenerated `openapi.yaml` (this is the artefact T14 consumes; §14). (FR-009; SC-005)
- [ ] T012 Run the quickstart verification matrix: full db-profile suite (159 baseline + new T13 tests) green; `ruff check` + `ruff format --check` + `mypy --strict` clean; `generate_openapi --check` clean. (quickstart.md §A–C)

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (Phase 1)** → T001 (`[P]`, package files).
- **Foundational (Phase 2)** → T002 (deps) ∥ T003 (flag YAML/docs) ∥ T004 (update schema) ∥ T005 (service) — different files; all block the router. (T002's `is_enabled` call site + T003's YAML entry must land together for the registration hook.)
- **US1 (Phase 3)** → T006 (router POST/GET + main wiring; needs T002 + T005) → T007 (tests).
- **US2 (Phase 4)** → T008 (same router file, after T006; needs T004 + T005) → T009 (tests).
- **US3 (Phase 5)** → T010 (tests; needs the endpoints + T002 deps).
- **Polish (Phase 6)** → T011 (openapi, after all routes) → T012 (verification).

### Parallel opportunities (file-level, single committer)
- T002 ∥ T003 ∥ T004 ∥ T005 (deps.py / feature-flags.yaml+md / schemas / services — distinct files).
- Never parallel: edits to `api/position_templates.py` (T006→T008), to `tests/api/test_position_templates.py` (T007→T009→T010), or to `main.py` (T006).

---

## Implementation Strategy

### MVP first (US1)
1. Foundational (deps + flag + schema + service) → US1 (create + read + tests).
2. **STOP and VALIDATE**: create/read work on the test stack; invalid input rejected.

### Incremental delivery
1. Foundational → seams + persistence exist.
2. US1 → create + read (MVP).
3. US2 → list + edit + archive (soft-delete).
4. US3 → authz + flag-gate proven.
5. Polish → regenerate `openapi.yaml` (unblocks T14) + full regression.

### Suggested commit grouping (manual commits, our norm)
- `feat(T13): API deps (get_db, auth seam, role + feature-flag gates) + flag registration` (T001–T003)
- `feat(T13): PositionTemplateUpdate schema + service persistence helpers` (T004–T005)
- `feat(T13): create + read endpoints + tests` (T006–T007)
- `feat(T13): list + edit + soft-delete endpoints + tests` (T008–T009)
- `test(T13): authorization + feature-flag gate cases` (T010)
- `feat(T13): regenerate openapi.yaml with position-template paths; verification` (T011–T012)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- No schema change / no migration — reuses T12 tables + `validate_position_template`.
- Auth is a seam (overridable `get_current_user`); real Identity Platform wiring is T07 (GCP-blocked).
- The §9 flag `position_template_crud_enabled` defaults false (dark); `is_enabled` falls back to the YAML default until an operator flips the DB row.
- The regenerated `openapi.yaml` completes T12's Variant A and is the contract T14 builds against (§14).
