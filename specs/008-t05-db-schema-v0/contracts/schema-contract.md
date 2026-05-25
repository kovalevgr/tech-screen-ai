# Schema Contract: T05 — DB schema v0

This is the structural contract downstream tasks (T05a, T06, T08, T15, T18–T21, T35, T37) build against. The **source of truth** is the runtime artefact `alembic/versions/0001_baseline.py` + the SQLAlchemy models under `app/backend/db/models/`; this document states the guarantees those artefacts must uphold so a reviewer (and later tasks) can rely on them without re-reading the DDL. Where this contract and the code disagree, the code is fixed to match the contract — or the contract is amended by a follow-up plan.

## §0 — Dependency budget

Added to `[project].dependencies`: `sqlalchemy[asyncio] >= 2.0,<2.1`, `alembic >= 1.13,<2`, `asyncpg >= 0.30,<0.31`. No new dev dependency. No `pgvector` Python package (no `vector` column yet). `uv.lock` regenerated.

## §1 — Tables created (names are contract)

Rubric tree: `rubric_tree_version`, `stack`, `competency_block`, `competency`, `topic`, `level`.
Identity: `user`.
Session placeholders: `position_template`, `interview_session`, `interview_plan`.
Append-only (§3): `turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`.

Column-level detail and FK directions: see [../data-model.md](../data-model.md). Downstream tasks may rely on: every table has a UUID `id` PK defaulted by `gen_random_uuid()`; every table except `audit_log` has `created_at TIMESTAMPTZ` (`audit_log` uses `ts`); the FK graph in data-model.md §Relationship summary.

## §2 — Extensions

After `upgrade head`, `vector` and `pgcrypto` are present (`SELECT extname FROM pg_extension`). Created with `IF NOT EXISTS`. No `vector(...)` column exists yet — later embedding work (H2) adds it without a destructive migration.

## §3 — Append-only guarantee (the core contract)

For each of the six append-only tables, **as the `techscreen_app` role**:
- `INSERT` — allowed.
- `SELECT` — allowed.
- `UPDATE` — rejected (permission denied; the grant is revoked).
- `DELETE` — rejected (permission denied; the grant is revoked).

Independently, **as any non-migrator role including superuser**:
- `UPDATE`/`DELETE` — rejected by the `reject_audit_mutation()` trigger with SQLSTATE `P0001` and message `append-only: <TG_OP> not allowed on <table>`.

**As the `techscreen_migrator` role**:
- `UPDATE`/`DELETE` — allowed (trigger exemption + retained grant), so human-approved forward-only migrations (§10) can evolve audit data.

Downstream write-side tasks (T21 writes `turn_trace`; T19 writes `assessment`; T35 writes `assessment_correction`/`turn_annotation`; T37 writes `session_decision`) MUST only `INSERT` (and `SELECT`) — never `UPDATE`/`DELETE` — on these tables. "Effective value" reads use latest-correction-wins query logic (ADR-019), not mutation.

## §Roles — role contract

Two cluster-global roles exist after `upgrade head`:
- `techscreen_app` — `NOLOGIN` (T05). Privileges per §3. T06 adds `LOGIN` + a Secret-Manager password and points the runtime DSN at it.
- `techscreen_migrator` — `NOLOGIN` (T05). Full DDL+DML; trigger-exempt. T06 adds `LOGIN` + password; Alembic in prod runs as this role.

T06 MUST NOT redefine these roles — only `ALTER ROLE … LOGIN PASSWORD …` and grant connect/usage. The privilege shape on the six tables is owned by T05.

## §Migration — up/down behaviour

- `alembic upgrade head` on an empty database creates all of the above; idempotent on re-run (guarded roles, `IF NOT EXISTS` extensions).
- `alembic downgrade base` returns the database to empty (triggers → function → tables → roles → extensions). Local/CI reset only; production is forward-only (§10).
- Offline `alembic upgrade head --sql` renders complete SQL (for the T10 dry-run gate) — all structural statements are `op.execute()` raw SQL that renders without a connection.
- Migration revision id: `0001_baseline`, `down_revision = None`.

## §Docker parity

`docker-compose.test.yml` Postgres image is `pgvector/pgvector:pg17` (== dev). The backend test command runs `alembic upgrade head` before `pytest` under the `db` profile.

## §Test obligations (maps to spec SC)

| Test | Asserts | Spec |
| ---- | ------- | ---- |
| migration round-trip | upgrade creates all objects; downgrade empties; second upgrade succeeds | SC-001/002/006 |
| role + grant shape | both roles exist; app role lacks UPDATE/DELETE, has INSERT/SELECT on all six tables | SC-003/005 |
| append-only matrix | per-table app-role UPDATE+DELETE rejected (12 asserts); trigger layer (superuser); migrator path succeeds; INSERT succeeds | SC-003/004 |
| rubric tree + tx | parent/child FKs + version linkage resolve; insert/rollback on `stack` leaves no row | US3, US2#4 |
| extensions | `vector` + `pgcrypto` present | SC-007 |
