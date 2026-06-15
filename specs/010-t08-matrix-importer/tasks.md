---
description: "Task list for T08 — Matrix importer (xlsx → YAML → DB)"
---

# Tasks: Matrix importer (T08)

**Input**: Design documents from `specs/010-t08-matrix-importer/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: INCLUDED — spec explicitly requires the schema-violation matrix (SC-007), the §4 immutability assertion (SC-004), rename rejection (SC-005), audit-row count (SC-008), and convert/seed idempotency (SC-002/SC-003).

**Agent / parallelism**: every task is `agent: backend-engineer`, executed sequentially in one PR. `[P]` marks tasks that touch *different files* and may be written back-to-back without ordering hazards; it does **not** authorise sub-agent fan-out (constitution §18 — `parallel: false` for T08 as a whole).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add the one new dependency `openpyxl` so the importer service can read xlsx workbooks.

- [ ] T001 Add `openpyxl>=3.1,<4` to `[project].dependencies` in `pyproject.toml`; regenerate `uv.lock` via `docker run --rm -v "$PWD":/w -w /w ghcr.io/astral-sh/uv:python3.12-bookworm uv lock` (research §1; uses the same uv 0.9.x image that T05a established for PEP 735 support).

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Author the contracts, schema, model + migration, and skeleton config directory every user story depends on.

**⚠️ CRITICAL**: No user story can be validated until this phase is complete.

- [ ] T002 Create `docs/contracts/rubric.schema.json` — JSON Schema draft 2020-12 per data-model.md §2. Required fields on a YAML file: `version` (int), `retired` (bool, default false), `nodes` (array). Each node: stable `id` (regex `^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)*$`), `label_en` (required always), `label_uk` (required when `retired=false`), optional `parent`, optional `retired`, optional `levels[]` with `{level: int 1..5, label_uk, descriptor_en, evidence_examples_en: [str]}`. Validates §11 hybrid-language and FR-012.
- [ ] T003 [P] Create `docs/contracts/matrix-format.md` — human-readable Excel workbook contract (FR-003). One sheet per stack; header columns `block`, `competency_id`, `competency_label_uk`, `competency_label_en`, `topic`, `level`, `descriptor_en`, `evidence_examples` (semicolon-separated); workbook-quirk rules from research §8 (merged cells across key cols rejected; NFC normalisation; HTML passthrough; semicolon delimiter).
- [ ] T004 Edit `app/backend/db/models/rubric.py` — add `payload_hash: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))` to `RubricTreeVersion`. Docstring explains the §4 versioning role.
- [ ] T005 Create `alembic/versions/0003_rubric_payload_hash.py` (revision `"0003_rubric_payload_hash"`, `down_revision="0002_feature_flags"`). `upgrade()` runs `ALTER TABLE rubric_tree_version ADD COLUMN payload_hash TEXT NOT NULL DEFAULT ''` then `ADD CONSTRAINT uq_rubric_tree_version_payload_hash UNIQUE (payload_hash)`. Reversible `downgrade()` drops constraint + column. Docstring documents the transitional-row safety (research §10).
- [ ] T006 [P] Create `configs/rubric/.gitkeep` + `configs/rubric/example.yaml` — minimal valid draft (`version: 1`, `retired: false`, `nodes:` with one retired demonstration node `example.demonstration`). Must validate against T002's schema; sunset-style entry locks in the format from day one (mirrors T05a's `example_demonstration` pattern).
- [ ] T007 [P] Create `app/backend/tests/cli/__init__.py` and `app/backend/tests/contracts/test_rubric_schema.py` placeholder + `app/backend/tests/contracts/test_rubric_schema_hook.py` placeholder (test bodies filled later in their stories' phases). Package markers exist so other stories' tests can run in isolation.

**Checkpoint**: contracts + model + migration + example YAML + package markers exist. User-story implementation can begin.

---

## Phase 3: User Story 1 — Operator turns Excel matrix into Git-tracked YAML (Priority: P1) 🎯 MVP

**Goal**: A maintainer points the CLI at a `.xlsx` and gets one schema-valid YAML per stack in `configs/rubric/`. Re-running on unchanged input is byte-identical.

**Independent Test**: A programmatically-generated fixture workbook produces N YAMLs that validate against `docs/contracts/rubric.schema.json`; a second convert run leaves them byte-identical; a fixture with duplicate `competency_id` is rejected non-zero before any file is written.

### Implementation for User Story 1

- [ ] T008 [US1] Create `app/backend/services/rubric_importer.py` (first slice — convert path + shared canonical YAML emitter + payload hash helper). Public surface: `class RubricImporter`, `RubricImporter.convert(xlsx_path: Path, out_dir: Path) -> list[Path]`, module-level `_emit_canonical_yaml(area: dict) -> str` and `_compute_payload_hash(yaml_dir: Path) -> str` (research §2/§3/§7). Workbook-quirk rules per research §8: NFC normalisation; semicolon-split `evidence_examples`; merged-cell across key columns → `MergedKeyColumnError`. Duplicate `competency_id` across blocks → `DuplicateCompetencyIdError`. No DB access in this slice.
- [ ] T009 [US1] Create `app/backend/cli/__init__.py` + `app/backend/cli/import_matrix.py` (convert subcommand only at this slice; seed lands in US2). `python -m app.backend.cli.import_matrix convert <xlsx> --out <dir>` invokes `RubricImporter.convert(...)`. Errors print to stderr with no traceback; exit codes: 0 success, 1 validation failure, 2 configuration error.

### Tests for User Story 1

- [ ] T010 [P] [US1] Create `app/backend/tests/cli/test_import_matrix_convert.py` — fixture workbook constructed in `tmp_path` with `openpyxl.Workbook()` (research §9); subprocess invocation of `python -m app.backend.cli.import_matrix convert ...`. Asserts: exit 0; N YAMLs written; every YAML validates against the schema; second invocation produces a byte-identical diff (SC-002, `filecmp.cmp(strict=True)`); duplicate-id fixture exits non-zero with the offending id in stderr; merged-cell-across-key-column fixture exits non-zero. Plus a unit test of `_emit_canonical_yaml`: same input → byte-identical output across runs.

**Checkpoint**: Excel → Git-tracked YAML pipeline is provable end-to-end on a fixture workbook — the MVP of T08.

---

## Phase 4: User Story 2 — DB is the runtime mirror of YAML; new immutable version per change (Priority: P1)

**Goal**: `--seed` materialises the rubric tree from `configs/rubric/`; first run creates one `rubric_tree_version` + full child set + audit row; second run on unchanged YAML is a no-op (SC-003); a content change creates a NEW version with a NEW child-row set, leaving pre-existing rows byte-identical (SC-004); each new version writes exactly one `audit_log` row (SC-008).

**Independent Test**: A pytest fixture seeds against the migrated test DB and asserts: row counts on first seed; zero new rows on repeat seed; new `rubric_tree_version` + new child set + one `audit_log` row on a content change; pre/post row-byte-hashes of prior-version rows are identical (the §4 invariant).

### Implementation for User Story 2

- [ ] T011 [US2] Extend `app/backend/services/rubric_importer.py` — add `RubricImporter.seed(yaml_dir: Path, *, dsn: str, dry_run: bool = False) -> SeedResult`. Flow per research §3–6: load + validate every `configs/rubric/*.yaml` against the schema (defence in depth); compute SHA-256 payload hash via `_compute_payload_hash`; open asyncpg connection; take `pg_advisory_xact_lock(987654321)`; look up the latest `rubric_tree_version.payload_hash`; if equal → return `SeedResult(noop=True)`; if different → INSERT new `rubric_tree_version` row (label `tree:<sha-prefix>`, `payload_hash=<full hash>`, `is_active=true`), then materialise the tree (`stack` → `competency_block` → `competency` → `topic` → `level`), then INSERT one `audit_log` row (`action='rubric.versioned'`, `actor_id=NULL`, `subject_hash=<hash>`). Commit. `--dry-run`: return the computed `SeedResult` without writing.
- [ ] T012 [US2] Extend `app/backend/cli/import_matrix.py` — add `seed` subcommand and the `--dry-run` flag. Connects to `DATABASE_URL` (Settings). Reports the SeedResult on stdout in a stable one-line format. Exit codes: 0 success/no-op, 1 validation failure, 2 DB connectivity error.

### Tests for User Story 2

- [ ] T013 [P] [US2] Create `app/backend/tests/cli/test_import_matrix_seed.py` — gated by the existing `db_available` fixture. Sub-tests:
  - `test_first_seed_creates_one_version_and_full_tree` — asserts row counts in `rubric_tree_version`/`stack`/`competency_block`/`competency`/`topic`/`level` after one seed against a fixture YAML directory.
  - `test_repeat_seed_is_no_op` — second seed inserts zero rows (compare row counts pre/post; SC-003).
  - `test_content_change_creates_new_version` — bumps `version` + edits one descriptor → seed runs; assert 1 new `rubric_tree_version`, fresh child row set linked to new version, prior-version rows byte-identical via SHA-256 of `row_to_json` per row (SC-004).
  - `test_audit_row_per_new_version` — `SELECT COUNT(*) FROM audit_log WHERE action='rubric.versioned'` increments by exactly 1 per new-version seed (SC-008).
  - `test_concurrent_seed_serialised` — two concurrent asyncpg connections both call seed; one wins, the other returns no-op without UNIQUE-violation error (advisory-lock contract from research §6).

**Checkpoint**: SC-003 + SC-004 + SC-008 are provable end-to-end on live Postgres.

---

## Phase 5: User Story 3 — Schema enforcement keeps the YAML uniform (Priority: P1)

**Goal**: A committed JSON Schema validates every `configs/rubric/*.yaml` on every commit. Pre-commit + CI reject violations.

**Independent Test**: Five fixture YAMLs each violating a distinct schema rule are rejected with a precise error; the clean post-T08 tree passes (exit 0).

### Implementation for User Story 3

- [ ] T014 [US3] Create `scripts/check-rubric-schema.py` — Python 3.12 script. Resolves `--root <path>` (default = repo root from script location). Loads `docs/contracts/rubric.schema.json` and validates every `configs/rubric/*.yaml`. Exits non-zero with a precise stderr message (file + JSON path + error description) on any violation. Mirrors the shape of `scripts/check-feature-flag-registration.py` from T05a.
- [ ] T015 [US3] Edit `.pre-commit-config.yaml` — add one new local hook `id: rubric-schema`, `name: rubric schema validation`, `language: system`, `entry: python3 scripts/check-rubric-schema.py`, `files: ^(configs/rubric/.+\\.yaml|docs/contracts/rubric\\.schema\\.json)$`, `pass_filenames: false`. Mirror T05a's `feature-flag-registered` hook shape.

### Tests for User Story 3

- [ ] T016 [P] [US3] Create `app/backend/tests/contracts/test_rubric_schema.py` — for each of five fixture YAMLs written to `tmp_path` (missing `label_uk` on active node; invalid level integer > 5; bad `id` regex; retired-without-retire-metadata-on-area; missing `descriptor_en` on active competency level), assert `jsonschema.Draft202012Validator(schema).iter_errors(doc)` returns the expected error message substring. Plus a positive baseline: the post-T08 example YAML validates clean (SC-006).
- [ ] T017 [P] [US3] Create `app/backend/tests/contracts/test_rubric_schema_hook.py` — subprocess invocations of `scripts/check-rubric-schema.py --root <tmp_path>` against fixture trees. Five negative trees (one per failure mode above) assert non-zero exit + precise message. One positive test against the real post-T08 tree (no `--root`) asserts exit 0 (SC-006).

**Checkpoint**: SC-006 + SC-007 enforced on every commit and in CI.

---

## Phase 6: User Story 4 — Stable id rename rejected (Priority: P2)

**Goal**: An attempt to rename a stable node `id` is rejected by the CLI with a precise message; nothing is written.

**Independent Test**: A fixture YAML directory where one node's `id` has been changed from a prior version's value (without retiring the old id) → `--seed` exits non-zero with the "retire + introduce" message and writes nothing.

### Implementation for User Story 4

- [ ] T018 [US4] Extend `app/backend/services/rubric_importer.py` — within `seed()`, after the new-version detection but before writing, run the rename check from research §5: load prior-version active node-id set; compute `disappeared = prior_active - new_active - new_retired`; if non-empty, raise `RenameForbiddenError(disappeared)` with a message naming the disappeared ids and instructing "retire + introduce instead". Transaction is rolled back, advisory lock released.

### Tests for User Story 4

- [ ] T019 [P] [US4] Extend `app/backend/tests/cli/test_import_matrix_seed.py` (existing file from T013) — add `test_rename_attempt_rejected`: seed initial version; then edit a YAML to rename one stable id from the prior payload without retiring; assert seed exits non-zero with the offending id in stderr and writes zero rows (SC-005). Also a positive: explicit retire-old + introduce-new is accepted.

**Checkpoint**: SC-005 locked in; the §4/ADR-018 stable-id contract is enforced structurally.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T020 [P] Edit `README.md` — add a short "Rubric content" subsection (two sentences max) with links to `docs/contracts/rubric.schema.json`, `docs/contracts/matrix-format.md`, and `configs/rubric/`. Mirrors the T05a "Feature flags" subsection.
- [ ] T021 Run guardrails inside Docker: `ruff check app/backend` + `ruff format --check app/backend alembic scripts` + `mypy --strict app/backend` + `python -m app.backend.generate_openapi --check` (byte-identical — no route added). `pre-commit run --all-files` passes (the new hook runs against the clean tree → exit 0). Full test suite under the `db` profile: `docker compose -f docker-compose.test.yml --profile db run --rm backend sh -c "alembic upgrade head && pytest app/backend/tests -v"`. Confirm SC-009 (< 90 s wall time).

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)** → no deps; T001 first.
- **Foundational (P2)** → depends on Setup. T002 (schema) blocks T003 and T006 (the example YAML must validate against the schema; the workbook contract references the schema for `evidence_examples_en` semantics). T004 (model) blocks T005 (migration depends on `Base.metadata` parity). T005 (migration) blocks every US2 / US4 DB-touching test.
- **US1 (P3)** → depends on Foundational. T008 → T009 (CLI depends on the service). T010 in parallel with the implementation files (separate file).
- **US2 (P4)** → depends on US1 (extends the same service file). T011 follows T008. T012 follows T009. T013 in its own file. T011/T012 are sequential edits to the same file pair; T013 in parallel with neither implementation file.
- **US3 (P5)** → depends on Foundational (T002 + T006). T014 → T015. T016/T017 are `[P]` with each other (different files).
- **US4 (P6)** → depends on US2 (extends the same seed service path). T018 follows T011 (same file). T019 extends T013's file (sequential).
- **Polish (P7)** → after all stories.

### Story independence
- US1 alone is the MVP: xlsx → YAML conversion proven end-to-end with no DB needed.
- US2 layers on top of US1 (seed path, new version, audit row).
- US3 layers on schema enforcement (cross-story, but easier to verify after US1 + US2 show the format works in practice).
- US4 layers on US2 (rename detection is inside the seed path).

### Parallel opportunities (file-level, single committer)
- T003 ∥ T002 (different files; foundational).
- T006 ∥ T007 (different files; foundational).
- T010 ∥ T009 (test file vs CLI file).
- T013 ∥ T012 (test file vs CLI file).
- T016 ∥ T017 (separate test files; US3).
- T020 ∥ T021 (polish doc vs guardrail run).
- Never parallel: any two edits to `app/backend/services/rubric_importer.py` (T008, T011, T018); to `app/backend/cli/import_matrix.py` (T009, T012); to `alembic/versions/0003_rubric_payload_hash.py` (T005); to `app/backend/tests/cli/test_import_matrix_seed.py` (T013, T019); to `.pre-commit-config.yaml` (T015).

---

## Implementation Strategy

### MVP first (US1)
1. Setup (Phase 1) → Foundational (Phase 2) → US1 (Phase 3).
2. **STOP and VALIDATE**: xlsx → schema-valid YAML pipeline proven on a fixture workbook.

### Incremental delivery
1. Setup + Foundational → contracts + model + migration + example YAML exist.
2. US1 → convert path proven (MVP).
3. US2 → seed + new-version + immutability + audit row proven on live DB.
4. US3 → schema enforcement on every commit (pre-commit + CI).
5. US4 → rename detection in seed path locked in.
6. Polish → README, guardrails, quickstart sweep.

### Suggested commit grouping (manual commits, our norm)
- `feat(T08): rubric contracts + payload_hash column + migration 0003` (T001–T007)
- `feat(T08): rubric importer convert path + CLI convert subcommand` (T008–T009)
- `test(T08): convert path — fixture xlsx + byte-identical re-run + duplicate-id rejection` (T010)
- `feat(T08): rubric importer seed path + advisory lock + audit_log emission` (T011–T012)
- `test(T08): seed e2e — idempotency + immutability + new-version + audit row` (T013)
- `feat(T08): rubric schema pre-commit + CI hook` (T014–T015)
- `test(T08): schema-violation matrix + clean-tree baseline` (T016–T017)
- `feat(T08): rename rejection in seed (retire + introduce policy)` (T018)
- `test(T08): rename attempt rejected` (T019)
- `docs(T08): README rubric subsection + tasks complete` (T020 + tasks.md done)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- §4 immutability is enforced via versioning + a byte-identical pre/post test on prior-version rows (SC-004). Old session snapshots remain interpretable forever.
- §3 carve-out: rubric-tree tables get NEW rows per version (mutation across versions); `audit_log` is INSERT-only from the importer (the §3 invariant is preserved).
- The CLI is module-invoked (`python -m app.backend.cli.import_matrix`); no console_script entry in pyproject — module invocation is enough for T08 / T16.
- T16 (Configs-as-Code sync, future) will wire a GitHub Actions workflow that calls `import_matrix --seed` on `main` merge, mirroring T05a's `sync-feature-flags.yml` shape.
- Real-world rubric content (C# + React matrices) lands via follow-up PRs through the same CLI. T08 ships only the mechanism + the fixture-driven test matrix + a minimal example YAML.
