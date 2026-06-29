# Implementation Plan: Rubric read endpoint

**Branch**: `016-rubric-read-endpoint` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/016-rubric-read-endpoint/spec.md`

## Summary

Add `GET /rubric/active` — a read-only endpoint returning the active rubric
version's full tree, reusing T15's `snapshot_rubric` and the committed
`rubric-snapshot.schema.json` shape. Unblocks T14 (the admin form needs to list
stacks/competencies). recruiter/admin auth (T13 seam), 404 when no active
version, OpenAPI regenerated. **No migration, no new schema.**

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async, Pydantic v2
**Storage**: PostgreSQL 17 — existing rubric tree (T08); `rubric_tree_version.is_active`
**Testing**: pytest in the `docker-compose.test.yml` db-profile stack; 181-test baseline stays green
**Project Type**: Web service (backend only)
**Constraints**: read-only; contract no-drift (§14); reuse T15 + T13 (no new shape, no migration)
**Scale/Scope**: one router + one service helper + tests; reuse everything else

## Constitution Check

| Principle | Relevance | Verdict |
| --- | --- | --- |
| §3 Append-only | Read-only endpoint; touches no audit table. | ✅ Pass |
| §4 Snapshot | Reuses the snapshot *shape*; reads the live active version (not a session). Doesn't affect §4. | ✅ Pass |
| §9 Dark-launch | Read-only view of internal config (low risk) → **no feature flag** (justified). | ✅ Pass (no flag) |
| §14 Contract-first | OpenAPI regenerated with the path; response reuses the committed `rubric-snapshot.schema.json`. T14 builds its client from it. | ✅ Pass |
| §15 PII | Rubric structure, no candidate PII. | ✅ Pass |
| §17 / §18 | Spec-kit; single-agent (`backend-engineer`, `parallel: false`). | ✅ Pass |
| §10 Migration | None. | ✅ N/A |

**No violations → Complexity Tracking empty.**

## Project Structure

```text
specs/016-rubric-read-endpoint/
├── spec.md  plan.md  research.md  data-model.md  quickstart.md
└── contracts/endpoints.md   # GET /rubric/active (design ref; live contract = openapi.yaml + rubric-snapshot.schema.json)

app/backend/
├── api/rubric.py                 # NEW — APIRouter GET /rubric/active
├── services/rubric_snapshot.py   # EXTEND — get_active_rubric_snapshot(conn) -> RubricSnapshot | None
├── main.py                       # EDIT — include_router(rubric_router)
├── openapi.yaml                  # REGENERATE — + /rubric/active + RubricSnapshot components
└── tests/api/test_rubric.py      # NEW — active tree, 404 no-active, authz 401/403
```

**Structure Decision**: A second small router in `app/backend/api/`. The
endpoint resolves the active version + snapshots it via a new service helper, so
the router stays thin; data access stays on `AsyncConnection` (via
`session.connection()`) to reuse the T15 `snapshot_rubric`.

## Phase 0 — Research

See [research.md](./research.md). Resolves: reuse of `snapshot_rubric` +
`RubricSnapshot` as the response (no new shape); active-version selection
(`is_active`); no §9 flag; auth-seam reuse; the `get_active_rubric_snapshot`
helper (None → 404); OpenAPI regenerate.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — no new entities; the helper + endpoint flow.
- [contracts/endpoints.md](./contracts/endpoints.md) — `GET /rubric/active` (status codes); the committed contract is the regenerated `openapi.yaml` + the existing `docs/contracts/rubric-snapshot.schema.json`.
- [quickstart.md](./quickstart.md) — verification matrix.
- **Agent context**: `CLAUDE.md` has no `<!-- SPECKIT -->` markers — injection skipped.

## Phase 2 — Task planning approach (preview)

`speckit-tasks` will produce a single-agent (`backend-engineer`, `parallel: false`)
list: (1) `get_active_rubric_snapshot` helper; (2) the `GET /rubric/active` router
+ main wiring; (3) integration tests; (4) regenerate `openapi.yaml`; (5)
verification. The regenerated contract is committed in the same PR (§14) for T14.

## Complexity Tracking

*No constitution violations — section intentionally empty.*
