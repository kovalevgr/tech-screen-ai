---
description: "Task list for the Rubric read endpoint (T14 prerequisite)"
---

# Tasks: Rubric read endpoint

**Input**: Design documents from `specs/016-rubric-read-endpoint/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/endpoints.md, quickstart.md

**Tests**: Integration tests against real Postgres (`docker-compose.test.yml` db profile) — the active tree, the no-active 404, and authz (401/403). Plus the 181-test regression baseline and the OpenAPI drift check.

**Agent / parallelism**: every task is `agent: backend-engineer`, sequential in one PR (§18 — `parallel: false`). No migration, no new schema — reuses T15 `snapshot_rubric` + `RubricSnapshot` and the T13 auth seam.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

No setup — `app/backend/api/`, `services/`, and `tests/api/` already exist (T13/T15).

---

## Phase 2: Foundational

No blocking prerequisites beyond what's merged (T15 `snapshot_rubric`, T13 auth seam).

---

## Phase 3: User Story 1 — Staff tooling can read the current rubric (Priority: P1) 🎯 MVP

**Goal**: `GET /rubric/active` returns the active rubric version's full tree.

**Independent Test**: Seed an active version → 200 + full tree; no active version → 404; recruiter/admin allowed, other → 403, anonymous → 401.

### Implementation for User Story 1

- [ ] T001 [US1] Add `get_active_rubric_snapshot(conn: AsyncConnection) -> RubricSnapshot | None` to `app/backend/services/rubric_snapshot.py`: `SELECT id FROM rubric_tree_version WHERE is_active = true LIMIT 1`; return `None` if no row, else `await snapshot_rubric(conn, active_id)`. (data-model.md; research §2/§5; FR-001/003)
- [ ] T002 [US1] Create `app/backend/api/rubric.py` — `APIRouter(prefix="/rubric", tags=["rubric"])` with `GET /active` (depends on `require_roles("recruiter","admin")` + `SessionDep`; `conn = await session.connection()`; `result = await get_active_rubric_snapshot(conn)`; 404 if `None`, else 200 `RubricSnapshot`). Wire `app.include_router(...)` in `app/backend/main.py`. (data-model.md; research §4; FR-001/004/005)
- [ ] T003 [US1] Create `app/backend/tests/api/test_rubric.py` (db profile; same httpx ASGITransport + savepoint-isolation + auth/seam-override pattern as `test_position_templates.py`): seed a rubric tree with an `is_active` version → `GET /rubric/active` 200 reproduces the tree; no active version → 404; non-privileged role → 403; anonymous → 401. (SC-001/002)

**Checkpoint**: the active rubric is readable over HTTP, gated to recruiter/admin.

---

## Phase 4: Polish & Verification

- [ ] T004 Regenerate `app/backend/openapi.yaml` (`python -m app.backend.generate_openapi`) so it carries `/rubric/active` + the `RubricSnapshot` component family; confirm `--check` + `test_openapi_regeneration` green; commit it (the contract T14 consumes, §14). (FR-006; SC-003)
- [ ] T005 Run the quickstart matrix: endpoint tests pass; full db-profile suite (181 baseline + new) green; `ruff check` + `ruff format --check` + `mypy --strict` clean; `generate_openapi --check` clean. (quickstart.md)

---

## Dependencies & Execution Order

- T001 (helper) → T002 (router needs the helper + main wiring) → T003 (tests need the route).
- T004 (openapi) after the route exists → T005 (verification) last.
- Never parallel: `services/rubric_snapshot.py` (T001), `api/rubric.py` + `main.py` (T002), the single test file (T003).

## Suggested commit grouping (manual commits, our norm)
- `feat: get_active_rubric_snapshot helper` (T001)
- `feat: GET /rubric/active endpoint + tests` (T002–T003)
- `feat: regenerate openapi.yaml with /rubric/active; verification` (T004–T005)

## Notes
- No migration / no new schema — reuses T15 + T13.
- The regenerated `openapi.yaml` is the §14 contract that unblocks T14's TS client.
