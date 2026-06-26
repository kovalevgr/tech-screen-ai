---
description: "Task list for T15 — Rubric snapshot (deep-copy on session start)"
---

# Tasks: Rubric snapshot (deep-copy on session start) (T15)

**Input**: Design documents from `specs/015-t15-rubric-snapshot/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/rubric-snapshot.schema.json, quickstart.md

**Tests**: Integration tests against real Postgres (`docker-compose.test.yml` db profile) ARE the proof of §4 — the deep-copy structure, the unknown-version guard, the self-containment, and the mutation-immutability invariant. Plus the 171-test regression baseline and the JSON-schema contract round-trip.

**Agent / parallelism**: every task is `agent: backend-engineer`, executed sequentially in one PR (§18 — `parallel: false`). `[P]` marks tasks that touch *different files*; NOT sub-agent fan-out. T15 has a migration (`0005`); no change to the rubric tables.

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

No setup needed — `schemas/` and `services/` packages already exist (T12/T13); no new dependency.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The column + migration + frozen-shape models underpin the snapshot function and every test.

- [ ] T001 Edit `app/backend/db/models/interview.py`: add `rubric_snapshot: Mapped[dict[str, Any]]` to `InterviewSession` (`JSONB`, `nullable=False`, `server_default=text("'{}'::jsonb")`). Create `alembic/versions/0005_rubric_snapshot.py` (`down_revision = "0004_position_template"`): raw `op.execute("ALTER TABLE interview_session ADD COLUMN rubric_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb")`; symmetric dev-only `downgrade()` (`DROP COLUMN IF EXISTS`); docstring noting additive upgrade + the T10 `needs-adr` false-positive (as `0004`). (data-model.md; FR-003/007)
- [ ] T002 Create `app/backend/tests/db/test_rubric_snapshot_migration.py` (db profile): assert the `rubric_snapshot` column exists, is NOT NULL, and defaults to `{}`; assert a placeholder insert `INSERT INTO interview_session (position_template_id) VALUES (...)` still succeeds (the transitional default covers it). (FR-007; SC-004)
- [ ] T003 [P] Create `app/backend/schemas/rubric_snapshot.py`: the `RubricSnapshot` family (`RubricSnapshot`, `SnapshotStack`, `SnapshotCompetencyBlock`, `SnapshotCompetency`, `SnapshotTopic`, `SnapshotLevel`), Pydantic v2, `extra="forbid"`, mirroring the data-model shape (ids carried as plain values). (data-model.md; FR-002)

**Checkpoint**: the column exists and the frozen shape is defined.

---

## Phase 3: User Story 1 — A session's assessment basis is frozen at start (Priority: P1) 🎯 MVP

**Goal**: Capture a complete, self-contained snapshot of a rubric version.

**Independent Test**: Snapshot a seeded version → the structure matches the source (every stack/block/competency/topic/level); reading it needs no live join; an unknown version errors.

### Implementation for User Story 1

- [ ] T004 [US1] Create `app/backend/services/rubric_snapshot.py`: `RubricSnapshotError`; `snapshot_rubric(conn, rubric_tree_version_id) -> RubricSnapshot` (deterministic `SELECT`s per level over `AsyncConnection`; raise on a non-existent version — FR-005); `freeze_session_rubric(conn, interview_session_id, rubric_tree_version_id) -> RubricSnapshot` (UPDATE the session's `rubric_snapshot` with `model_dump(mode="json")`). (data-model.md; research §3/§4; FR-001/002/005)
- [ ] T005 [US1] Create `app/backend/tests/services/test_rubric_snapshot.py` (db profile): seed a full rubric version, assert `snapshot_rubric` reproduces the whole tree (names/ranks/descriptors/positions, child counts); assert the snapshot is self-contained (all values present); assert an unknown version id raises `RubricSnapshotError`. (SC-001/003; FR-005)

**Checkpoint**: a faithful, self-contained snapshot is produced and unknown versions are rejected.

---

## Phase 4: User Story 2 — A later rubric edit never changes a session (Priority: P1)

**Goal**: Prove the §4 immutability invariant.

**Independent Test**: Freeze a version onto a session; mutate the live tree; the stored snapshot is unchanged.

### Implementation for User Story 2

- [ ] T006 [US2] Extend `app/backend/tests/services/test_rubric_snapshot.py`: seed version V + a session; `freeze_session_rubric`; capture the stored JSON; then rename a stack, insert a new competency, and create a newer `rubric_tree_version`; re-read `interview_session.rubric_snapshot` and assert it equals the captured JSON exactly. (FR-004; SC-002 — the §4 invariant)

**Checkpoint**: the immutability guarantee is regression-proof.

---

## Phase 5: Contract (cross-cutting, §14)

- [ ] T007 Commit the canonical contract `docs/contracts/rubric-snapshot.schema.json` (copy of the design under `specs/015-.../contracts/`; `$id` already points at the `docs/contracts/` path). Create `app/backend/tests/contracts/test_rubric_snapshot_contract.py`: assert it is a valid Draft 2020-12 schema, validates a good snapshot, and rejects a malformed one (e.g. missing `rubric_tree_version_id`). Optionally assert a real `snapshot_rubric` output validates against it. (FR-006; SC-005)

---

## Phase 6: Polish & Verification

- [ ] T008 Run the quickstart verification matrix: `alembic upgrade head` → `0005`; all T15 test files pass (incl. the §4 mutation test); the full db-profile suite (171 baseline + new) green; `ruff check` + `ruff format --check` + `mypy --strict` clean; `generate_openapi --check` clean (no-op — no routes); destructive-DDL grep over the `0004→0005` upgrade render is additive-only. (quickstart.md §A–C)

---

## Dependencies & Execution Order

### Phase dependencies
- **Foundational (Phase 2)** → T001 (column+migration) → T002 (migration test); T003 (`[P]`, schemas — different file). All block the user stories.
- **US1 (Phase 3)** → T004 (needs T003 models + T001 column) → T005 (tests).
- **US2 (Phase 4)** → T006 (needs T004 `freeze_session_rubric` + T001 column).
- **Contract (Phase 5)** → T007 (schema mirrors T003; test may use T004 output).
- **Polish (Phase 6)** → T008 after everything.

### Parallel opportunities (file-level, single committer)
- T003 (`schemas/rubric_snapshot.py`) ∥ T001/T002 (interview.py + migration + db test).
- Never parallel: edits to `services/rubric_snapshot.py` (T004) or to `tests/services/test_rubric_snapshot.py` (T005→T006).

---

## Implementation Strategy

### MVP first (US1)
1. Foundational (column + migration + models) → US1 (snapshot function + tests).
2. **STOP and VALIDATE**: a snapshot reproduces the tree and is self-contained.

### Incremental delivery
1. Foundational → column + shape exist.
2. US1 → capture + self-containment (MVP).
3. US2 → the §4 immutability proof.
4. Contract → committed §14 shape + test.
5. Polish → verification matrix + regression.

### Suggested commit grouping (manual commits, our norm)
- `feat(T15): rubric_snapshot column + 0005 migration + migration test` (T001–T002)
- `feat(T15): RubricSnapshot schemas` (T003)
- `feat(T15): snapshot_rubric + freeze helper + tests` (T004–T005)
- `test(T15): §4 rubric-snapshot immutability test` (T006)
- `feat(T15): rubric-snapshot.schema.json contract + contract test; verification` (T007–T008)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- T15 reuses the rubric tables (T08) read-only; the only schema change is the additive `rubric_snapshot` column.
- Migration `0005` upgrade is additive → CI's destructive-DDL gate flags `needs_adr=true` only from the dev-only downgrade DROP (documented false-positive, as `0004`).
- OpenAPI is a no-op (T15 adds no routes).
