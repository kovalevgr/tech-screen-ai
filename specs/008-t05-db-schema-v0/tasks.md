---
description: "Task list for T05 — DB schema v0 + Alembic baseline + append-only enforcement"
---

# Tasks: DB schema v0 + Alembic baseline + append-only enforcement (T05)

**Input**: Design documents from `specs/008-t05-db-schema-v0/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/schema-contract.md, quickstart.md

**Tests**: INCLUDED — the spec explicitly requires the §3 invariant tests (FR-012, SC-004) plus the migration round-trip and rubric-tree tests. Test tasks are therefore first-class here, not optional.

**Agent / parallelism**: every task is `agent: backend-engineer`, executed sequentially in one PR. `[P]` marks tasks that touch *different files* and may be written back-to-back without ordering hazards; it does **not** authorise sub-agent fan-out (constitution §18 — `parallel: false` for T05 as a whole). Tasks that edit the single migration file `alembic/versions/0001_baseline.py` are never `[P]` with each other.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Introduce SQLAlchemy + Alembic tooling and the `app/backend/db/` package scaffold (none exist yet).

- [ ] T001 Add `sqlalchemy[asyncio]>=2.0,<2.1`, `alembic>=1.13,<2`, `asyncpg>=0.30,<0.31` to `[project].dependencies` in `pyproject.toml`; run `uv lock` to regenerate `uv.lock`. (research §1; contract §0)
- [ ] T002 Create `app/backend/db/__init__.py` and `app/backend/db/base.py` — `class Base(DeclarativeBase)` with an explicit `MetaData(naming_convention=…)` per research §6. Export `Base` and `metadata`.
- [ ] T003 [P] Create `app/backend/db/models/_mixins.py` — `UUIDPk` (UUID PK, `server_default=text("gen_random_uuid()")`) and `TimestampCreated` (`created_at TIMESTAMPTZ NOT NULL server_default=func.now()`) mixins (research §7; data-model §Base infrastructure).
- [ ] T004 [P] Create `app/backend/db/session.py` — `create_async_engine(settings.database_url)` + `async_sessionmaker`. Runtime-only (later tiers); not imported by Alembic. Guard against `database_url is None`.
- [ ] T005 Add `database_url: str | None = None` field to `Settings` in `app/backend/settings.py` (reads `DATABASE_URL`); keep existing fields/validators untouched.
- [ ] T006 Create Alembic scaffold at repo root: `alembic.ini` (`script_location = alembic`, no hard-coded URL), `alembic/env.py` (async: `async_engine_from_config` + `connection.run_sync(...)`, `target_metadata = Base.metadata`, URL from `Settings`/`DATABASE_URL`, offline `--sql` mode supported per research §1), `alembic/script.py.mako`. Replace the `alembic/.gitkeep` placeholder.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Author all SQLAlchemy models and the table-creation + extensions + roles core of the baseline migration. Every user story below depends on this schema existing.

**⚠️ CRITICAL**: No user story can be validated until this phase is complete.

- [ ] T007 [P] Create `app/backend/db/models/rubric.py` — `rubric_tree_version`, `stack`, `competency_block`, `competency`, `topic`, `level` with parent FKs + `rubric_tree_version_id` on every node (data-model §Rubric; §4/ADR-018).
- [ ] T008 [P] Create `app/backend/db/models/identity.py` — `user` (`subject` UNIQUE, `role`); staff only, no candidate PII (data-model §Identity; §15).
- [ ] T009 [P] Create `app/backend/db/models/interview.py` — `position_template`, `interview_session` (FK→position_template, nullable), `interview_plan` (FK→interview_session, nullable); minimal placeholders only (data-model §Session placeholders; spec Clarification).
- [ ] T010 Create `app/backend/db/models/audit.py` — the six append-only tables (`turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`) with the FK graph from data-model §Audit (`assessment_correction.assessment_id→assessment`, etc.). `audit_log` carries only `actor_id`/`action`/`subject_hash`/`ts` (§15). **Decision (deferred per data-model §turn_trace)**: do NOT add the T04 `TraceRecord` columns (`agent`/`model`/`outcome`/`latency_ms`/`cost_usd`/`prompt_sha`) here — they land in T21 via a forward migration. Add a code comment recording this so T21 has the anchor.
- [ ] T011 Create `app/backend/db/models/__init__.py` importing every model module so `Base.metadata` is complete for Alembic.
- [ ] T012 Create `alembic/versions/0001_baseline.py` (`revision="0001_baseline"`, `down_revision=None`). `upgrade()`: `CREATE EXTENSION IF NOT EXISTS vector` + `CREATE EXTENSION IF NOT EXISTS pgcrypto`, then all 16 `op.create_table(...)` (seed via `alembic revision --autogenerate` against the models, then hand-finish ordering/onupdate). No `vector(...)` column (contract §2).
- [ ] T013 In `alembic/versions/0001_baseline.py` `upgrade()`, add idempotent role creation: guarded `DO $$ … CREATE ROLE techscreen_app NOLOGIN … $$` and same for `techscreen_migrator` (research §5; contract §Roles).
- [ ] T014 Extend `app/backend/tests/conftest.py` with DB fixtures: a session-scoped `db_available` probe that `pytest.skip`s the `db/` suite when `DATABASE_URL` is unset/unreachable; a session-scoped fixture that runs `alembic upgrade head` once against the test DB (research §9 — use the real migration, not `create_all`); an async-engine fixture; a `set_role` async helper (`SET ROLE …` / `RESET ROLE`).

**Checkpoint**: schema + roles exist; test harness can reach a migrated DB. User-story validation can begin.

---

## Phase 3: User Story 1 — DB physically refuses to mutate audit history (Priority: P1) 🎯 MVP

**Goal**: The six append-only tables cannot be `UPDATE`d/`DELETE`d by the app role, enforced by trigger + revoke; the migrator may still mutate.

**Independent Test**: As `techscreen_app`, every UPDATE/DELETE on the six tables is rejected; INSERT/SELECT succeed; as superuser the trigger fires; as `techscreen_migrator` mutation succeeds (quickstart §3–4).

### Implementation for User Story 1

- [ ] T015 [US1] In `alembic/versions/0001_baseline.py` `upgrade()`, add the shared trigger function `reject_audit_mutation()` (PL/pgSQL): exempt `current_user='techscreen_migrator'`, else `RAISE EXCEPTION 'append-only: % not allowed on %', TG_OP, TG_TABLE_NAME` (data-model §Trigger function; research §2).
- [ ] T016 [US1] In the same migration, wire a `BEFORE UPDATE OR DELETE … FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()` trigger on each of the six append-only tables.
- [ ] T017 [US1] In the same migration, `GRANT INSERT, SELECT` to `techscreen_app` and `REVOKE UPDATE, DELETE` from `techscreen_app` on the six tables; ensure `techscreen_migrator` retains full DML (contract §3; FR-004/005/006; SC-005 — keep the REVOKE statements greppable/grouped).

### Tests for User Story 1

- [ ] T018 [P] [US1] Create `app/backend/tests/db/__init__.py` and `app/backend/tests/db/test_append_only.py` — for each of the six tables: as `techscreen_app`, assert UPDATE rejected and DELETE rejected (12 asserts, SC-004); assert INSERT allowed; plus the trigger layer (as superuser → `append-only:` error on a representative table) and the migrator path (as `techscreen_migrator` → mutation succeeds). (contract §Test obligations; SC-003/004)
- [ ] T019 [P] [US1] Create `app/backend/tests/db/test_roles.py` — both roles exist (`pg_roles`); `techscreen_app` has INSERT+SELECT but lacks UPDATE/DELETE on all six tables (`has_table_privilege`); trigger present on all six (`pg_trigger`). (SC-003/005)

**Checkpoint**: §3 append-only is enforced and proven on every audit table — the MVP of T05.

---

## Phase 4: User Story 2 — Build the schema from zero and reset it (Priority: P1)

**Goal**: One command brings an empty DB to full schema; one command returns it to empty; re-apply is idempotent.

**Independent Test**: `alembic upgrade head` (twice) then `alembic downgrade base` leaves zero relations (quickstart §1, §6).

### Implementation for User Story 2

- [ ] T020 [US2] Add `downgrade()` to `alembic/versions/0001_baseline.py`: drop triggers → `reject_audit_mutation()` → all tables (children before parents) → `DROP ROLE IF EXISTS` both roles → `DROP EXTENSION IF EXISTS vector/pgcrypto` (research §8; FR-002/SC-002). Document in the downgrade docstring that this is for local/CI reset only (§10 forward-only in prod).
- [ ] T021 [US2] Update `docker-compose.test.yml`: change Postgres image `postgres:16-bookworm` → `pgvector/pgvector:pg17` (parity §7 + pgvector availability, research §4); re-enable the `alembic upgrade head` step in the backend command (remove the `# TODO(T05)` comment). Add a doc-comment to `docker-compose.yml` noting the `--profile db` migrate command (image already pg17).

### Tests for User Story 2

- [ ] T022 [P] [US2] Create `app/backend/tests/db/test_baseline_migration.py` — `upgrade head` creates all 16 tables + both extensions + both roles; a second `upgrade head` succeeds (idempotency, SC-006); `downgrade base` leaves zero relations (SC-002). (contract §Migration; SC-001/002/006)

**Checkpoint**: the schema is reproducible and fully reversible on a laptop with no cloud DB.

---

## Phase 5: User Story 3 — Stable schema for downstream foreign keys (Priority: P2)

**Goal**: The rubric tree relationships + version linkage and the enabled extensions are present so later tiers can build FKs without a destructive migration.

**Independent Test**: rubric tree parent/child FKs + `rubric_tree_version` linkage resolve; `vector`+`pgcrypto` present; a transactional insert/rollback on a non-audit table leaves no row (quickstart §2; spec US3 + US2#4).

### Tests for User Story 3

- [ ] T023 [P] [US3] Create `app/backend/tests/db/test_rubric_tree.py` — insert a `rubric_tree_version → stack → competency_block → competency → topic/level` chain and assert FKs resolve; assert `vector` + `pgcrypto` in `pg_extension` (SC-007); insert a `stack` inside a transaction and roll back, asserting no row persists (US2 acceptance #4).

**Checkpoint**: all three user stories independently validated.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T024 [P] Doc-fix: in `docs/engineering/implementation-plan.md` T05 entry, correct the pgvector reference `ADR-008` → `ADR-007` (ADR-008 is hybrid prompt language). (spec Assumptions; plan §7)
- [ ] T025 [P] Add a "Database dev loop" subsection to `README.md`: migrate up/down commands, how to run the `db` test profile, the two roles and the append-only guarantee.
- [ ] T026 Run guardrails on the post-T05 tree: `ruff check app/backend`, `mypy --strict app/backend`, `python -m app.backend.generate_openapi --check` (byte-identical — no route added), `pre-commit run --all-files`; then run the full `quickstart.md` walkthrough and tick SC-001…SC-007.

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)** → no deps; start immediately.
- **Foundational (P2)** → depends on Setup. Blocks all user stories. (Models T007–T009 are `[P]`; T010 depends on them for FKs; T012 depends on all models; T013 part of same migration after T012; T014 depends on T012/T013 being runnable.)
- **US1 (P3)** → depends on Foundational. T015→T016→T017 edit the same migration file sequentially (not `[P]`). Tests T018/T019 are `[P]` with each other.
- **US2 (P4)** → depends on Foundational; T020 edits the same migration (sequential after US1's edits). T021 independent file.
- **US3 (P5)** → depends on Foundational only.
- **Polish (P6)** → after the stories that produce the artefacts it documents.

### Story independence
- US1, US2, US3 each have their own test files and validate distinct acceptance scenarios; all three share the single migration authored across Foundational + US1 + US2. That shared file is why intra-migration tasks are sequential, not parallel.

### Parallel opportunities (file-level, single committer)
- T003 ∥ T004 (mixins ∥ session).
- T007 ∥ T008 ∥ T009 (model modules, different files).
- T018 ∥ T019 (US1 test files); T024 ∥ T025 (doc files).
- Never parallel: any two edits to `alembic/versions/0001_baseline.py` (T012, T013, T015, T016, T017, T020).

---

## Implementation Strategy

### MVP first (US1)
1. Setup (Phase 1) → Foundational (Phase 2) → US1 (Phase 3).
2. **STOP and VALIDATE**: append-only enforced on all six tables (the constitutional core of T05).

### Incremental delivery
1. Setup + Foundational → schema exists.
2. US1 → §3 enforcement proven (MVP).
3. US2 → reproducible up/down + CI parity.
4. US3 → downstream-FK readiness validated.
5. Polish → doc-fix, README, guardrails, quickstart.

### Suggested commit grouping (manual commits, our norm)
- `feat(T05): SQLAlchemy models + db package scaffold` (T001–T011)
- `feat(T05): Alembic baseline migration 0001 (tables + extensions + roles)` (T012–T014)
- `feat(T05): §3 append-only enforcement — triggers + REVOKE` (T015–T017)
- `test(T05): append-only matrix + roles + migration round-trip + rubric tree` (T018–T023)
- `chore(T05): test-stack pg17/pgvector parity + alembic step` (T021)
- `docs(T05): ADR-007 pgvector typo fix + README db dev loop` (T024–T025)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- The §3 guarantee lives in the migration, so tests run `alembic upgrade head`, never `create_all`.
- DB tests skip cleanly when no DB is reachable, keeping the no-DB unit run green.
- `turn_trace` rich columns are intentionally deferred to T21 (recorded in T010).
- Commit after each logical group; run `pre-commit` before each commit.
