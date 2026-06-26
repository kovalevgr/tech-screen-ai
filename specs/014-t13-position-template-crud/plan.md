# Implementation Plan: Position Template CRUD endpoints (T13)

**Branch**: `014-t13-position-template-crud` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/014-t13-position-template-crud/spec.md`

## Summary

Expose T12's Position Template entity over HTTP: `POST/GET(list)/GET(one)/PATCH/DELETE
/position-templates`, with soft-delete (archived excluded by default,
`?include_archived=true`), recruiter/admin authorization via an overridable
dependency seam, atomic persistence, and the OpenAPI contract regenerated with
the new paths (completing T12's Variant A). Reuses T12's ORM models, Pydantic
schemas, and `validate_position_template`; **no schema change, no migration**.
This is the backend's first APIRouter and first request-scoped DB-session
dependency.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: FastAPI, SQLAlchemy 2.x async (AsyncSession), Pydantic v2
**Storage**: PostgreSQL 17 — existing tables from T12 (`position_template` + 2 association tables); migration head `0004_position_template`
**Testing**: pytest + FastAPI TestClient against the `docker-compose.test.yml` db-profile stack (real Postgres); 159-test baseline stays green
**Target Platform**: Linux container (Cloud Run in prod; Docker parity dev/CI, §7)
**Project Type**: Web service (backend only for this task)
**Performance Goals**: N/A (internal admin CRUD; no hot path, no LLM calls)
**Constraints**: Soft-delete only (§3 spirit / FR-007); contract must not drift (§14); auth real-wiring deferred to T07 (GCP-blocked)
**Scale/Scope**: 5 operations on one entity; one router, one get_db dep, one auth seam, no new schema

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 (below).*

| Principle | Relevance | Verdict |
| --- | --- | --- |
| §3 Append-only | `position_template` is not an append-only table; PATCH (UPDATE) is allowed and DELETE is a soft archive (`archived_at`) — **no row is ever removed**. | ✅ Pass |
| §9 Dark-launch | Ships behind a feature flag **`position_template_crud_enabled` (default `false`)**: a `require_crud_enabled` dependency returns 404 when off. Independent of auth (kill-switch). No migration — `is_enabled` falls back to the YAML default (false) until an operator flips the DB row (sync/SQL). | ✅ Pass (flag added) |
| §14 Contract-first | T13 regenerates `app/backend/openapi.yaml` with the `/position-templates` paths; the request/response shapes were frozen by T12's JSON schema. T14 (frontend, parallel) generates its client from this. | ✅ Pass |
| §15 PII | A Position Template holds role config, no candidate PII. | ✅ Pass |
| §17 / §18 | Spec-kit flow; single-agent (`backend-engineer`, `parallel: false`). | ✅ Pass |
| §10 Migrations | No schema change → no migration. | ✅ N/A |
| Auth (T07) | Real SSO + role claims are T07 (GCP-blocked). T13 builds an **overridable** `get_current_user` seam + role check; default is 401 until T07 wires the provider — safe (the surface is dark until auth exists). | ✅ Pass (seam documented) |

**No violations → Complexity Tracking empty.**

## Project Structure

### Documentation (this feature)

```text
specs/014-t13-position-template-crud/
├── spec.md            # committed (ff59950)
├── plan.md            # this file
├── research.md        # Phase 0 — decisions
├── data-model.md      # Phase 1 — shapes/flows (reuses T12 tables; adds PositionTemplateUpdate)
├── quickstart.md      # Phase 1 — verification matrix
├── contracts/
│   └── endpoints.md   # the 5 operations + status codes (design ref; live contract = openapi.yaml)
└── tasks.md           # speckit-tasks (next gate)
```

### Source Code (repository root)

```text
app/backend/
├── api/                          # NEW package — first HTTP routers
│   ├── __init__.py
│   ├── deps.py                   # get_db (AsyncSession) + get_current_user seam + require_roles + require_crud_enabled (§9 flag)
│   └── position_templates.py     # APIRouter: POST/GET list/GET one/PATCH/DELETE
├── schemas/position_template.py  # EXTEND — add PositionTemplateUpdate (all-optional PATCH body)
├── services/position_template.py # EXTEND — add create/get/list/update/archive persistence (reuse validate_position_template)
├── main.py                       # EDIT — include_router(position_templates.router)
├── openapi.yaml                  # REGENERATE — now carries the /position-templates paths
└── tests/api/
    ├── __init__.py
    └── test_position_templates.py  # integration: 5 verbs, archived filter, 422/403/401/404, flag-off→404, atomicity

configs/feature-flags.yaml                     # ADD position_template_crud_enabled (state active, default false)
docs/engineering/feature-flags.md              # ADD the flag to the human-readable index
docs/contracts/position-template.schema.json   # unchanged (T12) — shapes already frozen
```

**Structure Decision**: Introduce `app/backend/api/` (first router package) and a
request-scoped `get_db` dependency built on the existing `db/session.py`
sessionmaker. Persistence logic lives in `services/position_template.py` (next to
the T12 validator) so the router stays thin and the logic is unit-testable.

## Phase 0 — Research

See [research.md](./research.md). Resolves: AsyncSession + ORM persistence (and how
the AsyncConnection-based T12 validator is invoked from a session); the auth seam
shape (get_current_user default-401, overridable; require_roles → 403); router/
get_db wiring; PATCH partial-update + selection-replace semantics; error→status
mapping; and the OpenAPI regenerate-then-check flow.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — reuses T12 tables; adds the `PositionTemplateUpdate` boundary model + the auth principal; documents the create/read/list/update/archive flows and the transaction boundary.
- [contracts/endpoints.md](./contracts/endpoints.md) — the five operations, query params, and status codes (design reference; the committed contract is the regenerated `app/backend/openapi.yaml` + T12's `docs/contracts/position-template.schema.json`).
- [quickstart.md](./quickstart.md) — verification matrix (endpoint tests, openapi regenerate+check, full suite, lint/types).
- **Agent context**: `CLAUDE.md` has no `<!-- SPECKIT -->` markers — injection skipped intentionally.

## Phase 2 — Task planning approach (preview, not executed here)

`speckit-tasks` will produce a single-agent (`backend-engineer`, `parallel: false`)
list: (1) get_db + auth seam deps; (2) PositionTemplateUpdate schema; (3) service
persistence helpers; (4) the router + main wiring; (5) regenerate openapi.yaml;
(6) integration tests; (7) verification matrix + regression. The regenerated
`openapi.yaml` is committed in the same PR (§14) so T14 can fan out.

## Complexity Tracking

*No constitution violations — section intentionally empty.*
