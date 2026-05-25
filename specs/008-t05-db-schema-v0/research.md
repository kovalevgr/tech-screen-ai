# Phase 0 Research: T05 — DB schema v0 + Alembic baseline + append-only enforcement

All decisions sit below spec altitude and above `speckit-tasks` altitude. Each is rooted in an existing repo artefact (committed DSN, compose file, constitution clause) or a load-bearing Postgres/Alembic behaviour.

---

## §1 — Async vs sync Alembic, and how many drivers

**Decision**: One driver — `asyncpg`. The app runtime uses `create_async_engine("postgresql+asyncpg://…")`. Alembic uses an **async `env.py`** that opens an async connection and runs the migration body via `connection.run_sync(do_run_migrations)`. No second synchronous driver (`psycopg`) is added.

**Rationale**:
- Both `docker-compose.yml` and `docker-compose.test.yml` already pin `DATABASE_URL=postgresql+asyncpg://…`. The driver is therefore a **pre-committed contract** — choosing anything else would mean rewriting infra the earlier tiers already shipped.
- A single driver keeps the dependency budget minimal (constitution "floor not ceiling" bias) and avoids the "which URL does this code path use" foot-gun.
- Alembic's documented async recipe (`async_engine_from_config` + `run_sync`) is mature and is exactly the shape the SQLAlchemy 2.x docs recommend.
- The T10 CI dry-run gate (`alembic upgrade head --sql`, §10) runs in **offline** mode, which does not open a connection at all — it renders DDL from the migration ops against the dialect. Our raw-SQL `op.execute()` blocks (extensions, roles, triggers, grants) render verbatim offline, so the gate works without asyncpg connecting.

**Alternatives considered**:
- *Sync `psycopg` for migrations + asyncpg for runtime* — two drivers, two URL shapes, and a translation step (`postgresql+asyncpg` → `postgresql+psycopg`) in `env.py`. Rejected: more moving parts for zero benefit at our scale.
- *Fully sync stack* — rejected: the app runtime is async (FastAPI handlers grow `async def` as they gain DB calls), and T04 already established async as the spine.

---

## §2 — The §3 enforcement design (the core of T05)

**Decision**: Defend the six append-only tables with **two independent layers**:

1. **A shared trigger function** `reject_audit_mutation()` (PL/pgSQL), wired as a `BEFORE UPDATE OR DELETE` row-level trigger on each of the six tables. It raises:
   `RAISE EXCEPTION 'append-only: % not allowed on %', TG_OP, TG_TABLE_NAME;`
   …**unless** `current_user = 'techscreen_migrator'`, in which case it returns the row unchanged (allowing human-approved migrations to evolve audit data — FR-006, §10).
2. **`REVOKE UPDATE, DELETE`** on all six tables from `techscreen_app`, while `GRANT INSERT, SELECT` remains. The migrator role keeps full DML.

**Rationale (why both)** — the layers fail differently, so together they cover more:
- The **REVOKE** is the hard floor: a role without the privilege cannot even attempt the statement; the database rejects it at permission-check time. But REVOKE is invisible to a superuser connection (superusers bypass grants), so on a dev box where the app currently connects as the `techscreen` superuser the revoke alone would not protect anything.
- The **trigger** fires for *everyone* who is not the migrator — including a superuser — so it catches the exact dev/test case the revoke misses, and it produces a **self-describing error** (`append-only: UPDATE not allowed on assessment`) that tells a developer *why*, not just "permission denied".
- ADR-019 mandates the REVOKE; the trigger is the defense-in-depth the implementation-plan T05 entry adds on top. Constitution §3 is satisfied by the REVOKE; §1 (auditability as a first-class, not best-effort, guarantee) motivates the second layer.

**Why the migrator exemption lives in the trigger (not "disable triggers in migrations")**:
- A `current_user`-keyed exemption needs no elevated privilege and works identically on local Postgres and Cloud SQL.
- The alternative — `ALTER TABLE … DISABLE TRIGGER` or `SET session_replication_role = replica` inside data migrations — requires table-owner or superuser rights that the migrator may not have on managed Cloud SQL, and it disables *all* triggers, a blunter instrument. Rejected.

**Alternatives considered**:
- *Trigger only* — loses the hard privilege floor; a future careless `GRANT` or a code path that disables the trigger reopens mutation. Rejected.
- *REVOKE only (literal constitution text)* — invisible to superusers; gives a cryptic error; no protection on the current dev superuser connection. Rejected as insufficient alone.
- *`RULE`-based blocking* — Postgres rules are legacy and interact badly with RETURNING. Rejected.

---

## §3 — Testing both enforcement layers without new credentials

**Decision**: Tests connect using the **existing compose superuser** (`techscreen`, already in the DSN) and switch identity with `SET ROLE` / `RESET ROLE` inside a transaction. The two T05 roles stay `NOLOGIN`. This yields three clean, independent probes per concern:

| Probe | How | Proves |
| ----- | --- | ------ |
| **Revoke layer** | `SET ROLE techscreen_app; UPDATE/DELETE <table>` | Fails with *permission denied* — the privilege floor (FR-004/005). 12 assertions = 6 tables × {UPDATE, DELETE}. |
| **Trigger layer** | as superuser (no SET ROLE), `UPDATE <table>` | Fails with *append-only: …* — superuser bypasses the grant, so only the trigger stands; isolates it. (A representative subset of tables — the function is shared, so one or two tables prove the wiring; all six are checked for trigger *presence* via catalog query.) |
| **Migrator path** | `SET ROLE techscreen_migrator; UPDATE <table>` | Succeeds — exemption + retained grant (FR-006). |
| **Append still works** | `SET ROLE techscreen_app; INSERT <table>` | Succeeds — INSERT/SELECT retained (FR-005, US1 #3). |

**Rationale**:
- `SET ROLE` from a superuser to a `NOLOGIN` role is permitted and makes privilege checks apply *as that role* (`is_superuser` becomes false), so the REVOKE is genuinely enforced under test — without provisioning a LOGIN password (that hardening is T06).
- Reuses the DSN already wired in `docker-compose.test.yml`; no new env var, no second connection pool.
- Each probe runs in its own transaction with `RESET ROLE` in teardown, so role state never leaks between tests.

**Alternatives considered**:
- *Give the roles LOGIN + dev passwords and open a second engine per role* — more fixtures, a password in compose, and pulls T06's concern forward. Rejected for T05.
- *Test only the app-role rejection* — would leave the trigger layer unproven, and the trigger is the part that protects the current dev superuser connection. Rejected.

---

## §4 — Test Postgres image parity (pg16 → pg17 + pgvector)

**Decision**: Change `docker-compose.test.yml` Postgres from `postgres:16-bookworm` to `pgvector/pgvector:pg17` — matching `docker-compose.yml` (dev) exactly.

**Rationale**:
- The baseline runs `CREATE EXTENSION IF NOT EXISTS vector`. The stock `postgres:16-bookworm` image does **not** ship the pgvector extension files, so `alembic upgrade head` would fail in CI the moment we re-enable it. The `pgvector/pgvector:pg17` image bundles the extension.
- Constitution §7 (Docker parity dev → CI → prod) requires the test image to match dev. The existing pg16/pg17 split is a latent drift this PR is the right place to close (dev is already pg17; Cloud SQL will be pg17 per ADR-007/ADR-001).
- pgvector must be installable now even though T05 creates **no** `vector` column, because the *extension* is created at baseline (ADR-007 / spec FR; avoids a destructive migration later).

**Alternatives considered**:
- *Keep pg16 for tests, skip `CREATE EXTENSION vector` in test runs* — would make the migration behave differently in CI than in prod, defeating §7 and leaving the extension path untested. Rejected.
- *Use `pgvector/pgvector:pg16`* — closes the pgvector gap but not the version drift; ADR-007 amendment pins PG17. Rejected.

---

## §5 — Idempotent role creation

**Decision**: Create roles inside guarded `DO` blocks:
```sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'techscreen_app') THEN
    CREATE ROLE techscreen_app NOLOGIN;
  END IF;
END $$;
```
(same for `techscreen_migrator`). Extensions use `CREATE EXTENSION IF NOT EXISTS`.

**Rationale**: FR-003 / SC-006 require a second `upgrade` on an already-initialised database to succeed. `CREATE ROLE` has no `IF NOT EXISTS`, so the guard is necessary. Roles are cluster-global (not per-database), so on a shared local cluster they may already exist from a prior run — the guard makes that safe. `downgrade` drops the roles (after re-assigning/【dropping owned objects】 — see §8) so a clean local reset removes them too.

**Alternatives considered**: `CREATE ROLE … ` unguarded (fails on re-run) — rejected. `DROP ROLE IF EXISTS; CREATE ROLE` (churns role OIDs, breaks any granted membership) — rejected.

---

## §6 — SQLAlchemy 2.x typed models + naming convention

**Decision**: Use 2.x declarative typed style (`class Base(DeclarativeBase)`, `Mapped[...]`, `mapped_column(...)`). Attach an explicit `MetaData(naming_convention=…)` to `Base` so constraints/indexes get deterministic names:
```python
naming_convention = {
  "ix": "ix_%(column_0_label)s",
  "uq": "uq_%(table_name)s_%(column_0_name)s",
  "ck": "ck_%(table_name)s_%(constraint_name)s",
  "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
  "pk": "pk_%(table_name)s",
}
```

**Rationale**: Deterministic names make every later `alembic revision --autogenerate` produce stable, reviewable diffs (no random PostgreSQL-assigned constraint names churning across migrations). `Mapped[]` gives `mypy --strict` full coverage for free, satisfying the existing T01–T04 mypy gate. 2.x style only — the project is greenfield, no 1.x legacy.

**Alternatives considered**: 1.x `Column()` classic style (weaker typing) — rejected. No naming convention (Postgres-assigned names) — rejected: future autogenerate diffs would be noisy and migrations harder to review under §10.

---

## §7 — UUID primary-key strategy

**Decision**: Primary keys are `UUID` with a **server-side default** `gen_random_uuid()` (from `pgcrypto`), mapped as `mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))`.

**Rationale**: The implementation-plan T05 entry names `pgcrypto`'s `gen_random_uuid()` for PKs. Server-side generation means a plain `INSERT … DEFAULT` works from SQL probes and future bulk imports without the app pre-computing IDs, and keeps ID generation uniform across app code, the rubric importer (T08), and manual SQL. UUIDs (over serial integers) avoid cross-environment key collisions and don't leak row counts.

**Alternatives considered**: app-side `uuid4()` Python default (works, but SQL-only inserts in tests/imports wouldn't get a default) — rejected as the *primary* mechanism (the model may still set a Python-side default as a convenience, but the server default is authoritative). `BIGSERIAL` (enumerable, leaks volume, collides across envs) — rejected.

---

## §8 — Reversible `downgrade()`

**Decision**: `downgrade()` removes everything `upgrade()` created, in dependency-safe order:
1. `DROP TRIGGER` on each of the six tables, then `DROP FUNCTION reject_audit_mutation()`.
2. `DROP TABLE` for all tables (Alembic `op.drop_table`, children before parents).
3. `DROP ROLE IF EXISTS techscreen_app / techscreen_migrator` (after their privileges vanish with the tables; no owned objects remain because the migration created the objects as the migrating superuser, not as these NOLOGIN roles).
4. `DROP EXTENSION IF EXISTS vector; DROP EXTENSION IF EXISTS pgcrypto;`.

**Rationale**: FR-002 / SC-002 require `downgrade base` to leave an empty database for local resets. Order matters: triggers depend on the function and tables; roles must not own objects when dropped (they don't); extensions last. This does **not** change the production forward-only posture (§10) — downgrade is a local/CI convenience only and is never run against prod.

**Caveat researched**: dropping `pgcrypto`/`vector` on downgrade is safe here because nothing else in the (single-migration) tree depends on them; if a later migration starts depending on an extension, that migration owns its own create/keep decision. Documented in the migration's downgrade docstring.

**Alternatives considered**: leaving extensions/roles in place on downgrade (cluster-global, "harmless") — rejected: SC-002 asks for *zero orphaned objects*, and a truly empty reset is what local devs expect.

---

## §9 — Gating DB integration tests

**Decision**: DB tests live under `app/backend/tests/db/` and are **skipped when no database is reachable**. A session-scoped fixture probes `settings.database_url`; if unset or the connection fails, the whole `db/` package `pytest.skip`s with a clear reason. When present, a session-scoped fixture runs `alembic upgrade head` once against the test database before the suite.

**Rationale**:
- The existing no-DB unit command (`docker compose -f docker-compose.test.yml run --rm backend pytest`, no `db` profile) must stay green — T05 must not force every contributor to spin up Postgres for unrelated unit tests.
- Under `--profile db` (local) and in CI/T10, the DB is present and the suite runs in full.
- Running `alembic upgrade head` (rather than `Base.metadata.create_all`) in the fixture means the tests exercise the **actual migration** — including triggers, roles, and grants that `create_all` would never produce. This is essential: the §3 guarantee lives in the migration, not the model metadata.

**Alternatives considered**:
- `Base.metadata.create_all()` for test setup — faster, but skips the triggers/roles/grants that are the entire point. Rejected.
- A custom marker (`@pytest.mark.db`) deselected by default — viable, but a connectivity-probe skip is zero-config for the developer and matches how `captured_logs`/fixtures already lazy-load. We add the marker too for explicit selection, but the skip-on-unreachable is the gate.

---

## §10 — Minimal-but-coherent column sets

**Decision**: Each table gets a UUID PK, a `created_at TIMESTAMPTZ NOT NULL DEFAULT now()` (via the `TimestampCreated` mixin), the foreign keys that other T05 tables or known later-tier references need, and the few domain columns the implementation-plan explicitly named (e.g. `assessment.score` + `assessment.confidence`; `audit_log.actor_id` / `action` / `subject_hash` / `ts`). Everything else is deferred to the owning tier. The rubric tree additionally encodes parent FKs + `rubric_tree_version_id` on each node (ADR-018, §4).

**Rationale**: The spec Clarification fixed "minimal" for the session placeholders; this research extends the same principle to the audit tables (the implementation-plan calls them "schema only"). Coherent FKs now (e.g. `assessment_correction.assessment_id → assessment.id`) encode the ADR-019 "correction references the corrected row" shape, which is structural and must be right at baseline. Domain richness (status enums, transcript links, JSON payloads) lands with the tier that writes those rows, avoiding speculative columns that later need destructive changes.

**Exact column lists**: see [data-model.md](./data-model.md).

---

## Summary of resolved decisions

| # | Decision |
| - | -------- |
| 1 | Single `asyncpg` driver; async Alembic `env.py` via `run_sync`; offline `--sql` for the T10 gate. |
| 2 | Two-layer §3 enforcement: shared `reject_audit_mutation()` trigger (migrator-exempt) + `REVOKE UPDATE, DELETE` on `techscreen_app`. |
| 3 | Test both layers via `SET ROLE` from the existing superuser; roles stay `NOLOGIN`. |
| 4 | Test image → `pgvector/pgvector:pg17` (parity §7 + pgvector availability). |
| 5 | Idempotent role creation via guarded `DO` blocks; extensions via `IF NOT EXISTS`. |
| 6 | SQLAlchemy 2.x `Mapped[]` models + explicit `MetaData` naming convention. |
| 7 | UUID PKs with `gen_random_uuid()` server default (pgcrypto). |
| 8 | `downgrade base` drops triggers→functions→tables→roles→extensions for a truly empty reset. |
| 9 | DB tests skip when no DB reachable; fixture runs the real `alembic upgrade head`. |
| 10 | Minimal-but-coherent columns; correct FKs now, domain richness deferred to owning tiers. |
