# Implementation Plan: Position Template schema + contract (T12)

**Branch**: `013-t12-position-template-schema` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/013-t12-position-template-schema/spec.md`

## Summary

Extend the existing T05 `position_template` placeholder into a fully-defined,
validated entity and publish its committed contract so the downstream CRUD
(T13) and admin UI (T14) tasks can fan out in parallel (§14). Deliverables:
a SQLAlchemy model + association tables + a forward-only additive Alembic
migration (`0004_position_template`); Pydantic request/response schemas with
stateless validation; a DB-backed validator for the stateful rules; the
committed JSON-schema contract `docs/contracts/position-template.schema.json`;
and tests. No HTTP endpoints (T13) and no UI (T14) — schema + contract only.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: SQLAlchemy 2.x (async), Alembic, Pydantic v2, FastAPI (for OpenAPI regen only — no new routes here)
**Storage**: PostgreSQL 17 (pgvector image); rubric tree + `position_template` placeholder already present
**Testing**: pytest in the `docker-compose.test.yml` `db`-profile stack (real Postgres); 138-test baseline must stay green
**Target Platform**: Linux container (Cloud Run in prod; Docker parity in dev/CI, §7)
**Project Type**: Web service (backend only for this task)
**Performance Goals**: N/A (schema/validation task; no runtime hot path)
**Constraints**: Forward-only, zero-downtime, additive DDL only (§10); no destructive DDL; append-only invariants untouched (§3)
**Scale/Scope**: One table extended + two association tables + one migration + Pydantic schemas + one validator + one JSON-schema contract

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 (below).*

| Principle | Relevance | Verdict |
| --- | --- | --- |
| §3 Append-only audit trail | `position_template` is **not** an append-only table — it's recruiter-editable config. Normal UPDATEs are allowed; no audit table is touched. | ✅ Pass |
| §4 Immutable rubric snapshot | A template references rubric `stack`/`competency` by id; it does **not** snapshot them. Snapshotting onto a session is T15. Editing a template never mutates a past session. | ✅ Pass (T15 owns the freeze) |
| §10 Migration approval / forward-only | `0004` is additive only (ADD COLUMN, CREATE TABLE, ADD CONSTRAINT). No DROP/type-narrowing. T10's CI renders the SQL + runs the destructive-DDL detector → expected `needs_adr=false`. | ✅ Pass (no ADR needed) |
| §14 Contract-first | This task **is** the contract task. `docs/contracts/position-template.schema.json` is committed here, unblocking T13/T14 parallel work. §14 accepts "OpenAPI **or** JSON schema"; the JSON schema is the chosen artefact. | ✅ Pass |
| §16 Configs as code | Position templates are named in §16 as Git-promoted configs. T12 lands the **runtime DB table**; the export-to-Git + drift-checker mechanism is a property of the Admin UI tier (T14+), **not** T12. Flagged, not violated. | ✅ Pass (deferred mechanism noted) |
| §17 Specs precede implementation | Spec-kit flow in use; spec committed (`2ca00b5`). | ✅ Pass |
| §18 Multi-agent explicit | T12 is single-agent (`backend-engineer`), `parallel: false`. It **unlocks** the T13 ∥ T14 fan-out by publishing the contract; no fan-out happens *within* T12. | ✅ Pass |
| §15 PII containment | A position template holds role definitions, no candidate PII. | ✅ Pass |

**No violations → Complexity Tracking left empty.**

### Key design decision (surface at the gate)

**The §14 contract is the JSON schema, not OpenAPI paths.** FastAPI generates
`openapi.yaml` from *registered routes*. T12 adds **no routes** (those are T13),
so regenerating `openapi.yaml` here is a **no-op / no-drift** — the
`test_openapi_regeneration` check stays green with no change. The committed,
reviewable contract that T13/T14 build against is
`docs/contracts/position-template.schema.json` (request/response JSON shapes +
validation rules). The Position Template **paths** land in `openapi.yaml` in
T13 when the endpoints exist.

> This deviates from the implementation-plan wording ("regenerate `openapi.yaml`
> with Position Template endpoints in the same PR"), but satisfies the
> constitution (§14 accepts a JSON schema) and keeps the T12/T13 boundary clean
> — no stub routes. *Alternative considered:* register read-only endpoint stubs
> in T12 so the OpenAPI paths appear now (Option B in research.md §2). Rejected
> as scope-bleed into T13. **If the user prefers Option B, adjust in tasks.**

## Project Structure

### Documentation (this feature)

```text
specs/013-t12-position-template-schema/
├── spec.md              # committed (2ca00b5)
├── plan.md              # this file
├── research.md          # Phase 0 — decisions
├── data-model.md        # Phase 1 — tables, columns, constraints, rules
├── quickstart.md        # Phase 1 — how to verify T12
├── contracts/
│   └── position-template.schema.json   # design copy; canonical lands at docs/contracts/
└── tasks.md             # created by speckit-tasks (next gate)
```

### Source Code (repository root)

```text
app/backend/
├── db/models/
│   └── interview.py          # EXTEND PositionTemplate; ADD PositionTemplateStack, PositionTemplateCompetency
├── schemas/                  # NEW package — boundary (Pydantic) request/response models
│   ├── __init__.py
│   └── position_template.py  # PositionTemplateCreate / PositionTemplateRead + stateless validators
├── services/                 # NEW package — domain logic callable by future endpoints
│   ├── __init__.py
│   └── position_template.py  # validate_position_template(session, payload): stateful (DB) rules
└── tests/
    ├── db/test_position_template_migration.py     # migration applies; additive DDL; soft-delete
    ├── schemas/test_position_template_schema.py   # stateless rules (level enum, ⊆, ≥1, dedupe)
    ├── services/test_position_template_validate.py# stateful rules (stack exists, belongs-to-stack)
    └── contracts/test_position_template_contract.py # JSON schema validates good / rejects bad

alembic/versions/
└── 0004_position_template.py  # NEW — additive: ALTER position_template + CREATE 2 assoc tables

docs/contracts/
└── position-template.schema.json  # NEW — canonical committed §14 contract
```

**Structure Decision**: Backend-only change. Introduce two small new packages
(`app/backend/schemas/`, `app/backend/services/`) because no boundary/service
layer exists yet and T13 will build directly on them. ORM models extend the
existing `interview.py` (where `PositionTemplate` already lives as a placeholder).

## Phase 0 — Research

See [research.md](./research.md). Resolves: level representation (TEXT+CHECK vs
PG enum), the OpenAPI-vs-JSON-schema contract strategy, additive-migration
safety on an existing table, association tables vs JSON columns, where stateful
validation lives given there are no endpoints yet, and the Pydantic v2 patterns.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — the extended `position_template`, the two
  association tables, all columns/constraints, and the four validation rules
  mapped to FRs.
- [contracts/position-template.schema.json](./contracts/position-template.schema.json)
  — design copy of the §14 JSON-schema contract; the canonical file is committed
  to `docs/contracts/` during implement.
- [quickstart.md](./quickstart.md) — the verification matrix (migration apply,
  the four validation tests, JSON-schema contract test, `openapi --check` no-op).
- **Agent context**: `CLAUDE.md` has no `<!-- SPECKIT -->` markers (hand-maintained) — agent-context injection skipped intentionally.

## Phase 2 — Task planning approach (preview, not executed here)

`speckit-tasks` will produce an ordered, single-agent (`backend-engineer`,
`parallel: false`) task list, roughly: (1) ORM models + association tables;
(2) migration `0004` + migration test; (3) Pydantic schemas + stateless-rule
tests; (4) DB-backed validator + stateful-rule tests; (5) JSON-schema contract
+ contract test; (6) `openapi --check` no-op confirmation + full-suite
regression. Contract (step 5) is committed before any T13/T14 work begins (§14).

## Complexity Tracking

*No constitution violations — section intentionally empty.*
