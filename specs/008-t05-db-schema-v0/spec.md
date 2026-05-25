# Feature Specification: DB schema v0 + Alembic baseline + append-only enforcement (T05)

**Feature Branch**: `008-t05-db-schema-v0`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: "T05 — DB schema v0 + Alembic baseline + append-only enforcement" (from `docs/engineering/implementation-plan.md`, Tier 1 / W1–W2)

## Clarifications

### Session 2026-04-28

- Q: Does T05 create the two database roles (`techscreen_app`, `techscreen_migrator`), or assume infra (T06 Cloud SQL) provisions them? → A: T05's baseline migration **creates both roles idempotently** (guarded `CREATE ROLE` via a `DO $$ … $$` block, `NOLOGIN` by default) so the schema, the `REVOKE`/`GRANT` statements, and the §3 invariant tests all run standalone on a fresh local/CI Postgres without depending on T06. T06 later attaches `LOGIN` + a Secret-Manager-sourced password and wires Cloud SQL connectivity — it does not redefine the roles. Rationale: §3 enforcement is the entire point of T05; it cannot be tested if the role it revokes from does not yet exist. The roles must therefore be born with the schema, not with the infra.
- Q: Are `vw_effective_assessment` (the "latest correction wins" materialised view, ADR-019) and `annotated_turn_embedding` (the `vector(768)` table, ADR-007) part of T05? → A: **Deferred, both.** T05 ships the six append-only base tables and *enables* the `vector` extension, but does not create the embedding table (Roadmap H2, no consumer yet) nor the effective-assessment view (needs `assessment_correction` write semantics that land with the Assessor/Reviewer tiers). T05's scope is "every table later tiers need a foreign key into, plus the §3 guardrail" — not the derived/read artefacts built on top of them.
- Q: For the session-placeholder tables (`interview_session`, `position_template`, `interview_plan`), how complete are the columns? → A: **Minimal viable columns only** — a primary key, a `created_at`, and the foreign keys that other T05 tables or the rubric snapshot mechanism (T15) reference. Domain columns (status, candidate link, magic-link token, frozen `rubric_snapshot` JSONB, etc.) are added by the tier that owns each table. T05 creates the table so a foreign key can point at it; it does not finalise its shape.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the humans and AI sub-agents that build every later data-touching feature: `backend-engineer` writing the rubric importer (T08), Position Template CRUD (T12–T13), the orchestrator and agent services that write `turn_trace` / `assessment` (T18–T21), and the Reviewer UI that appends `assessment_correction` / `turn_annotation` (T35); `infra-engineer` provisioning Cloud SQL and the migration-approval gate (T06, T10); and — most importantly — the operators, reviewers, auditors, and compliance/legal staff who must reconstruct a months-old hiring decision long after the session ended. T05 is the **foundation every later row sits on**: until the schema exists and the append-only invariant is enforced at the database level, no audit-bearing feature can be trusted, and no later table has a foreign key to point at.

### User Story 1 — The database physically refuses to mutate audit history (Priority: P1)

A hiring decision is challenged six months later. Compliance asks: "What did the model originally score, what did the reviewer change, and when?" That question is only answerable if no row in the six audit tables was ever silently overwritten or deleted. Constitution §3 and ADR-019 require that corrections be *new rows*, never mutations — and that the guarantee is enforced by the database, not by code discipline that one careless `UPDATE` can break.

**Why this priority**: P1 — it is the entire reason T05 exists as a discrete task rather than "just add some tables". A single un-guarded `UPDATE` on `assessment` that ships to production destroys auditability retroactively and is reportable to leadership/legal. The cheapest moment to make mutation impossible is when the tables are born.

**Independent Test**: On a fresh database, connect as the application role and attempt `UPDATE` and `DELETE` against each of the six append-only tables. Every attempt is rejected — both by a trigger raising an exception and by the absence of the table-level grant. Connect as the migrator role and confirm the same statements succeed (so migrations can still evolve schema).

**Acceptance Scenarios**:

1. **Given** a fresh database at `head`, **When** the application role issues `UPDATE` against any of `turn_trace`, `assessment`, `assessment_correction`, `turn_annotation`, `audit_log`, `session_decision`, **Then** the statement is rejected with an `append-only: … not allowed on …` exception.
2. **Given** the same state, **When** the application role issues `DELETE` against any of the six tables, **Then** the statement is rejected.
3. **Given** the same state, **When** the application role issues `INSERT` against any of the six tables, **Then** the row is written (append is always allowed).
4. **Given** the same state, **When** the *migrator* role issues `UPDATE`/`DELETE` against those tables, **Then** the statements succeed (schema evolution and emergency forward-fix migrations remain possible).

---

### User Story 2 — A developer can build the entire schema from zero and reset it (Priority: P1)

Every downstream task (T05a, T06, T08, T12+) needs the schema to exist before it can be written or tested. A developer or CI runner must be able to take an empty Postgres and bring it to the full v0 schema with one documented command, and reverse it cleanly when resetting a local environment — without manual SQL, without leftover objects, and without a live cloud database.

**Why this priority**: Co-equal P1. T05 is the gate for T05a/T06/T08; if the schema cannot be created reproducibly and torn down on a laptop, the whole Tier-1 pipeline stalls and later tests become environment-dependent and flaky.

**Independent Test**: On an empty Postgres container, run the documented migrate-up command and observe every table, extension, role, trigger, and grant present. Run the documented migrate-down command and observe the database returns to empty (no orphaned tables, functions, or types). Run migrate-up a second time and confirm it succeeds without "already exists" errors.

**Acceptance Scenarios**:

1. **Given** an empty database, **When** the baseline migration is applied, **Then** all rubric, session-placeholder, and append-only tables exist, the `vector` and `pgcrypto` extensions are enabled, and both database roles exist.
2. **Given** a database at `head`, **When** the baseline migration is reversed to `base`, **Then** every object the migration created is removed and the database is empty.
3. **Given** a database where extensions/roles already exist, **When** the baseline migration is applied, **Then** it completes idempotently without failing on pre-existing extensions or roles.
4. **Given** a database at `head`, **When** a developer inserts a `stack` row inside a transaction and rolls back, **Then** no row persists — confirming normal transactional writes work for non-audit tables.

---

### User Story 3 — Later tiers have a stable schema to build foreign keys onto (Priority: P2)

The rubric tree (`stack → competency_block → competency → topic → level`, versioned by `rubric_tree_version`) and the session/plan placeholders (`interview_session`, `position_template`, `interview_plan`) must exist as real tables so that the rubric importer (T08), the rubric snapshot mechanism (T15), and the agent/session tiers can declare foreign keys against them. The relationships and read-only nature of the rubric tree must be encoded now to avoid a destructive migration later.

**Why this priority**: P2 — necessary for downstream work but not itself the audit-critical core. Getting the relationships right at baseline (and enabling pgvector/pgcrypto now) avoids the destructive DDL that constitution §10 makes expensive (an extra ADR + approval).

**Independent Test**: Inspect the schema and confirm the rubric tree's parent/child foreign keys and the `rubric_tree_version` linkage exist, and that each session-placeholder table has a primary key plus the foreign keys later tiers reference.

**Acceptance Scenarios**:

1. **Given** the schema at `head`, **When** the rubric tree is inspected, **Then** each level of the hierarchy references its parent and is associated with a `rubric_tree_version`.
2. **Given** the schema at `head`, **When** the session-placeholder tables are inspected, **Then** each has a primary key and a creation timestamp, and foreign keys resolve without error.
3. **Given** the schema at `head`, **When** the enabled extensions are listed, **Then** both `vector` and `pgcrypto` are present, so future embedding/UUID features need no destructive migration.

---

### Edge Cases

- **Migrator must retain mutation rights.** The `REVOKE` targets only the application role; the migrator role keeps `UPDATE`/`DELETE` so future forward-only migrations can backfill or restructure audit tables under human approval (§10).
- **Re-applying the baseline.** Extension creation uses `IF NOT EXISTS`; role creation is guarded — a second apply on a partially-initialised database must not error.
- **Downgrade completeness.** Reversing the baseline must also drop the trigger functions and any custom enum/types it created, not just the tables, so a re-upgrade starts clean.
- **Append after revoke.** Revoking `UPDATE`/`DELETE` must not accidentally revoke `INSERT` or `SELECT` from the application role.
- **Empty-prefix local role.** On a fresh local Postgres whose only role is the compose superuser, the migration must still create the app/migrator roles rather than assume they exist (see Assumptions).
- **PII boundary.** `audit_log` stores `actor_id`, `action`, `subject_hash`, `ts` only — never raw candidate PII (§15). The schema must make a PII column an obvious mistake, not a silent option.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST provide a single baseline migration that, applied to an empty database, creates the complete v0 schema (rubric tree, session placeholders, six append-only tables), enables the `vector` and `pgcrypto` extensions, and creates the application and migrator database roles.
- **FR-002**: The baseline migration MUST be reversible — reversing it returns the database to empty, removing every table, trigger, function, and type it created.
- **FR-003**: The baseline migration MUST be idempotent with respect to pre-existing extensions and roles — re-applying it on an already-initialised database MUST NOT fail.
- **FR-004**: The system MUST prevent the application role from issuing `UPDATE` or `DELETE` on any of the six append-only tables, enforced **both** by a database trigger that raises an exception **and** by a revoked table-level grant.
- **FR-005**: The application role MUST retain `INSERT` and `SELECT` on the append-only tables (append and read are always permitted).
- **FR-006**: The migrator role MUST retain `UPDATE` and `DELETE` on all tables so that human-approved forward-only migrations can evolve audit data.
- **FR-007**: The trigger that blocks mutation MUST raise a clearly identifiable, append-only-specific error message naming the operation and the table.
- **FR-008**: The rubric tree tables MUST encode the parent→child hierarchy (`stack → competency_block → competency → topic → level`) via foreign keys and MUST associate the tree with a `rubric_tree_version`.
- **FR-009**: Each session-placeholder table (`interview_session`, `position_template`, `interview_plan`) MUST have a primary key and a creation timestamp and MUST expose the foreign keys that other T05 tables or the rubric snapshot mechanism reference; finalising domain columns is explicitly out of scope.
- **FR-010**: `audit_log` MUST be limited to non-PII fields (`actor_id`, `action`, `subject_hash`, `ts`) per §15.
- **FR-011**: The migration MUST follow the forward-only, zero-downtime invariant (§10); the reversibility in FR-002 exists for local/CI resets and does not change the production forward-only posture.
- **FR-012**: The system MUST include automated tests proving the §3 invariant for each of the six append-only tables (one `UPDATE` and one `DELETE` rejection per table), plus a migration up/down round-trip test and a transactional insert/rollback test on a non-audit table.
- **FR-013**: A reviewer MUST be able to confirm, by reading the migration source, that `REVOKE UPDATE, DELETE` is applied to all six append-only tables for the application role.

### Key Entities *(include if feature involves data)*

- **Rubric tree** — read-only reference hierarchy: `stack`, `competency_block`, `competency`, `topic`, `level`, each linked to its parent, all versioned by `rubric_tree_version`. New rubric content creates a new version; existing nodes are never edited in place (ADR-018, §4).
- **user** — system accounts (recruiters, reviewers, admins) referenced by audit and decision rows. Not candidate PII storage.
- **Session placeholders** — `interview_session`, `position_template`, `interview_plan`: minimally-shaped tables that later tiers extend; present now so foreign keys resolve.
- **Append-only audit set (the six §3 tables)**:
  - `turn_trace` — every LLM call: inputs, outputs, latency, cost.
  - `assessment` — the Assessor's per-session, per-competency final score + confidence.
  - `assessment_correction` — reviewer overrides, each a new row referencing the `assessment` it corrects.
  - `turn_annotation` — reviewer per-turn quality marks.
  - `audit_log` — actor / action / subject_hash / ts for every state change (no PII, §15).
  - `session_decision` — the final hiring decision artefact with inputs and justification.
- **Database roles** — `techscreen_app` (application; `INSERT`/`SELECT` on audit tables, no `UPDATE`/`DELETE`) and `techscreen_migrator` (full DDL/DML for human-approved migrations).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: From an empty database, a single documented command brings the schema to the complete v0 state with 100% of the specified tables, extensions, and roles present.
- **SC-002**: A single documented command returns the database to empty with zero orphaned objects remaining.
- **SC-003**: 100% of mutation attempts (`UPDATE` and `DELETE`) by the application role against the six append-only tables are rejected; 100% of `INSERT`/`SELECT` attempts succeed.
- **SC-004**: All six append-only tables are covered by automated invariant tests (12 mutation-rejection assertions total — one `UPDATE` and one `DELETE` each), and the full suite passes in CI without a live cloud database.
- **SC-005**: A reviewer can confirm append-only coverage for all six tables by reading the migration source in under 5 minutes (every table's `REVOKE` and trigger is visible and greppable).
- **SC-006**: Applying the baseline twice in a row succeeds without error (idempotency verified).
- **SC-007**: Zero destructive DDL is required by any later Tier-1/Tier-2 task to add pgvector or UUID-default support, because both extensions are enabled at baseline.

## Assumptions

- **Role ownership boundary.** T05 creates `techscreen_app` and `techscreen_migrator` idempotently (guarded, `NOLOGIN`); T06 (Cloud SQL + Secret Manager) later attaches `LOGIN` + password and connectivity. This lets §3 enforcement be tested standalone now. *(If infra is expected to own role creation instead, this assumption must change before planning.)*
- **Local/CI database.** Tests run against the `pgvector/pgvector:pg17` container already defined in `docker-compose.yml` (`--profile db`) and `docker-compose.test.yml`; no live Cloud SQL is required.
- **Deferred derived artefacts.** `vw_effective_assessment` (ADR-019) and `annotated_turn_embedding` (ADR-007, `vector(768)`) are out of scope for T05; only the `vector` extension is enabled now.
- **Session-placeholder minimalism.** Placeholder tables carry only PK + timestamp + referenced foreign keys; their domain columns are owned by later tiers (e.g. `rubric_snapshot` JSONB by T15).
- **Candidate-PII tables not in scope.** `candidate`, `message`, `turn` (the PII-bearing tables in §15) are introduced by the candidate-session tier (Tier 5), not T05.
- **ADR reference correction.** pgvector is governed by **ADR-007** (and ADR-001 for the PG17 pin); the implementation-plan T05 entry's "ADR-008" reference is a typo (ADR-008 is hybrid prompt language) and will be reconciled in the plan-phase documentation-fix step.
- **UUID strategy.** Primary keys default to `gen_random_uuid()` from `pgcrypto`, consistent with the implementation-plan note; exact per-table key types are settled in `data-model.md` at plan time.
