# Implementation Plan: Rubric snapshot (deep-copy on session start) (T15)

**Branch**: `015-t15-rubric-snapshot` | **Date**: 2026-06-24 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/015-t15-rubric-snapshot/spec.md`

## Summary

Implement constitution §4. Add a `rubric_snapshot` JSONB column to
`interview_session` (migration `0005`, NOT NULL via a transitional
`'{}'::jsonb` default), a pure `snapshot_rubric(conn, rubric_tree_version_id)
-> RubricSnapshot` that deep-copies the whole tree (stack → competency_block →
competency → {topic, level}) into a self-contained structure, a Pydantic
`RubricSnapshot` family + the committed `docs/contracts/rubric-snapshot.schema.json`
(§14), and a `freeze_session_rubric` persist helper. Prove §4 with a mutation
test: snapshot a version onto a session, mutate the live tree, the stored
snapshot is unchanged.

## Technical Context

**Language/Version**: Python 3.12
**Primary Dependencies**: SQLAlchemy 2.x async (AsyncConnection + Core SQL, matching the rubric read style), Pydantic v2, Alembic
**Storage**: PostgreSQL 17 — existing rubric tree (T08) + `interview_session` placeholder (T05); migration head `0004_position_template` → new `0005_rubric_snapshot`
**Testing**: pytest in the `docker-compose.test.yml` db-profile stack (real Postgres); 171-test baseline stays green
**Target Platform**: Linux container (Docker parity dev/CI, §7)
**Project Type**: Web service (backend only)
**Performance Goals**: N/A (snapshot is a one-time per-session copy; no hot path)
**Constraints**: §4 immutability (the deliverable); forward-only additive migration (§10); self-contained snapshot (no live FK reliance)
**Scale/Scope**: one column + one read-only snapshot function + one persist helper + one JSON-schema contract + §4 tests

## Constitution Check

*GATE: must pass before Phase 0. Re-checked after Phase 1 (below).*

| Principle | Relevance | Verdict |
| --- | --- | --- |
| §4 Immutable rubric snapshot | **This task IS §4.** `interview_session.rubric_snapshot` becomes NOT NULL; the snapshot is a self-contained deep copy; tests prove a rubric edit never changes a stored snapshot. | ✅ Pass (implements it) |
| §3 Append-only | `interview_session` is not an append-only audit table; the snapshot is written once at capture and not mutated thereafter. No audit table is touched. | ✅ Pass |
| §10 Migration | `0005` is additive (`ADD COLUMN ... NOT NULL DEFAULT '{}'::jsonb`). No destructive upgrade DDL → no ADR. The dev-only downgrade's `DROP COLUMN` trips T10's whole-file detector → expected `needs-adr` false-positive (documented in the migration, as T12). | ✅ Pass (no ADR) |
| §14 Contract-first | `docs/contracts/rubric-snapshot.schema.json` committed so the Assessor (Tier 3) + reviewer tooling can read the snapshot shape without producer internals. | ✅ Pass |
| §15 PII | A snapshot is rubric structure, no candidate PII. | ✅ Pass |
| §17 / §18 | Spec-kit flow; single-agent (`backend-engineer`, `parallel: false`). | ✅ Pass |

**No violations → Complexity Tracking empty.**

### Key design decision (confirmed at the spec gate)

`rubric_snapshot` is **NOT NULL with a transitional `'{}'::jsonb` default**.
§4 mandates NOT NULL; the `interview_session` placeholder is inserted without a
snapshot by the T05 seed (and real session-creation is T28). The transitional
default keeps those inserts working and is only ever seen by placeholder/test
rows — every real session gets a real snapshot via `freeze_session_rubric`.

## Project Structure

### Documentation (this feature)

```text
specs/015-t15-rubric-snapshot/
├── spec.md            # committed (d70399d)
├── plan.md            # this file
├── research.md        # Phase 0 — decisions
├── data-model.md      # Phase 1 — column, snapshot shape, function, helper
├── quickstart.md      # Phase 1 — verification matrix (incl the §4 mutation test)
├── contracts/
│   └── rubric-snapshot.schema.json   # §14 contract for the frozen shape
└── tasks.md           # speckit-tasks (next gate)
```

### Source Code (repository root)

```text
app/backend/
├── db/models/interview.py          # EDIT — add rubric_snapshot JSONB to InterviewSession
├── schemas/rubric_snapshot.py      # NEW — RubricSnapshot + nested Snapshot* Pydantic models
├── services/rubric_snapshot.py     # NEW — snapshot_rubric(conn, version_id) + freeze_session_rubric(conn, session_id, version_id) + RubricSnapshotError
└── tests/
    ├── db/test_rubric_snapshot_migration.py     # column NOT NULL + default; placeholder insert still works
    ├── services/test_rubric_snapshot.py         # deep-copy structure; unknown-version error; §4 mutation invariant
    └── contracts/test_rubric_snapshot_contract.py  # schema valid; good snapshot passes / malformed rejected

alembic/versions/0005_rubric_snapshot.py         # NEW — additive ADD COLUMN
docs/contracts/rubric-snapshot.schema.json       # NEW — canonical committed contract
```

**Structure Decision**: Backend-only. The snapshot function reads the rubric
tree via `AsyncConnection` + Core SQL (matching the existing `tests/db` rubric
style and the T12 validator), keeping it independent of the ORM. The frozen
shape is a Pydantic family serialized to JSONB.

## Phase 0 — Research

See [research.md](./research.md). Resolves: the NOT-NULL-default choice; the
snapshot JSON shape (which fields/ids are copied for self-containment + Assessor
correlation); AsyncConnection + Core SQL vs ORM for the deep copy; deterministic
ordering for a stable snapshot; how `freeze_session_rubric` writes JSONB; and the
unknown-version error path.

## Phase 1 — Design & Contracts

- [data-model.md](./data-model.md) — the `rubric_snapshot` column, the
  `RubricSnapshot` nested shape mapped to the T08 tree, the function + helper
  signatures, and the §4 invariant mapping.
- [contracts/rubric-snapshot.schema.json](./contracts/rubric-snapshot.schema.json)
  — the committed §14 contract (design copy; canonical at `docs/contracts/`).
- [quickstart.md](./quickstart.md) — verification matrix incl. the §4 mutation test.
- **Agent context**: `CLAUDE.md` has no `<!-- SPECKIT -->` markers — injection skipped intentionally.

## Phase 2 — Task planning approach (preview, not executed here)

`speckit-tasks` will produce a single-agent (`backend-engineer`,
`parallel: false`) list: (1) ORM column + migration `0005` + migration test;
(2) `RubricSnapshot` Pydantic models; (3) `snapshot_rubric` + `freeze_session_rubric`
+ structure/unknown-version tests; (4) the §4 mutation test; (5) JSON-schema
contract + contract test; (6) verification matrix + regression.

## Complexity Tracking

*No constitution violations — section intentionally empty.*
