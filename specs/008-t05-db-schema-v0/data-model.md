# Phase 1 Data Model: T05 — DB schema v0

Scope note: columns are **minimal-but-coherent** (research §10). Every table has a UUID PK (`gen_random_uuid()` server default, pgcrypto) and, unless noted, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Domain columns named by later tiers are listed under *Deferred* and are **not** created by T05.

Legend — **Lifecycle**: `read-only tree` (written only by the T08 importer as new versions; never edited in place — §4/ADR-018), `placeholder` (extended by a later tier), `append-only` (§3 — INSERT/SELECT only for the app role).

---

## Base infrastructure

### `Base` (`app/backend/db/base.py`)
- `DeclarativeBase` subclass carrying a `MetaData` with the naming convention from research §6.
- `target_metadata = Base.metadata` is what `alembic/env.py` imports.

### Mixins (`app/backend/db/models/_mixins.py`)
- `UUIDPk` — `id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))`.
- `TimestampCreated` — `created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())`.

### Session factory (`app/backend/db/session.py`)
- `create_async_engine(settings.database_url)` + `async_sessionmaker`. Used by **app runtime in later tiers**, not by migrations. No models import it.

---

## Rubric read-only tree  *(Lifecycle: read-only tree — §4, ADR-018)*

### `rubric_tree_version`
| Column | Type | Notes |
| ------ | ---- | ----- |
| `id` | UUID PK | |
| `label` | TEXT NOT NULL | human label, e.g. `"2026-Q2"` |
| `is_active` | BOOLEAN NOT NULL DEFAULT false | at most one active version (enforced in app/importer logic, not a DB constraint at T05) |
| `created_at` | TIMESTAMPTZ | |

Every tree node below carries `rubric_tree_version_id` FK → `rubric_tree_version.id` so a whole tree is addressable by version (snapshotting in T15 copies by version).

### `stack`  — top of the tree (e.g. "Backend Python")
`id` PK · `rubric_tree_version_id` FK · `name TEXT NOT NULL` · `created_at`

### `competency_block` — groups competencies within a stack
`id` PK · `rubric_tree_version_id` FK · `stack_id` FK → `stack.id` · `name TEXT NOT NULL` · `position INTEGER NOT NULL DEFAULT 0` · `created_at`

### `competency` — a scored competency
`id` PK · `rubric_tree_version_id` FK · `competency_block_id` FK → `competency_block.id` · `name TEXT NOT NULL` · `created_at`

### `topic` — a probe area within a competency
`id` PK · `rubric_tree_version_id` FK · `competency_id` FK → `competency.id` · `name TEXT NOT NULL` · `created_at`

### `level` — proficiency descriptor for a competency
`id` PK · `rubric_tree_version_id` FK · `competency_id` FK → `competency.id` · `rank SMALLINT NOT NULL` (e.g. 1–5) · `descriptor TEXT NOT NULL` · `created_at`

*Deferred*: weightings, scoring anchors, localisation columns (owned by T08/rubric tooling).

---

## Identity

### `user`  *(Lifecycle: placeholder)*
| Column | Type | Notes |
| ------ | ---- | ----- |
| `id` | UUID PK | |
| `subject` | TEXT NOT NULL UNIQUE | external SSO subject id (Identity Platform, T07) — **not** candidate PII; staff only |
| `role` | TEXT NOT NULL | `"recruiter" \| "reviewer" \| "admin"` (free-text now; enum/CHECK owned by T07) |
| `created_at` | TIMESTAMPTZ | |

`user` is referenced by `audit_log.actor_id` and `session_decision`. Staff accounts only; candidate identity lives in the Tier-5 `candidate` table (§15), **not** here.
*Deferred*: display name, email handling, last-login (T07).

---

## Session placeholders  *(Lifecycle: placeholder — minimal per spec Clarification)*

### `position_template`
`id` PK · `created_at`. *Deferred*: name, stack link, JD text, rubric selection (T12).

### `interview_session`
`id` PK · `position_template_id` FK → `position_template.id` (NULLABLE) · `created_at`.
*Deferred*: `rubric_snapshot JSONB NOT NULL` (T15, §4), candidate link (Tier 5), status enum, magic-link token (T28), timestamps for lifecycle.

### `interview_plan`
`id` PK · `interview_session_id` FK → `interview_session.id` (NULLABLE) · `created_at`.
*Deferred*: plan JSON, freeze flag, planner trace link (T24/T25).

---

## Append-only audit set  *(Lifecycle: append-only — §3, ADR-019)*

All six carry the `reject_audit_mutation()` `BEFORE UPDATE OR DELETE` trigger and `REVOKE UPDATE, DELETE` from `techscreen_app`.

### `turn_trace` — one row per LLM call
`id` PK · `interview_session_id` FK → `interview_session.id` (NULLABLE) · `created_at`.
*Deferred but reserved by T04's `TraceRecord` shape (written in T21)*: `agent`, `model`, `model_version`, `outcome`, `attempts`, `latency_ms`, `cost_usd NUMERIC`, `prompt_sha`. T05 creates the table + §3 guard; T21 adds the columns via a forward migration. **Decision point flagged for tasks/clarify**: whether to seed these columns now (cheap, matches T04's committed `TraceRecord`) or defer. Default: defer to keep T05 minimal; revisit in `speckit-tasks`.

### `assessment` — Assessor output, per session × competency
`id` PK · `interview_session_id` FK → `interview_session.id` · `competency_id` FK → `competency.id` · `score SMALLINT NOT NULL` · `confidence NUMERIC(4,3) NOT NULL` · `created_at`.

### `assessment_correction` — reviewer override (new row, never a mutation)
`id` PK · `assessment_id` FK → `assessment.id` (the corrected row — ADR-019) · `corrected_score SMALLINT NOT NULL` · `corrected_by` FK → `user.id` · `created_at`.

### `turn_annotation` — reviewer per-turn quality mark
`id` PK · `turn_trace_id` FK → `turn_trace.id` · `annotated_by` FK → `user.id` · `created_at`.
*Deferred*: label/comment columns (T35).

### `audit_log` — actor/action/subject for every state change *(§15: NO PII)*
`id` PK · `actor_id` FK → `user.id` (NULLABLE for system actions) · `action TEXT NOT NULL` · `subject_hash TEXT NOT NULL` (hashed reference, never raw subject) · `ts TIMESTAMPTZ NOT NULL DEFAULT now()`.
Note: uses `ts` (named in the implementation-plan) as its event timestamp; no separate `created_at`.

### `session_decision` — final hiring decision artefact
`id` PK · `interview_session_id` FK → `interview_session.id` · `decided_by` FK → `user.id` · `created_at`.
*Deferred*: decision enum, justification text, report link (T37).

---

## Database roles

### `techscreen_app`  *(NOLOGIN at T05; LOGIN+password in T06)*
- `GRANT INSERT, SELECT` on the six append-only tables; full DML on non-audit tables (rubric/session — though the app rarely writes the read-only tree).
- `REVOKE UPDATE, DELETE` on the six append-only tables.
- The role the FastAPI runtime connects as in prod (T06 wiring). In dev/test today the app still connects as the `techscreen` superuser; hardening the runtime DSN to `techscreen_app` is T06.

### `techscreen_migrator`  *(NOLOGIN at T05; LOGIN+password in T06)*
- Full DDL + DML on all tables. Exempt from the append-only trigger (via `current_user` check) so human-approved forward-only migrations (§10) can backfill/restructure audit data.

---

## Trigger function

### `reject_audit_mutation()` — PL/pgSQL, shared by all six triggers
```text
IF current_user = 'techscreen_migrator' THEN
    RETURN COALESCE(NEW, OLD);          -- allow migrations
END IF;
RAISE EXCEPTION 'append-only: % not allowed on %', TG_OP, TG_TABLE_NAME;
```
Wired as `BEFORE UPDATE OR DELETE ON <table> FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation()` on each append-only table.

---

## Extensions enabled at baseline
- `vector` (pgvector) — ADR-007; enables future `vector(768)` embeddings (`annotated_turn_embedding`, H2) with no destructive migration. **No vector column created in T05.**
- `pgcrypto` — supplies `gen_random_uuid()` for all PKs.

---

## Relationship summary (FK directions)

```text
rubric_tree_version ──< stack ──< competency_block ──< competency ──< topic
                                                          └──< level
position_template ──< interview_session ──< interview_plan
interview_session ──< turn_trace ──< turn_annotation
interview_session ──< assessment ──< assessment_correction
interview_session ──< session_decision
competency ──< assessment
user ──< audit_log.actor_id, assessment_correction.corrected_by,
         turn_annotation.annotated_by, session_decision.decided_by
```
