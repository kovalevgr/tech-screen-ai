---
description: "Task list for T05a — Feature-flag infrastructure (§9 dark-launch enabler)"
---

# Tasks: Feature-flag infrastructure (T05a)

**Input**: Design documents from `specs/009-t05a-feature-flag-infrastructure/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: INCLUDED — spec explicitly requires the hook-fixture matrix (SC-006), the §3 carve-out positive test (SC-009), and the sub-second propagation test (SC-003).

**Agent / parallelism**: every task is `agent: backend-engineer`, executed sequentially in one PR. `[P]` marks tasks that touch *different files* and may be written back-to-back without ordering hazards; it does **not** authorise sub-agent fan-out (constitution §18 — `parallel: false` for T05a as a whole).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the one new dependency `jsonschema 4.23` so every downstream module that imports it (the service, the hook, the workflow's upsert script) can do so.

- [x] T001 Add `jsonschema>=4.23,<5` to `[project].dependencies` in `pyproject.toml`; run `uv lock` to regenerate `uv.lock` (research §1). Inside Docker: `docker run --rm -v "$PWD":/w -w /w ghcr.io/astral-sh/uv:0.4.25-python3.12-bookworm uv lock`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Author the structural contracts (schema, YAML skeleton, SQLAlchemy model, package markers) every user story depends on. Nothing here ships behaviour — it's the substrate the stories build on.

**⚠️ CRITICAL**: No user story can be validated until this phase is complete.

- [x] T002 Create `docs/contracts/feature-flag.schema.json` — JSON Schema draft 2020-12 for the YAML entry (research §9): required `name` (snake_case regex `^[a-z][a-z0-9_]{2,63}$`), `owner`, `default` (bool), `description`, `state` (enum `active|sunset`); optional `default_value`; `if state == "sunset"` → required `sunset_pr` (`^#\\d+$`) + `sunset_date` (date). The file lives under `docs/contracts/` per FR-006 and the user input.
- [x] T003 Create `configs/feature-flags.yaml` skeleton — top-level `flags:` list with **zero active entries** + **one demonstration sunset entry** `example_demonstration` so the format is concrete from day one. Must validate against the schema from T002. (Sunset entries remain forever — FR-011.)
- [x] T004 [P] Create `app/backend/db/models/feature_flag.py` — SQLAlchemy 2.x `Mapped[]` model for `feature_flag` (columns per data-model.md §feature_flag). **Docstring MUST call out the §3 carve-out explicitly** (FR-013) so a future contributor doesn't add audit-table protections by reflex.
- [x] T005 Edit `app/backend/db/models/__init__.py` to import + export `FeatureFlag` so `Base.metadata` is complete (Alembic autogenerate parity — even though 0002 is hand-written, future autogen must produce zero diff).
- [x] T006 [P] Create `app/backend/services/__init__.py` — empty package marker (the first service module in the project; future T12+ services land alongside).
- [x] T007 [P] Create `app/backend/tests/services/__init__.py` and `app/backend/tests/contracts/__init__.py` — empty package markers for the two new test sub-packages.

**Checkpoint**: schema contract + YAML skeleton + model + package markers exist. User-story implementation can now begin.

---

## Phase 3: User Story 1 — A risky feature ships dark by default (Priority: P1) 🎯 MVP

**Goal**: Declaring a flag in YAML produces a DB row with `enabled=false`; `is_enabled` returns `false`; unknown name raises a typed error. The `feature_flag` table is **mutable** (no §3 trigger, no REVOKE — FR-013).

**Independent Test**: `alembic upgrade head` creates `feature_flag` with full GRANTs to both roles and **no** `reject_audit_mutation` trigger; `UPDATE feature_flag` from `techscreen_app` succeeds (SC-009); a fresh service against an empty DB returns `false` for a declared flag and raises `UnknownFeatureFlag` for an undeclared one.

### Implementation for User Story 1

- [x] T008 [US1] Create `alembic/versions/0002_feature_flags.py` (revision `"0002_feature_flags"`, `down_revision="0001_baseline"`). `upgrade()` creates the `feature_flag` table (columns per data-model.md §feature_flag, with a `BEFORE UPDATE` trigger to maintain `updated_at = now()`). **NO** `reject_audit_mutation()` trigger, **NO** `REVOKE UPDATE, DELETE` (deliberate carve-out per FR-013 — call this out in the migration docstring). `GRANT SELECT, INSERT, UPDATE, DELETE` to **both** `techscreen_app` and `techscreen_migrator`. Reversible `downgrade()` drops the table cleanly.
- [x] T009 [US1] Create `app/backend/services/feature_flags.py` (first slice — registry + cache + errors only, **no** LISTEN yet): YAML loader that parses `configs/feature-flags.yaml`, validates it against the schema (`jsonschema`), and builds a strict in-memory registry keyed by `name`. `class UnknownFeatureFlag(Exception)`. `class FeatureFlagService` with `async def is_enabled(name: str, *, session_id: UUID | None = None) -> bool` — cache hit returns immediately; cache miss reads the single row from `feature_flag` and caches it with a 60-s TTL. Module-level `is_enabled` is a thin wrapper over a singleton initialised by `main.py`. Unknown name (not in registry) raises `UnknownFeatureFlag` immediately, before any DB call (FR-004).
- [x] T010 [US1] Edit `app/backend/main.py` to construct the `FeatureFlagService` singleton in a FastAPI startup hook (load registry; no listener yet). The startup error path raises with a clear message if the YAML fails schema validation, so the backend refuses to boot on a malformed source-of-truth file.

### Tests for User Story 1

- [x] T011 [P] [US1] Create `app/backend/tests/db/test_feature_flag_table.py` — gated by the existing `db_available` fixture; asserts `feature_flag` exists after `alembic upgrade head`; asserts **no** trigger named like the audit guard (`SELECT tgname FROM pg_trigger WHERE tgrelid = 'feature_flag'::regclass` must not include `reject_audit_mutation`); asserts `has_table_privilege('techscreen_app', 'feature_flag', 'UPDATE')` and `'DELETE'` both return true; positive end-to-end as `techscreen_app`: `INSERT` → `UPDATE` → `DELETE` all succeed (SC-009, FR-013).
- [x] T012 [P] [US1] Create `app/backend/tests/services/test_feature_flags.py` (first batch only — registry + unknown-name + default-false; the propagation tests land in US2): `test_unknown_flag_raises` (FR-004); `test_declared_flag_starts_disabled` (US1 #1, #2); `test_yaml_schema_violation_refuses_startup` (validation at construction time).

**Checkpoint**: Constitution §9 dark-launch invariant is enforceable and proven on the §3-carved-out table — the MVP of T05a.

---

## Phase 4: User Story 2 — An operator flips a flag without a deploy (Priority: P1)

**Goal**: A DB-side write (PR-driven workflow OR direct emergency SQL) propagates to every running backend instance within 1 second, with no restart/redeploy.

**Independent Test**: Write a `feature_flag` row → `is_enabled` returns `false`; `UPDATE` the row → `is_enabled` returns `true` within 1 second (SC-003). Listener disconnect followed by reconnect leaves the service correct.

### Implementation for User Story 2

- [x] T013 [US2] Edit `alembic/versions/0002_feature_flags.py` — add an `AFTER INSERT OR UPDATE OR DELETE` trigger on `feature_flag` that calls `pg_notify('feature_flag_changed', COALESCE(NEW.name, OLD.name))` (research §2). Add the matching `DROP TRIGGER` and `DROP FUNCTION` to `downgrade()` so round-trip stays clean.
- [x] T014 [US2] Edit `app/backend/services/feature_flags.py` — add a long-lived dedicated `asyncpg.Connection` (outside the engine pool) that LISTENs on channel `feature_flag_changed`; on NOTIFY, evict the single matching cache entry by name (research §2/§4). Implement reconnect with exponential backoff (1s → 30s cap, research §3) and structured logging at INFO on each (re)connect. While disconnected, the cache silently falls back to the 60-s TTL backstop.
- [x] T015 [US2] Edit `app/backend/main.py` — in the FastAPI startup hook, start the LISTEN task as a background asyncio Task after the registry loads; in the shutdown hook, cancel the task and dispose the listener connection so tmpfs-based tests don't leak sockets (research §3).
- [x] T016 [US2] [P] Create `.github/workflows/sync-feature-flags.yml` — `on: push` to `main` with `paths: [configs/feature-flags.yaml]` plus `workflow_dispatch`. Job uses `google-github-actions/auth@v2` with `<TODO-T06: workload_identity_provider>` and `<TODO-T06: service_account>` placeholders; Cloud SQL Auth Proxy step with `<TODO-T06: project/region/instance>` placeholders. An upsert step runs an inline Python script that re-validates YAML against the schema (defence in depth, FR-006), upserts each entry with `updated_by='configs-as-code'`, and emits one GitHub Actions `::warning::` annotation per orphan row found in DB-but-not-in-YAML (does NOT delete, FR-009). The upsert step is wrapped in an `if: <placeholders resolved>` guard so the workflow file is structurally valid + `actionlint`-clean while remaining inert until T06 fills the bindings.

### Tests for User Story 2

- [x] T017 [P] [US2] Extend `app/backend/tests/services/test_feature_flags.py` — second batch (the live-DB propagation tests): `test_update_propagates_under_one_second` uses `asyncio.wait_for(loop_until_match, timeout=1.0)` with a 10-ms poll interval (research §7) — `INSERT` row, observe `is_enabled=false`; `UPDATE` row to `enabled=true`; assert `is_enabled→true` within 1 s (SC-003). `test_listener_reconnects_after_drop` forces the listener connection closed and asserts a later UPDATE is still observed after backoff. `test_delete_invalidates_cache` covers the AFTER-DELETE trigger path.

**Checkpoint**: SC-003 propagation SLO is proven end-to-end on live Postgres; the GHA workflow file is structurally valid and waiting on T06 to fill its WIF binding.

---

## Phase 5: User Story 3 — Unregistered flag usage is rejected before merge (Priority: P1)

**Goal**: Adding `is_enabled("undeclared_name")` to backend code is rejected by pre-commit locally and CI before it can be merged; removing the last call without flipping the YAML entry to `state: sunset` is rejected symmetrically.

**Independent Test**: Five fixture trees (undeclared name; orphan-active YAML; sunset entry missing docs row; YAML schema violation; orphan docs row) all fail the hook with precise, actionable messages; a clean tree exits 0.

### Implementation for User Story 3

- [x] T018 [US3] Create `scripts/check-feature-flag-registration.py` — Python 3.12 script. Loads `configs/feature-flags.yaml`; validates against `docs/contracts/feature-flag.schema.json` (FR-006). Regex-scans `app/backend/**/*.py` for `is_enabled\(["']([^"']+)["']\)` literals (research §6/§8). Parses the Active + Sunset markdown tables from `docs/engineering/feature-flags.md`. Enforces (research §8 algorithm):
  - every literal name → declared in YAML with `state="active"` (FR-010a; "typo" failure mode);
  - every YAML `state="active"` entry → at least one call site (FR-010b; "orphan declaration");
  - every YAML `state="sunset"` entry → non-empty `sunset_pr` + `sunset_date` (FR-011);
  - every YAML `state="sunset"` entry → row in docs Sunset table (FR-011);
  - every docs Sunset row → matching YAML `state="sunset"` entry (FR-011; "orphan docs row").
  Exits non-zero with a precise message (file + line/path + remediation) on any violation. Script is executable (`chmod +x`).
- [x] T019 [US3] Edit `.pre-commit-config.yaml` — add one new local hook `id: feature-flag-registered`, `name: feature flag registration (backend)`, `language: system`, `entry: python scripts/check-feature-flag-registration.py`, `files:` matching `^(app/backend/.+\\.py|configs/feature-flags\\.yaml|docs/engineering/feature-flags\\.md|docs/contracts/feature-flag\\.schema\\.json)$`. Mirror the T04 `no-provider-sdk-imports` hook shape.

### Tests for User Story 3

- [x] T020 [P] [US3] Create `app/backend/tests/contracts/test_feature_flag_registration.py` — five fixture subprocesses, each building a fixture tree on `tmp_path` and invoking the hook script as a subprocess; each fixture asserts non-zero exit + the substring of the expected error message:
  1. **undeclared name** → `is_enabled("typo_flag")` without YAML entry: `'typo_flag' is referenced in code but not declared`.
  2. **orphan active YAML** → YAML `state: active` for `orphan` but no call site: `'orphan' is state=active but no call site`.
  3. **sunset missing docs row** → YAML `state: sunset` for `retired` but docs Sunset table has no matching row: `'retired' is state=sunset but missing from docs/engineering/feature-flags.md`.
  4. **YAML schema violation** → entry with `state: pending` (not in enum): error message includes the JSON path of the failing field.
  5. **orphan docs row** → docs Sunset row for `ghost` but no YAML entry: `'ghost' appears in docs but not in configs/feature-flags.yaml`.
  Plus a positive test: the **real** committed tree (post-T05a) passes the hook with exit 0 (SC-004 baseline).

**Checkpoint**: SC-006 enforcement is proven for every documented failure mode; SC-004 baseline holds on the clean tree.

---

## Phase 6: User Story 4 — Sunset history is preserved across the project's lifetime (Priority: P2)

**Goal**: Every flag the project has ever had (active + sunset) is discoverable from one human-readable file forever; sunset entries are never silently deleted.

**Independent Test**: After applying T05a, `docs/engineering/feature-flags.md` lists the one demonstration sunset entry (`example_demonstration`) with `sunset_pr` + `sunset_date`; the hook accepts the clean tree. The DB row for an orphan flag (one in DB but not in YAML) survives the sync workflow (FR-009) — covered by inspecting the workflow YAML.

### Implementation for User Story 4

- [x] T021 [US4] Create `docs/engineering/feature-flags.md` — full skeleton: a "How-to" section with four short blocks (declare / flip / sunset / emergency disable, ≤ 30 lines total per data-model.md §Human-readable index document); an empty "Active flags" table with the four-column header (`name | owner | default | description`); a "Sunset flags" table with the four-column header (`name | sunsetted in | date | description`) and **one** row for the demonstration entry `example_demonstration` whose `sunsetted in` and `date` match the YAML's `sunset_pr` and `sunset_date` from T003. The hook (T018) enforces that this row stays in sync with the YAML forever (FR-011).

**Checkpoint**: Sunset preservation is encoded structurally — the hook from US3 rejects any future deletion of a sunset entry, and the demonstration entry proves the format is in use from day one.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [x] T022 [P] Edit `README.md` — add a single short subsection ("Feature flags") with a one-paragraph summary and a link to `docs/engineering/feature-flags.md`. Two sentences max; this is discoverability, not duplication.
- [x] T023 Run guardrails inside Docker: `ruff check app/backend` + `mypy --strict app/backend` + `python -m app.backend.generate_openapi --check` (byte-identical — no route added). `pre-commit run --all-files` must pass (the new hook runs against the clean tree → exit 0). Build + run the full test suite under the `db` profile: `docker compose -f docker-compose.test.yml --profile db run --rm backend sh -c "alembic upgrade head && pytest app/backend/tests -v"`.
- [x] T024 Walk through `quickstart.md` end-to-end (steps 1–7) and tick SC-001 (declare a fixture flag in < 10 min) through SC-009 in the checklist at the bottom. Capture timing for SC-002 / SC-007 expectations from the workflow file (live timing for SC-002 lands after T06).

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)** → no deps; T001 first (jsonschema must be installed before any module imports it).
- **Foundational (P2)** → depends on Setup. T002 (schema) blocks T003 (YAML validates against it). T004 + T005 (model + re-export) block T008 (migration imports the model via env.py for autogen parity). T006/T007 (package markers) block their stories' tests.
- **US1 (P3)** → depends on Foundational. T008 → T009 (migration must exist before the service can read the table). T010 follows T009 (main.py wires the service). Tests T011/T012 are `[P]` with each other (different files).
- **US2 (P4)** → depends on US1 (extends the same migration file + the same service file). T013 (trigger) extends T008's migration **sequentially**. T014 (LISTEN) extends T009's service **sequentially**. T015 (shutdown) extends T010's main.py **sequentially**. T016 (workflow file) is `[P]` with T013/T014/T015 (different file). Test T017 extends T012's file sequentially (same file; "second batch").
- **US3 (P5)** → depends on Foundational (needs T002 schema + T003 YAML + T021 docs file from US4). T018 (script) → T019 (pre-commit entry). Test T020 is `[P]` with T019 (different file). **Note**: T018 references the docs file T021 creates, so T021 must land before T020's positive test passes. Acceptable: the dependency runs across phases; we order accordingly in the linear task list.
- **US4 (P6)** → depends on Foundational (T003 YAML must have the demonstration sunset entry first). T021 stands alone (one file).
- **Polish (P7)** → after all stories.

### Story independence
- US1 alone is the MVP: §9 dark-launch invariant is provably enforced even without LISTEN/NOTIFY (the propagation path degrades to TTL-only freshness, which is acceptable for the MVP definition).
- US2 layers on top of US1 (NOTIFY-driven sub-second propagation).
- US3 layers on the registration discipline.
- US4 layers on audit preservation.

### Parallel opportunities (file-level, single committer)
- T004 ∥ T006 ∥ T007 (foundational, different files).
- T011 ∥ T012 (US1 tests, different files).
- T016 ∥ T013/T014/T015 (US2 workflow is its own file).
- T017 lives in the same file as T012 (sequential, NOT parallel).
- T022 ∥ T023 ∥ T024 (polish — distinct files / actions).
- Never parallel: any two edits to `alembic/versions/0002_feature_flags.py` (T008, T013); to `app/backend/services/feature_flags.py` (T009, T014); to `app/backend/main.py` (T010, T015); to `.pre-commit-config.yaml` (T019); to `docs/engineering/feature-flags.md` (T021); to `app/backend/tests/services/test_feature_flags.py` (T012, T017).

---

## Implementation Strategy

### MVP first (US1)
1. Setup (Phase 1) → Foundational (Phase 2) → US1 (Phase 3).
2. **STOP and VALIDATE**: §9 dark-launch invariant proven; §3 carve-out proven (SC-009).

### Incremental delivery
1. Setup + Foundational → contract + model exist.
2. US1 → dark-launch invariant + §3 carve-out (MVP).
3. US2 → operator-grade flip without deploy + workflow skeleton.
4. US3 → registration discipline enforced before merge.
5. US4 → sunset history preserved structurally.
6. Polish → guardrails + quickstart sweep.

### Suggested commit grouping (manual commits, our norm)
- `feat(T05a): jsonschema dep + YAML schema contract + model + package scaffolding` (T001–T007)
- `feat(T05a): feature_flag table + service registry + main.py wiring` (T008–T010)
- `test(T05a): §3 carve-out positive + service registry + unknown-flag` (T011–T012)
- `feat(T05a): notify trigger + asyncpg LISTEN + sync workflow skeleton` (T013–T016)
- `test(T05a): sub-second propagation + listener reconnect` (T017)
- `feat(T05a): registration hook + pre-commit entry` (T018–T019)
- `test(T05a): hook failure-mode matrix + clean-tree baseline` (T020)
- `docs(T05a): feature-flags index + README link` (T021–T022)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- The hook script is in Python (not bash + grep) for clearer error messages — research §6 documents the rationale.
- The §3 carve-out is intentional (FR-013), proven by SC-009. The carve-out must be visible in both the migration docstring AND the SQLAlchemy model docstring so a future contributor doesn't extend audit-table protections to `feature_flag` by reflex.
- The workflow file ships **inert** in T05a (TODO-T06 placeholders); T06 fills the WIF / Cloud SQL bindings.
- DB tests skip cleanly when no DB is reachable (existing T05 pattern via the `db_available` fixture).
