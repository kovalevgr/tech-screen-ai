# Implementation Plan: Feature-flag infrastructure (T05a)

**Branch**: `009-t05a-feature-flag-infrastructure` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/009-t05a-feature-flag-infrastructure/spec.md`

## Summary

T05a lands the constitution-§9 dark-launch mechanism every later risky feature plugs into. In a single PR, in the order a reviewer should validate them:

1. **Schema contract** committed first (§14): `docs/contracts/feature-flag.schema.json` formalises the YAML entry shape (required fields, the `state ∈ {active, sunset}` enum, conditional `sunset_pr`/`sunset_date` when sunset). `configs/feature-flags.yaml` ships with an empty active list (no real flags yet — those are wired by their consuming PRs).
2. **Migration `alembic/versions/0002_feature_flags.py`** (additive, forward-only per §10, `down_revision='0001_baseline'`): creates the `feature_flag` table as **plain mutable** — **no** `reject_audit_mutation()` trigger and **no** `REVOKE UPDATE, DELETE` (this carve-out is FR-013, called out in the migration docstring AND in `app/backend/db/models/feature_flag.py` so a future contributor doesn't reflexively extend §3 protections to it). The migration ALSO adds an `AFTER INSERT OR UPDATE OR DELETE` trigger that calls `pg_notify('feature_flag_changed', COALESCE(NEW.name, OLD.name))` — structural to FR-003 / SC-003 (the 1-second cache-invalidation SLO needs the DB itself to wake listeners).
3. **`FeatureFlagService` at `app/backend/services/feature_flags.py`** — strict YAML-driven registry (unknown name raises `UnknownFeatureFlag`, FR-004), in-process per-flag cache with a 60-second TTL backstop, and a long-lived `asyncpg` LISTEN connection on channel `feature_flag_changed` that invalidates one cache entry per NOTIFY. Reconnect-with-backoff if the listener drops. The module-level `async def is_enabled(name, *, session_id=None) -> bool` is a thin wrapper over a singleton service constructed at FastAPI startup; tests inject the service directly.
4. **`scripts/check-feature-flag-registration.py`** — the bidirectional registration guard (FR-010, FR-011). It validates `configs/feature-flags.yaml` against the JSON Schema, scans `app/backend/` for `is_enabled("…")` / `is_enabled('…')` call sites, and asserts: every literal name is declared with `state: active`; every `state: active` YAML entry has at least one call site; every `state: sunset` entry has a matching row in `docs/engineering/feature-flags.md` with non-empty `sunset_pr` + `sunset_date`. Exits non-zero with a precise, actionable message on any violation. Wired both as a local pre-commit hook (new entry in `.pre-commit-config.yaml`) and in CI via the test container (T05's `COPY scripts ./scripts` carries it into the image already).
5. **GitHub Actions workflow `.github/workflows/sync-feature-flags.yml`** — triggered on `push` to `main` when `configs/feature-flags.yaml` changes (plus `workflow_dispatch` for manual reconciliation). Authenticates to Cloud SQL via Workload Identity Federation (§6 — no JSON SA key). On run: re-validates the YAML against the schema (defence in depth, FR-006 enforcement also at deploy-time), upserts each entry into `feature_flag` with `updated_by='configs-as-code'`, and emits a GitHub Actions warning annotation per orphan row found in DB-but-not-in-YAML (never deletes, per FR-009). **The WIF/Cloud-SQL live binding parameters (project, region, instance, IAM role) are placeholders T06 fills** — T05a ships the workflow file with documented placeholders and the auth scaffolding, T06 wires it to the actual Cloud SQL instance when it provisions one. A reviewer-facing note in the workflow file calls this boundary out explicitly.
6. **`docs/engineering/feature-flags.md`** — the human-readable flag index (FR-012): how-to (declare / flip / sunset / emergency-disable), an Active table (one row per active flag), and a Sunset table (one row per retired flag with `sunset_pr` back-reference and `sunset_date`). T05a ships the skeleton + one intentionally-archived "demonstration" sunset entry so the format is concrete from day one; sunset rows are forever (FR-011, §1).
7. **Tests**:
   - `app/backend/tests/db/test_feature_flag_table.py` — the §3 carve-out positive test: `UPDATE feature_flag` from `techscreen_app` succeeds (SC-009), and the table has neither the audit-table trigger nor the audit-table REVOKEs (catalog assertions on `pg_trigger` and `has_table_privilege`).
   - `app/backend/tests/services/test_feature_flags.py` — service end-to-end on live Postgres: declare flag in a temp YAML → row enabled=false → `is_enabled→false`; UPDATE row → cache invalidates within 1 second (SC-003); unknown name → typed `UnknownFeatureFlag`; listener reconnect after a forced drop.
   - `app/backend/tests/contracts/test_feature_flag_registration.py` — fixture-tree subprocess tests of the registration hook covering each FR-010/FR-011 failure mode (undeclared name, removed last call without sunset, sunset entry missing docs row, YAML schema violation) — each fixture exits non-zero with the message identifying the violator.

The PR adds **no** HTTP endpoint (the service is internal; consumers call `is_enabled` directly), **no** OpenAPI diff (the T02 regen-and-diff guardrail must stay byte-identical), **no** prompt content, **no** Docker / compose changes (the `db` profile already runs `alembic upgrade head` which now includes 0002), and ships **no** real flag — it ships the mechanism. Single-committer PR: `agent: backend-engineer`, `parallel: false`. The parallel fan-out it enables is later, on consumer features that need flags.

## Technical Context

**Language/Version**: Python 3.12 (unchanged; `pyproject.toml` pins `>=3.12,<3.13`).

**Primary Dependencies** added to `[project].dependencies`:

- `jsonschema >= 4.23, < 5` — pure-Python JSON Schema validator with the best error messages for our use case (compile-once-validate-once at startup + hook runs; speed is irrelevant, error clarity is). Research §1 documents the alternatives considered (`fastjsonschema` rejected for poorer errors; `jschon` rejected for smaller community).

No other new runtime deps. `pyyaml` and `asyncpg` already shipped in T01–T05.

**Dev dependencies**: none new (`pytest` + `pytest-asyncio` already configured).

**Storage**: Postgres 17 with the `pgvector` and `pgcrypto` extensions already enabled by T05's baseline. T05a adds the `feature_flag` table + one notify trigger; no new extensions.

**Testing**: `pytest` + `pytest-asyncio` (auto-mode). The new tests live under:
- `app/backend/tests/db/test_feature_flag_table.py` — gated by `db_available` (skips when no DB reachable, established T05 pattern).
- `app/backend/tests/services/test_feature_flags.py` — same DB gate; uses a temp-YAML pattern to test registry behaviour without touching `configs/feature-flags.yaml`.
- `app/backend/tests/contracts/test_feature_flag_registration.py` — subprocess invocations of `scripts/check-feature-flag-registration.py` against fixture trees on tmpfs.

**Target Platform**: Linux container (existing `dev` Docker target).

**Project Type**: Backend slice within the existing FastAPI monorepo. No frontend changes. No infra/Terraform changes (Cloud SQL provisioning + the workflow's WIF binding parameters are T06).

**Performance Goals**:
- Cache-invalidation freshness: < 1 second p95 from DB write to `is_enabled` reflecting the new value (FR-003 / SC-003), when the NOTIFY listener is healthy. Backstop of 60-second TTL when the listener is disconnected.
- Service startup: registry load from a ~10-entry YAML file completes in < 50 ms.
- `is_enabled` per-call latency: < 1 ms p95 cache hit; < 10 ms p95 cache miss (one DB row read).
- Sync workflow: full run (queue + auth + upsert) completes in < 5 minutes on a busy day (SC-002).

**Constraints**:
- **§3 carve-out** — `feature_flag` is mutable by design (FR-013); the migration MUST NOT attach `reject_audit_mutation()` to it and MUST NOT `REVOKE UPDATE, DELETE` from `techscreen_app`. The model file and migration docstring make this explicit so future contributors don't extend audit-table protections by reflex.
- **§5/§6 — no inline secrets** — the GHA workflow uses Workload Identity Federation (no JSON service-account key). `.env.example` gains no new key.
- **§10 — forward-only** — 0002 is purely additive; reversible `downgrade()` for local/CI resets only.
- **§14 — contract-first** — `docs/contracts/feature-flag.schema.json` and `configs/feature-flags.yaml` (skeleton) committed in this PR before any consumer ever calls `is_enabled`. The migration itself IS the runtime contract.
- **§16 — configs as code** — `configs/feature-flags.yaml` is the source of truth; admin/UI mutations are out of scope (Phase 2).
- **§18 — explicit orchestration** — single committer (`backend-engineer`), `parallel: false`; the parallel fan-out T05a enables happens on consumer features, not inside this PR.
- **OpenAPI diff is zero** — the service is internal (no route added); the T02 regen-and-diff guardrail must keep `app/backend/openapi.yaml` byte-identical.
- **mypy --strict clean** — every public symbol in `app/backend/services/feature_flags.py` is fully typed; the new SQLAlchemy model uses `Mapped[]` like T05's models.
- **Pre-commit guardrails** from T01–T05 (`gitleaks`, `detect-secrets`, `ruff`, `ruff-format`, `actionlint`, `check-yaml`, `check-toml`, `no-provider-sdk-imports`) all pass; T05a adds **one** new local hook (`feature-flag-registered`) without weakening any existing one.

**Scale/Scope**: Single PR, ≈ 16 new files (≈ 550 LOC source + ≈ 450 LOC tests + the JSON schema + the workflow + the index doc + the registration script). One committer (`agent: backend-engineer`), `parallel: false`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| §   | Principle                              | Applies to T05a?                                                                                                                                                                          | Status |
| --- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first    | Indirect — the audit value is in **preserved sunset history** (FR-011/SC-005) and the per-call gating trace surface (FR-014; wired by T21).                                                | Pass   |
| 2   | Deterministic orchestration            | Indirect — `is_enabled` returns a typed boolean an orchestrator (T20) can route on; no LLM is involved.                                                                                    | Pass   |
| 3   | Append-only audit trail                | **Intentional carve-out** — `feature_flag` IS mutable by design (FR-013). No `reject_audit_mutation()` trigger, no `REVOKE`. SC-009 is a positive test enforcing this. Code + migration docstrings flag this explicitly so a contributor cannot extend §3 protections to it by reflex. | Pass   |
| 4   | Immutable rubric snapshots             | N/A — no rubric code in T05a.                                                                                                                                                              | N/A    |
| 5   | No plaintext secrets                   | Yes — no secret added. The workflow uses WIF (no JSON SA key); `.env.example` gains no key.                                                                                                | Pass   |
| 6   | Workload Identity Federation only      | Yes — the GHA workflow authenticates via WIF; T05a ships the auth scaffolding, T06 wires the live binding (project/region/instance).                                                       | Pass   |
| 7   | Docker parity dev → CI → prod          | Yes — same image runs everywhere; `db` profile picks up 0002 automatically; no new build stage.                                                                                            | Pass   |
| 8   | Production-only topology               | Yes — the sync workflow runs against prod only (research §10); no staging environment is implied.                                                                                          | Pass   |
| 9   | Dark launch by default                 | **Primary purpose of T05a.** Provides the mechanism; default `enabled=false`; bidirectional registration enforced by the hook (FR-010); fast cross-instance propagation (FR-003).         | Pass   |
| 10  | Migration approval                     | Yes — 0002 is additive and forward-only; reversible downgrade is local/CI only. The CI `--sql` dry-run + `migration-approved` label mechanism is T10's; T05a ships a migration that passes. | Pass   |
| 11  | Hybrid language                        | Yes — all docstrings, log messages, schema descriptions, and the index doc are English; no candidate-facing text.                                                                          | Pass   |
| 12  | LLM cost and latency caps              | Indirect — flags will gate Vertex-touching features in Tier 3+; T05a itself makes no LLM call.                                                                                            | Pass   |
| 13  | Calibration never blocks merge         | N/A — no calibration in T05a.                                                                                                                                                              | N/A    |
| 14  | Contract-first for parallel work       | Yes — `docs/contracts/feature-flag.schema.json` + `configs/feature-flags.yaml` skeleton committed in this PR before any consumer fans out.                                                | Pass   |
| 15  | PII containment                        | Yes — `feature_flag` rows hold flag metadata only (name/owner/enabled/timestamps); no candidate PII; the service logs only `name` + `enabled`, never request body.                         | Pass   |
| 16  | Configs as code                        | Yes — `configs/feature-flags.yaml` is the source of truth; admin-UI mutation is Phase 2 (out of scope).                                                                                    | Pass   |
| 17  | Specifications precede implementation  | Yes — `speckit-specify` → this `speckit-plan`; implementation follows `speckit-tasks`.                                                                                                     | Pass   |
| 18  | Multi-agent orchestration is explicit  | Yes — `agent: backend-engineer`, `parallel: false`. Fan-out is on consumer features, post-merge.                                                                                          | Pass   |
| 19  | Rollback is a first-class operation    | Yes — T05a IS the rollback mechanism for risky features (flip off without a deploy). SC-007 quantifies the 60-second emergency disable path.                                              | Pass   |
| 20  | Floor, not ceiling                     | Pass.                                                                                                                                                                                      | Pass   |

**Gate result**: PASS. The §3 carve-out is intentional (FR-013) and explicitly documented; it is not a violation. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/009-t05a-feature-flag-infrastructure/
├── spec.md                                # Feature spec (speckit-specify)
├── plan.md                                # This file
├── research.md                            # Phase 0 — design-altitude decisions (10 numbered)
├── data-model.md                          # Phase 1 — feature_flag table, YAML entry, index doc shape
├── contracts/
│   └── plan-contract.md                   # Phase 1 — pointer to runtime contracts under the repo (schema, migration)
├── quickstart.md                          # Phase 1 — reviewer validation walkthrough (<10 min)
├── checklists/
│   └── requirements.md                    # From speckit-specify (passed)
└── tasks.md                               # Created by speckit-tasks (NOT this command)
```

### Source Code (repository root, after T05a merges)

```text
.
├── alembic/
│   └── versions/
│       └── 0002_feature_flags.py          # NEW — additive migration: table + notify trigger; NO §3 trigger, NO REVOKE; reversible downgrade
├── app/
│   └── backend/
│       ├── db/
│       │   └── models/
│       │       ├── __init__.py            # EDITED — import + export FeatureFlag so Base.metadata is complete
│       │       └── feature_flag.py        # NEW — SQLAlchemy model for autogen; docstring calls out §3 carve-out
│       ├── services/
│       │   ├── __init__.py                # NEW — package marker
│       │   └── feature_flags.py           # NEW — FeatureFlagService + module-level `is_enabled`, UnknownFeatureFlag error
│       ├── main.py                         # EDITED — FastAPI startup constructs the service + starts the listener task; shutdown disposes
│       └── tests/
│           ├── db/
│           │   └── test_feature_flag_table.py    # NEW — §3 carve-out positive test (SC-009)
│           ├── services/
│           │   ├── __init__.py            # NEW — package marker
│           │   └── test_feature_flags.py  # NEW — service e2e on live Postgres (SC-003 + unknown-name + listener reconnect)
│           └── contracts/
│               ├── __init__.py            # NEW — package marker
│               └── test_feature_flag_registration.py  # NEW — subprocess tests of the hook against fixture trees
├── configs/
│   └── feature-flags.yaml                  # NEW — empty active list + the one demonstration sunset entry; FORMAT per schema
├── docs/
│   ├── contracts/
│   │   └── feature-flag.schema.json        # NEW — JSON Schema for the YAML entry (committed contract per §14)
│   └── engineering/
│       └── feature-flags.md                # NEW — the human-readable flag index (active + sunset tables + how-to)
├── .github/
│   └── workflows/
│       └── sync-feature-flags.yml          # NEW — push-to-main triggered; WIF auth (T06 fills the live binding params)
├── scripts/
│   └── check-feature-flag-registration.py  # NEW — registration hook; called by pre-commit + CI; copied into image via T05's COPY scripts
├── .pre-commit-config.yaml                 # EDITED — add the new local hook `feature-flag-registered`
├── pyproject.toml                          # EDITED — add `jsonschema>=4.23,<5` to [project].dependencies
└── uv.lock                                  # EDITED — regenerated by `uv lock`
```

**Structure Decision**: The runtime code lives under a new `app/backend/services/` package; this is the first service module in the project, so its `__init__.py` becomes the future home of other services (e.g., the rubric service in T12+). The SQLAlchemy model for `feature_flag` sits in `app/backend/db/models/feature_flag.py` alongside the T05 models — strictly to keep `Base.metadata` complete for Alembic autogenerate; the runtime `is_enabled` path uses raw SQL via asyncpg (no ORM session per call) for low overhead. The JSON Schema contract lives in `docs/contracts/` (project-level, as the user input specified) — the spec-dir `contracts/plan-contract.md` is a plan-time pointer document, NOT a duplicated schema.

### Task labelling (for §18 / `/speckit-tasks`)

| Task slice                                                              | Agent              | Parallel? | Depends on                                       | Contract reference                                       |
| ---------------------------------------------------------------------- | ------------------ | --------- | ----------------------------------------------- | -------------------------------------------------------- |
| `pyproject.toml` `jsonschema` dep + `uv lock`                          | `backend-engineer` | false     | T01 (`pyproject.toml` exists)                    | research §1                                              |
| `docs/contracts/feature-flag.schema.json`                              | `backend-engineer` | false     | spec committed                                   | the schema IS the contract                               |
| `configs/feature-flags.yaml` skeleton (+ demonstration sunset entry)   | `backend-engineer` | false     | schema                                           | conforms to the schema                                   |
| `app/backend/db/models/feature_flag.py` (+ `__init__.py` re-export)    | `backend-engineer` | false     | T05 db base/mixins                               | data-model §FeatureFlag                                  |
| `alembic/versions/0002_feature_flags.py` (table + notify trigger)      | `backend-engineer` | false     | model committed                                  | data-model §FeatureFlag + research §2                    |
| `alembic/versions/0002_feature_flags.py` (reversible downgrade)        | `backend-engineer` | false     | same file                                        | (same migration)                                          |
| `app/backend/services/feature_flags.py` (registry, cache, error types) | `backend-engineer` | false     | jsonschema dep + YAML committed                  | data-model §Service contract                              |
| `app/backend/services/feature_flags.py` (LISTEN + invalidation)        | `backend-engineer` | false     | service registry + migration                     | research §2/§3/§4                                        |
| `app/backend/main.py` startup/shutdown wiring                          | `backend-engineer` | false     | service                                          | n/a                                                       |
| `scripts/check-feature-flag-registration.py`                           | `backend-engineer` | false     | schema + YAML + docs skeleton                    | research §6/§8                                            |
| `.pre-commit-config.yaml` add new local hook                           | `backend-engineer` | false     | script                                           | mirrors T04's no-provider-sdk hook                        |
| `.github/workflows/sync-feature-flags.yml`                             | `backend-engineer` | false     | schema + YAML                                    | research §5                                              |
| `docs/engineering/feature-flags.md` skeleton + demonstration sunset    | `backend-engineer` | false     | schema + YAML                                    | FR-012                                                    |
| DB tests (`test_feature_flag_table.py` — §3 carve-out positive)         | `backend-engineer` | false     | migration                                        | SC-009                                                    |
| Service tests (`test_feature_flags.py` — e2e, invalidation, errors)    | `backend-engineer` | false     | service + migration                              | SC-003 + FR-004 + research §7                            |
| Hook tests (`test_feature_flag_registration.py` — five failure modes)   | `backend-engineer` | false     | hook script                                      | SC-006                                                    |

All T05a slices are sequential inside one PR; no sub-agent fan-out from inside T05a. The parallelism boundary is "T05a as a whole → afterwards, every consumer of `is_enabled`".

## Phase 0 — Outline & Research

Research output: [research.md](./research.md). The spec has zero `[NEEDS CLARIFICATION]` markers; phase 0 settles ten implementation-altitude decisions:

1. **JSON Schema validator library** — `jsonschema >= 4.23` over `fastjsonschema` / `jschon`. Error-message quality > speed; pure-Python; mature community; size acceptable.
2. **LISTEN/NOTIFY payload shape** — payload carries the flag name (`COALESCE(NEW.name, OLD.name)`), enabling per-flag invalidation instead of cache-wide flush.
3. **asyncpg LISTEN lifecycle** — dedicated long-lived connection outside the engine pool; owned by FastAPI startup; reconnect-with-exponential-backoff on drop; cancelled on shutdown so no socket leaks in tests.
4. **Cache shape** — plain `dict[str, (value, expires_at)]` with a single `asyncio.Lock` around writes; per-flag TTL (each entry has its own expiry); reads are lock-free.
5. **GHA workflow ↔ Cloud SQL via WIF** — `google-github-actions/auth` issues a short-lived token, then Cloud SQL Auth Proxy opens an authenticated socket. T05a ships the workflow with documented placeholders (project, region, instance) that T06 fills.
6. **Hook script location & invocation** — `scripts/check-feature-flag-registration.py`, called by a `language: system` pre-commit hook (mirror of T04's `no-provider-sdk-imports` pattern) and by CI inside the test image (the script is already in the image via T05's `COPY scripts ./scripts`).
7. **Sub-second invalidation testing without flakiness** — `asyncio.wait_for(loop_until_match, timeout=1.0)` with a tight poll interval; the 1-second SLO has generous headroom over typical NOTIFY round-trip (<10 ms locally).
8. **Sunset detection algorithm** — full-tree post-state check (no git-diff awareness): every `state: active` YAML entry must have ≥ 1 call site; every `state: sunset` entry must have a docs row. Simpler than git-diff and equally enforces the invariant.
9. **YAML entry schema** — `name`/`owner`/`default`/`description`/`state` required; `default_value` optional (JSONB on the table); `sunset_pr` + `sunset_date` required only when `state=sunset` (JSON Schema `if/then/else`).
10. **Workflow target environments** — prod only (no staging — §8). Local devs use direct SQL or invoke the upsert script ad-hoc; the workflow exists for the canonical PR-driven flow.

All ten decisions are resolved in `research.md` with Decision, Rationale, and Alternatives Considered.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T05a's entities are:
- The runtime `feature_flag` table (mutable; columns + the notify trigger).
- The YAML entry schema (fields, conditional `sunset_*` requirements).
- The human-readable index document structure (Active + Sunset tables + how-to sections).
- The explicit cross-reference back to T05's data-model.md confirming that `feature_flag` is NOT in the §3 set.

### Contracts

See [contracts/plan-contract.md](./contracts/plan-contract.md). This is a plan-time pointer document — the actual contract artefacts live at the repo root:
- `docs/contracts/feature-flag.schema.json` is the YAML entry contract (FR-006).
- `alembic/versions/0002_feature_flags.py` is the runtime contract (table + notify trigger).
- The service surface (`async def is_enabled(name, *, session_id=None) -> bool` + `class UnknownFeatureFlag(Exception)`) is the consumer-facing contract; downstream consumer PRs depend on it.

### Quickstart

See [quickstart.md](./quickstart.md) — reviewer-facing walkthrough that validates T05a end-to-end in under 10 minutes: declare a fixture flag, observe the workflow upsert it, flip via SQL and observe sub-second `is_enabled` change, run the hook against fixture failure trees, prove SC-009 with a positive `UPDATE feature_flag` from `techscreen_app`.

### Agent context update

`CLAUDE.md` carries no `<!-- SPECKIT START/END -->` markers (verified earlier; same as T05). No auto-generated block is reintroduced. **No `CLAUDE.md` edit in this step.**

### Re-evaluate Constitution Check (post-design)

The Phase 0/1 commitments (`jsonschema 4.23`, NOTIFY payload = flag name, dedicated asyncpg LISTEN connection, dict-based per-flag cache with 60s TTL backstop, WIF for the workflow, full-tree post-state hook algorithm, prod-only workflow scope) are all consistent with §3 (carve-out is explicit, not violated), §5, §6, §8, §9, §10, §14, §16, §17, §18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations. The §3 carve-out is intentional and explicitly motivated (FR-013); it is encoded in code comments, the migration docstring, and a positive test (SC-009).

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
