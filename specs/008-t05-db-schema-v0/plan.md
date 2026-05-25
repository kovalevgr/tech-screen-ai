# Implementation Plan: DB schema v0 + Alembic baseline + append-only enforcement (T05)

**Branch**: `008-t05-db-schema-v0` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/008-t05-db-schema-v0/spec.md`

## Summary

T05 lays the **database foundation** the whole product sits on. In one PR it introduces SQLAlchemy + Alembic to the backend (neither exists yet) and ships the baseline migration `alembic/versions/0001_baseline.py` plus the SQLAlchemy 2.x models under `app/backend/db/models/`, in the order a reviewer should validate them:

1. **Tooling.** `sqlalchemy[asyncio]`, `alembic`, and the `asyncpg` driver are added to `pyproject.toml`; `uv.lock` is regenerated. An async-aware `alembic/env.py` + `alembic.ini` + `script.py.mako` are added. The backend gains `app/backend/db/` (declarative base + async engine/session factory).
2. **Schema.** The baseline migration creates the `vector` and `pgcrypto` extensions, the **rubric read-only tree** (`rubric_tree_version`, `stack`, `competency_block`, `competency`, `topic`, `level`), `user`, the **session placeholders** (`position_template`, `interview_session`, `interview_plan`), and the **six §3 append-only tables** (`turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`).
3. **§3 enforcement (the heart of T05).** Two independent layers: a shared trigger function `reject_audit_mutation()` wired as a `BEFORE UPDATE OR DELETE` trigger on all six tables (raising `append-only: <op> not allowed on <table>`), **and** `REVOKE UPDATE, DELETE` on those tables from the `techscreen_app` role. The trigger exempts `techscreen_migrator` via a `current_user` check so human-approved forward-only migrations can still evolve audit data (§10).
4. **Roles.** The migration idempotently creates `techscreen_app` and `techscreen_migrator` (`NOLOGIN`, guarded `DO` block) so the §3 guardrail and its tests run standalone now; T06 later attaches `LOGIN` + a Secret-Manager password.
5. **Tests.** Integration tests under `app/backend/tests/db/` prove the migration round-trip (up → down → up), the rubric-tree relationships, role existence + grant shape, and — the core — the §3 invariant on every one of the six tables, isolating each enforcement layer.
6. **Docker parity fix.** `docker-compose.test.yml`'s Postgres image moves from `postgres:16-bookworm` to `pgvector/pgvector:pg17` (matches dev; required so `CREATE EXTENSION vector` succeeds in CI — §7), and the `alembic upgrade head` step the T02 file left as `# TODO(T05)` is re-enabled.
7. **Documentation-fix slice.** `docs/engineering/implementation-plan.md` T05 entry's "ADR-008" pgvector reference is corrected to **ADR-007** (ADR-008 is hybrid prompt language). `README.md` gains a DB dev-loop subsection.

The PR adds **no** HTTP endpoint, **no** OpenAPI diff (the T02 regen-and-diff guardrail must stay byte-identical), **no** content under `prompts/` or `configs/rubric/`, and **no** write-side application code for the audit tables (that lands in T18–T21 / T35). It is a single-committer PR — `agent: backend-engineer`, `parallel: false`. The parallel fan-out it unblocks (T05a, T06, T08) happens *after* T05 merges.

## Technical Context

**Language/Version**: Python 3.12 (unchanged; `pyproject.toml` pins `>=3.12,<3.13`).

**Primary Dependencies** (added to `[project].dependencies`):

- `sqlalchemy[asyncio] >= 2.0, < 2.1` — ORM + Core. 2.x typed `Mapped[]` style (the project is greenfield; no 1.x legacy). The `[asyncio]` extra pulls the async engine support used by the app runtime.
- `alembic >= 1.13, < 2` — migrations. Async-aware `env.py` (Research §1).
- `asyncpg >= 0.30, < 0.31` — the async PostgreSQL driver. The DSN already wired into both compose files is `postgresql+asyncpg://…`, so the driver choice is **already a committed contract** — T05 only makes it real. A single driver (asyncpg) serves both the app runtime and Alembic (via `run_sync` inside an async `env.py`), so no second sync driver (`psycopg`) is added — Research §1.

No `pgvector` **Python** package is added: T05 only `CREATE EXTENSION vector` (so later embedding work needs no destructive migration) but creates **no** `vector(…)` column yet (`annotated_turn_embedding` is deferred per spec Clarifications). Adding the Python binding now would be an unused dependency.

**Dev dependencies**: none new. `pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`, already configured in T04) cover the async DB integration tests.

**Storage**: PostgreSQL 17 with the `pgvector` and `pgcrypto` extensions. Dev: `pgvector/pgvector:pg17` (already in `docker-compose.yml`). CI/test: same image after this PR's parity fix. Prod: Cloud SQL PG17 (provisioned in T06).

**Testing**: `pytest` + `pytest-asyncio`. New integration tests under `app/backend/tests/db/` require a live Postgres and are **gated**: they `pytest.skip` when no test database is reachable (Research §9), so the existing no-DB unit run (`docker compose -f docker-compose.test.yml run --rm backend pytest`) stays green, and the DB suite runs under `--profile db` (locally and in CI/T10).

**Target Platform**: Linux container (the existing `dev` Docker target carries all tooling). Migrations run via `alembic upgrade head`.

**Project Type**: Backend data-layer slice within the existing FastAPI monorepo. No frontend, no infra/Terraform changes (Cloud SQL provisioning is T06).

**Performance Goals**:

- `alembic upgrade head` on an empty database completes in < 5 s locally (single migration).
- The DB integration suite completes in < 30 s locally on the `db` profile (the §3 matrix is a set of small transactional probes).
- No production query-latency target in scope — T05 creates schema, not query paths.

**Constraints**:

- **§3 append-only** — enforced at the database, two layers (trigger + revoke). Application code that issues `UPDATE`/`DELETE` on the six tables cannot exist (FR-004/005). This is the task's reason to exist.
- **§10 forward-only, zero-downtime** — the baseline is additive only. `downgrade()` exists for local/CI resets (FR-002/011); it does not soften the production forward-only posture. No destructive DDL → no extra ADR required.
- **§15 PII containment** — `audit_log` carries only `actor_id`, `action`, `subject_hash`, `ts`. No table created by T05 stores candidate PII; the candidate-PII tables (`candidate`, `message`, `turn` per §15) are introduced by Tier 5.
- **§4 immutable rubric snapshots** — the rubric tree is versioned by `rubric_tree_version`; T05 encodes the version linkage now (ADR-018). The `interview_session.rubric_snapshot NOT NULL` column itself is owned by T15, deferred per spec Clarifications.
- **§7 Docker parity** — the test Postgres image must equal the dev image; this PR fixes the existing pg16/pg17 drift.
- **§16 configs as code** — no rubric *content* in T05 (that is T08's importer); only the empty tree tables.
- **No OpenAPI diff** — the T02 `python -m app.backend.generate_openapi` regen-and-diff guardrail stays byte-identical (no routes added).
- **Pre-commit guardrails from T01–T04** (`gitleaks`, `detect-secrets`, `ruff`, `ruff-format`, `actionlint`, `check-yaml`, `check-toml`, `no-provider-sdk-imports`) all pass on every new file. `mypy --strict app/backend` stays clean — SQLAlchemy 2.x `Mapped[]` models are fully typed.

**Scale/Scope**: Single PR, ≈ 22 files (≈ 600 LOC models + migration, ≈ 400 LOC tests, alembic scaffolding, two compose/doc edits). One committer (`agent: backend-engineer`), `parallel: false`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| §   | Principle                              | Applies to T05?                                                                                                                                                                              | Status |
| --- | -------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first    | Directly — the append-only schema *is* the substrate of every later auditability claim. T05 makes mutation of audit history physically impossible.                                            | Pass   |
| 2   | Deterministic orchestration            | Indirect — provides the `turn_trace` table the orchestrator (T20) logs typed routing fields into. No control flow in T05.                                                                     | Pass   |
| 3   | Append-only audit trail                | **Primary purpose.** Trigger + `REVOKE UPDATE, DELETE` on all six tables for `techscreen_app`; corrections-as-new-rows shape encoded (`assessment_correction.assessment_id` FK). ADR-019.     | Pass   |
| 4   | Immutable rubric snapshots             | Yes — rubric tree versioned by `rubric_tree_version` (ADR-018). `rubric_snapshot NOT NULL` column deferred to its owner T15 (spec Clarifications), no conflict.                               | Pass   |
| 5   | No plaintext secrets                   | Yes — no secret added. `DATABASE_URL` is already an (empty) key in `.env.example`; the dev/test passwords (`techscreen`) live only in compose files and are non-secret local defaults.        | Pass   |
| 6   | Workload Identity Federation only      | N/A at T05 — no GCP auth. Role passwords for prod come from Secret Manager in T06; T05 roles are `NOLOGIN`.                                                                                    | N/A    |
| 7   | Docker parity dev → CI → prod          | Yes — this PR **fixes** an existing drift (test pg16 → pg17 + pgvector) so `CREATE EXTENSION vector` runs identically dev/CI/prod.                                                             | Pass   |
| 8   | Production-only topology               | N/A — no environment created. Cloud SQL is T06.                                                                                                                                              | N/A    |
| 9   | Dark launch by default                 | N/A — schema creation is not a user-visible feature and carries no runtime behaviour to flag. (The `feature_flag` table itself is T05a.)                                                      | N/A    |
| 10  | Migration approval                     | Yes — the baseline is additive, reversible, forward-only. The CI `--sql` dry-run + `migration-approved` label *mechanism* is T10; T05 ships a migration that will pass it (raw SQL renders offline). | Pass   |
| 11  | Hybrid language                        | Yes — all DDL comments, model docstrings, trigger messages are English. No candidate-facing text in T05.                                                                                      | Pass   |
| 12  | LLM cost and latency caps              | N/A — no LLM call in T05. (`turn_trace.cost_usd` column is created for T21 to write.)                                                                                                         | N/A    |
| 13  | Calibration never blocks merge         | N/A — no calibration.                                                                                                                                                                        | N/A    |
| 14  | Contract-first for parallel work       | Yes — the schema contract (`contracts/schema-contract.md` + the migration itself) is committed before T05a/T06/T08 fan out against it. T05 itself is single-committer.                         | Pass   |
| 15  | PII containment                        | Yes — `audit_log` limited to `actor_id`/`action`/`subject_hash`/`ts`; no candidate-PII column in any T05 table; PII tables deferred to Tier 5.                                                | Pass   |
| 16  | Configs as code                        | Yes — rubric *content* stays in `configs/` (loaded by T08); T05 creates only empty tree tables. No drift introduced.                                                                          | Pass   |
| 17  | Specifications precede implementation  | Yes — `speckit-specify` → this `speckit-plan`; implementation follows `speckit-tasks`.                                                                                                        | Pass   |
| 18  | Multi-agent orchestration is explicit  | Yes — `agent: backend-engineer`, `parallel: false`. Fan-out (T05a/T06/T08) is post-merge.                                                                                                    | Pass   |
| 19  | Rollback is a first-class operation    | Yes — additive migration; `git revert` + (if applied to a throwaway) `alembic downgrade base` both work. No prod state until T06.                                                             | Pass   |
| 20  | Floor, not ceiling                     | Pass.                                                                                                                                                                                        | Pass   |

**Gate result**: PASS. No violations. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/008-t05-db-schema-v0/
├── spec.md                    # Feature spec (speckit-specify)
├── plan.md                    # This file
├── research.md                # Phase 0 — design-altitude decisions
├── data-model.md              # Phase 1 — tables, columns, relationships, lifecycle
├── contracts/
│   └── schema-contract.md     # Phase 1 — DDL/role/trigger/grant contract downstream tasks depend on
├── quickstart.md              # Phase 1 — reviewer validation walkthrough
├── checklists/
│   └── requirements.md        # From speckit-specify (passed)
└── tasks.md                   # Created by speckit-tasks (NOT this command)
```

### Source Code (repository root, after T05 merges)

```text
.
├── alembic.ini                                   # NEW — Alembic config; script_location = alembic; URL from env
├── alembic/
│   ├── env.py                                    # NEW — async env (asyncpg + run_sync); target_metadata = Base.metadata
│   ├── script.py.mako                            # NEW — migration template
│   └── versions/
│       └── 0001_baseline.py                      # NEW — THE CONTRACT: extensions, roles, all tables, triggers, revoke/grant
├── app/
│   └── backend/
│       ├── settings.py                           # EDITED — add `database_url` field (read from DATABASE_URL)
│       ├── db/
│       │   ├── __init__.py                        # NEW — package marker
│       │   ├── base.py                            # NEW — DeclarativeBase + MetaData naming convention (constraint/index names)
│       │   ├── session.py                         # NEW — async engine + async_sessionmaker factory (runtime, not migrations)
│       │   └── models/
│       │       ├── __init__.py                    # NEW — imports all models so Base.metadata is complete for Alembic autogen
│       │       ├── _mixins.py                     # NEW — UUIDPk mixin (gen_random_uuid server default), TimestampCreated mixin
│       │       ├── rubric.py                      # NEW — rubric_tree_version, stack, competency_block, competency, topic, level
│       │       ├── identity.py                    # NEW — user
│       │       ├── interview.py                   # NEW — position_template, interview_session, interview_plan (placeholders)
│       │       └── audit.py                       # NEW — the six §3 append-only tables
│       └── tests/
│           ├── conftest.py                        # EDITED — add db fixtures: db_available guard, async engine, migrated schema, set_role helper
│           └── db/
│               ├── __init__.py                    # NEW — package marker
│               ├── test_baseline_migration.py     # NEW — upgrade head; objects exist; downgrade base empties; second upgrade idempotent
│               ├── test_rubric_tree.py            # NEW — parent/child FKs + rubric_tree_version linkage; transactional insert/rollback (US3 + US2 #4)
│               ├── test_roles.py                  # NEW — both roles exist; app role lacks UPDATE/DELETE but has INSERT/SELECT on the six tables
│               └── test_append_only.py            # NEW — the §3 matrix: per-table app-role UPDATE+DELETE rejected (12 asserts); trigger layer (superuser); migrator-exempt path
├── docker-compose.test.yml                       # EDITED — postgres image postgres:16-bookworm → pgvector/pgvector:pg17; re-enable `alembic upgrade head`
├── docker-compose.yml                            # EDITED (doc-comment only) — note the `--profile db` migrate command; image already pgvector/pgvector:pg17
├── docs/engineering/implementation-plan.md       # EDITED — T05 entry: pgvector ADR-008 → ADR-007 typo fix
├── README.md                                     # EDITED — "Database dev loop" subsection (migrate up/down, run db tests)
├── pyproject.toml                                # EDITED — add sqlalchemy[asyncio], alembic, asyncpg to [project].dependencies
├── uv.lock                                        # EDITED — regenerated by `uv lock`
└── (every other path untouched)
```

**Structure Decision**: A new `app/backend/db/` package holds the declarative base (`base.py`), the async runtime engine/session factory (`session.py`, used by app code in later tiers — not by migrations), and the typed models split by domain (`rubric.py`, `identity.py`, `interview.py`, `audit.py`). Alembic lives at the repo root (`alembic.ini` + `alembic/`) following its convention and the existing `.gitkeep` placeholder. The single baseline migration `0001_baseline.py` is the load-bearing artefact and the task's **contract**; the SQLAlchemy models give `mypy --strict` coverage and feed future `--autogenerate`, but the baseline's structural SQL (extensions, roles, triggers, `REVOKE`/`GRANT`) is hand-authored because Alembic autogenerate does not emit roles, triggers, or grants.

### Task labelling (for §18 / speckit-tasks)

| Task slice                                                  | Agent              | Parallel? | Depends on                              | Contract reference                         |
| ---------------------------------------------------------- | ------------------ | --------- | --------------------------------------- | ------------------------------------------ |
| `pyproject.toml` deps + `uv lock`                          | `backend-engineer` | false     | T01 (`pyproject.toml` exists)           | `schema-contract.md` §0 (dependency budget) |
| `app/backend/db/base.py` + `_mixins.py` + `session.py`     | `backend-engineer` | false     | deps installed                          | `data-model.md` §Base                       |
| Models: `rubric.py`, `identity.py`, `interview.py`         | `backend-engineer` | false     | base + mixins                           | `data-model.md` §Rubric/§Identity/§Session  |
| Models: `audit.py` (six append-only tables)                | `backend-engineer` | false     | base + mixins + interview/rubric (FKs)  | `data-model.md` §Audit; `schema-contract.md` §3 |
| Alembic scaffold: `alembic.ini`, `env.py`, `script.py.mako` | `backend-engineer` | false     | base (target_metadata)                  | `schema-contract.md` §Migration             |
| `0001_baseline.py` — tables (autogen-seeded, hand-finished) | `backend-engineer` | false     | all models + alembic scaffold           | `schema-contract.md` §DDL                   |
| `0001_baseline.py` — extensions + roles + triggers + grants | `backend-engineer` | false     | tables in same migration                | `schema-contract.md` §3 / §Roles            |
| Tests: migration round-trip + rubric tree + roles          | `backend-engineer` | false     | migration                               | `quickstart.md`                             |
| Tests: §3 append-only matrix                                | `backend-engineer` | false     | migration + roles                       | `schema-contract.md` §3; `data-model.md`    |
| `docker-compose.test.yml` parity fix + alembic step        | `backend-engineer` | false     | migration runnable                      | §7 parity                                   |
| Doc-fix (implementation-plan ADR typo) + `README.md`       | `backend-engineer` | false     | spec/plan committed                     | n/a (in-PR clarification)                   |

All T05 slices are sequential inside one PR. No sub-agent fan-out from inside T05. The parallel boundary is "T05 as a whole → afterwards T05a ∥ T06 ∥ T08".

## Phase 0 — Outline & Research

Research output: [research.md](./research.md). The spec has zero `[NEEDS CLARIFICATION]` markers; the three Clarifications are resolved. Phase 0 settles the implementation-altitude decisions:

1. **Async vs sync Alembic & driver count** — async `env.py` over a single `asyncpg` driver (no second sync `psycopg`); offline `--sql` mode for the T10 dry-run gate.
2. **§3 enforcement design** — shared `reject_audit_mutation()` trigger + `REVOKE UPDATE, DELETE` on `techscreen_app`; migrator exemption via `current_user`; **why both layers** and how each is independently testable.
3. **Testing the two layers without new credentials** — connect as the existing compose superuser, then `SET ROLE techscreen_app` / `techscreen_migrator` / `RESET ROLE`; NOLOGIN roles suffice.
4. **Test image parity** — `postgres:16-bookworm` → `pgvector/pgvector:pg17`; why pgvector must be present even though no `vector` column exists yet.
5. **Idempotent role creation** — guarded `DO $$ … $$` `CREATE ROLE` blocks; re-apply safety.
6. **SQLAlchemy 2.x typed models** — `Mapped[]` / `mapped_column`; `MetaData` naming convention for stable constraint/index names (so future migrations diff cleanly).
7. **UUID PK strategy** — `gen_random_uuid()` server default (pgcrypto) vs app-side UUIDs.
8. **Reversible `downgrade()`** — order of drops (triggers → functions → tables → roles → extensions); making `downgrade base` truly empty for local resets.
9. **DB-test gating** — skip when no DB reachable so the no-DB unit run stays green; marker + connectivity probe.
10. **What the rubric tree and append-only tables minimally contain** — enough columns + FKs to be coherent and to receive later-tier extensions, without finalising domain shape.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md): every table, its minimal column set, relationships, lifecycle (read-only tree / placeholder / append-only), and the constitution principle it serves. Covers the rubric tree (versioned), `user`, the three session placeholders, and the six append-only tables, plus the two database roles and the trigger function.

### Contracts

See [contracts/schema-contract.md](./contracts/schema-contract.md) — the structural contract downstream tasks (T05a, T06, T08, T15, T18–T21) build against: table names + key columns + FK directions, the append-only trigger/grant guarantee, the two role names and their privilege shapes, the extension set, and the migration up/down behaviour. The runtime artefact (`alembic/versions/0001_baseline.py` + the models) is the source of truth; the contract document references it rather than duplicating DDL.

### Quickstart

See [quickstart.md](./quickstart.md) — a reviewer-facing walkthrough that brings up the `db` profile, runs the migration up/down, runs the DB test suite, and ticks each Success Criterion (SC-001…SC-007) in under 10 minutes without a cloud database.

### Agent context update

`CLAUDE.md` carries no `<!-- SPECKIT START/END -->` markers (verified: zero matches, same as T02–T04). No auto-generated block is re-introduced; the existing "Where to find things" already lists `alembic/` and `app/backend/`. **No `CLAUDE.md` edit in this step.**

### Re-evaluate Constitution Check (post-design)

Nothing in Phase 0/1 changes the gate. The async-Alembic + single-driver choice, the trigger+revoke design with migrator exemption, the SET-ROLE test strategy, and the pg17/pgvector parity fix are all consistent with §1, §3, §4, §7, §10, §15, §16, §17, §18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations. Table intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
