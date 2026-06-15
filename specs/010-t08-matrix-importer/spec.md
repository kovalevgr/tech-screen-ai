# Feature Specification: Matrix importer — xlsx → YAML → DB (T08)

**Feature Branch**: `010-t08-matrix-importer`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: T08 — Matrix importer (xlsx → YAML → DB), per `docs/engineering/implementation-plan.md` Tier 1 / W1–W2

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are humans and AI sub-agents that own the rubric content (the interview engineers who maintain the Excel "matrix"; the `prompt-engineer` agent that calibrates the rubric tree against reviewer corrections; the `backend-engineer` agent that wires the rubric into Position Templates in Tier 2; the project owner / reviewer who audits how a stale rubric became active in production). T08 delivers the **mechanism** that turns the authoritative Excel matrix into a Git-tracked, schema-validated YAML and into runtime database rows — without that mechanism the rubric tables from T05 are structurally empty and Tier 2 cannot start. T08 ships **no** Position Template, **no** Assessor wiring, **no** scoring logic — it ships the pipeline that puts rubric content where every later layer expects to find it.

### User Story 1 — Operator turns the Excel matrix into Git-tracked YAML (Priority: P1)

A rubric maintainer (interview engineer) has the authoritative content in a `.xlsx` file. They must be able to point a single command at the workbook and get one machine-readable YAML per stack, conforming to a committed schema, ready to commit through a PR. Running the command twice on an unchanged workbook produces a zero-line diff.

**Why this priority**: P1 because this is the entry point of the entire rubric pipeline. Constitution §16 (configs as code) requires the YAML to be the source of truth; ADR-021 forbids the Admin UI from being the authoritative editor. Without a reliable xlsx→YAML conversion, the rubric content either lives only in Excel (untracked, unreviewable) or has to be hand-translated by humans (error-prone, slow). The whole "configs as code" stance collapses without this step.

**Independent Test**: A maintainer clones the repo, runs the importer against the fixture matrix bundled with the PR, and observes one YAML per stack written to `configs/rubric/`. The output validates against the committed schema. Running the command a second time leaves the working tree byte-identical.

**Acceptance Scenarios**:

1. **Given** the fixture matrix bundled with this PR, **When** the maintainer runs the importer in convert mode with `--out configs/rubric/`, **Then** one `<stack-id>.yaml` is written per sheet/stack and every file validates against `docs/contracts/rubric.schema.json`.
2. **Given** the same workbook and existing YAMLs from a prior run, **When** the importer is rerun, **Then** the YAMLs are unchanged (byte-identical) and the command exits 0.
3. **Given** an xlsx whose rows declare a duplicate stable `competency_id` (e.g. the same id appearing in two blocks of the same stack), **When** the importer parses it, **Then** the command exits non-zero **before** any YAML is written and the error names the duplicate id.

---

### User Story 2 — Database is the runtime mirror of the YAML, with a new immutable version per change (Priority: P1)

The backend runtime reads rubric content from the database. The database must reflect what is currently in `configs/rubric/`, but — per ADR-018 / §4 — must **never edit existing rows in place**. Each meaningful change produces a new immutable `rubric_tree_version` row and a fresh set of `stack` / `competency_block` / `competency` / `topic` / `level` rows linked to that new version. Old session snapshots remain interpretable forever.

**Why this priority**: Co-equal P1. Without this seed path, every later runtime feature that consumes the rubric (Position Template, Assessor, Planner, reviewer UI) has nothing to read. The immutability discipline must land with the first seed, not retro-fitted later — otherwise the very first content edit silently mutates history.

**Independent Test**: On a freshly-migrated test database the maintainer runs the importer in seed mode. The database gains exactly one `rubric_tree_version` row, one `stack` per file, and the matching `competency_block` / `competency` / `topic` / `level` rows. A second seed run with unchanged YAML produces zero new rows. A YAML edit that changes a level descriptor (and bumps the file's `version` integer) produces a NEW `rubric_tree_version` and a NEW set of node rows linked to it — the previous version's rows remain byte-identical.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** the maintainer runs the importer in seed mode against `configs/rubric/`, **Then** exactly one `rubric_tree_version` row appears, plus one `stack` row per file and the matching children.
2. **Given** the database already reflects the current YAMLs, **When** the importer is rerun in seed mode, **Then** zero rows are inserted, zero rows are updated, and the command exits 0.
3. **Given** a maintainer edits one `descriptor_en` value in one YAML and bumps that file's top-level `version` integer, **When** the importer is rerun in seed mode, **Then** a NEW `rubric_tree_version` row is created and the full new tree is materialised under it; the prior version's rows remain unchanged.
4. **Given** any seed run that creates a new version, **When** it commits, **Then** exactly one `audit_log` row appears with action `rubric.versioned`, the new version's payload hash recorded, and no candidate PII (§15).

---

### User Story 3 — Schema enforcement keeps the YAML uniform across all maintainers (Priority: P1)

The YAML is the source of truth — but only if everyone writes it the same way. A committed JSON Schema contract describes every required and optional field; a pre-commit + CI hook validates every `configs/rubric/*.yaml` against it on every commit. A schema-violating PR cannot be merged.

**Why this priority**: Co-equal P1 because §14 (contract-first for parallel work) and §17 (specs precede implementation) require the schema to land in the same PR that introduces the rubric files — not in a follow-up PR after misshapen YAMLs have already polluted Git history. Downstream consumers (Tier 2 Position Template, Tier 3 Assessor) assume schema conformance; without enforcement they would have to defensively parse and the contract erodes.

**Independent Test**: Two fixture PRs. (a) A YAML that omits a required field (`label_uk` on an active node) is rejected by the pre-commit hook with a precise message naming the offending file and field. (b) A YAML with an invalid `state` value (e.g. `state: pending`) is rejected the same way. The same check fails in CI so a contributor cannot bypass it by skipping local hooks.

**Acceptance Scenarios**:

1. **Given** a contributor commits a YAML that omits `label_uk` on an active node, **When** pre-commit runs, **Then** the commit is rejected with the message naming the file, the node id, and the missing field.
2. **Given** the same defect in a PR (local hook bypassed), **When** CI runs the same check, **Then** the PR is marked failing.
3. **Given** a YAML conforming to the schema, **When** the importer's seed path is invoked, **Then** the CLI re-validates the YAML (defence in depth) and proceeds.

---

### User Story 4 — Stable node ids protect old session snapshots from accidental rename (Priority: P2)

ADR-018 says a node's stable identifier (e.g. `python.concurrency`) is the contract between a session's frozen rubric snapshot and the current rubric tree. Renaming an id silently breaks every historical interpretation. The importer must refuse a rename and force the maintainer to do the structural thing: retire the old id and introduce a new one.

**Why this priority**: P2 because it serves long-tail audit (months / years out), not the daily import loop. But the cost of NOT encoding it now is invisible debt: every rename quietly destroys backward compatibility with every prior session.

**Independent Test**: A maintainer changes a node id from `python.concurrency` to `python.threading` in one YAML and runs the importer in seed mode. The command exits non-zero with a message naming both ids and instructing the maintainer to retire the old one (set `retired: true`) and introduce the new id separately.

**Acceptance Scenarios**:

1. **Given** the DB has node `python.concurrency` from a prior version, **When** a YAML is edited to rename it to `python.threading` and a seed is attempted, **Then** the importer exits non-zero with a clear message and **no** rows are written.
2. **Given** the maintainer instead retires `python.concurrency` (sets `retired: true`) and adds a separate new node `python.threading`, **When** the seed runs, **Then** both ids exist in the new version's node set, the retired flag is reflected on the new row, and old session snapshots continue to resolve `python.concurrency` against the prior version.

---

### Edge Cases

- **Cell merges, whitespace, encoded entities in xlsx**: the importer trims whitespace, normalises NFC, and rejects merged cells that span across a key column (block / competency_id / level) with a clear error.
- **Workbook with mixed sheets** (some rubric, some operator notes): the importer accepts a `sheet_name` argument list to select which sheets to convert; unspecified extra sheets are ignored with an info-level log.
- **Multiple stacks in one workbook**: the importer emits one YAML per stack, named `<stack-id>.yaml`; duplicate stack ids across sheets are an error.
- **Empty active YAML** (a `configs/rubric/<stack>.yaml` with `nodes: []` and `retired: false`): allowed for an in-progress draft, but flagged by the schema as a warning (no active nodes means no content for that stack).
- **Concurrent seed runs**: two simultaneous seed invocations against the same database serialise via a database advisory lock; the second observes the first's new version and proceeds as a no-op.
- **Seed against a database that already has rubric data from a prior tree-version**: the importer leaves the existing rows untouched and either adds a new version (if YAML hash differs) or is a no-op (if hash matches). It never deletes prior-version rows.
- **YAML edited to add a `retired: true` flag**: that node is included in the new version's snapshot with `retired=true`; the runtime Assessor treats retired nodes as "do not probe" but the snapshot still resolves the id for old sessions.
- **xlsx and DB drift** (someone edited the YAML by hand without re-running the convert): the seed path treats the YAML as truth (§16); a future workflow (T16) will guard the round-trip.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a command-line entry point that converts a `.xlsx` workbook into one YAML file per stack in `configs/rubric/`, where each file conforms to the committed JSON Schema.
- **FR-002**: System MUST commit, in this same PR, the JSON Schema contract at `docs/contracts/rubric.schema.json` that every `configs/rubric/*.yaml` is validated against. The schema covers stable node identifiers, hybrid-language labels, `levels` arrays, lifecycle flags (`retired`), and the conditional fields required when a node or area is retired.
- **FR-003**: System MUST commit, in this same PR, a human-readable matrix-format contract at `docs/contracts/matrix-format.md` describing the expected workbook layout (sheet-per-stack convention, header columns, semantics of each cell). A maintainer must be able to produce a conforming workbook from that document alone, without reading code.
- **FR-004**: The convert path MUST be byte-identical idempotent: running the command twice on an unchanged workbook leaves the YAML files unchanged. The output is canonicalised (key order, list order, indentation).
- **FR-005**: The convert path MUST fail (non-zero exit + a message naming the offending value) before writing any file when the workbook violates the matrix-format contract — including duplicate stable competency ids, missing required columns, or merged cells spanning a key column.
- **FR-006**: System MUST provide a CLI seed mode that reads `configs/rubric/*.yaml`, validates each file against the JSON Schema (defence in depth on top of the pre-commit hook), and reconciles the database to match. The seed mode is non-destructive — it inserts new rows, never updates or deletes existing rows.
- **FR-007**: System MUST compute a deterministic hash of the canonical YAML payload (all `configs/rubric/*.yaml` combined) and compare it against the latest `rubric_tree_version` row's recorded snapshot. When the hash matches, the seed run is a no-op (zero inserts). When the hash differs, a NEW `rubric_tree_version` row is created and a complete fresh tree is inserted under it.
- **FR-008**: System MUST leave every existing `rubric_tree_version` row and its child nodes untouched on every seed run — the §4/ADR-018 immutability guarantee. A test asserts that pre-existing rows are byte-identical after a seed that created a new version.
- **FR-009**: System MUST refuse any rename of a stable node `id` and exit non-zero with a message instructing the maintainer to retire the old id (set `retired: true`) and introduce a new node with the new id as a separate change. The seed run writes nothing when a rename is detected.
- **FR-010**: On each seed run that creates a new `rubric_tree_version`, system MUST insert exactly one row into `audit_log` with action `rubric.versioned`, the new payload hash recorded in `subject_hash`, and `actor_id` left null (system action). The `audit_log` table's §3 append-only invariant is preserved (INSERT only).
- **FR-011**: System MUST validate `configs/rubric/*.yaml` against the JSON Schema via a pre-commit + CI hook. The hook rejects schema-violating commits locally and the same check fails in CI so it cannot be bypassed.
- **FR-012**: Hybrid-language enforcement (§11): the schema MUST require non-empty `label_uk` on every active node, and non-empty `descriptor_en` on every level of every active competency. Retired nodes are exempt from the active-content requirements but must keep their `id` and `retired: true` flag.
- **FR-013**: System MUST provide at least one fixture workbook bundled with the PR so the convert path is exercised standalone in tests, and at least one fixture set of `configs/rubric/*.yaml` so the seed path is exercised against a live database without any external data dependency.
- **FR-014**: System MUST add a `--dry-run` mode to the CLI that validates + computes the diff against the database and reports the change set (would-be-new version label + counts of new nodes per kind) without writing anything. Exit code is non-zero only on validation failure.
- **FR-015**: System MUST be invokable in the existing dev/CI Docker image without additional cloud credentials. The convert path is local-only (no network); the seed path opens a database connection via `DATABASE_URL` (existing T05 contract).

### Key Entities

- **Excel matrix workbook** (`.xlsx`): the authoritative source maintained outside the repository by interview engineers. One workbook may contain one or more stacks (one sheet per stack). The header row of each sheet declares a documented set of columns; each subsequent row contributes one `(block, competency, topic, level)` tuple to that stack.
- **Rubric YAML file** (`configs/rubric/<stack-id>.yaml`): the Git-tracked canonical representation of one stack's rubric. Conforms to the JSON Schema. Carries `version`, `retired`, and a `nodes` array; each node has a stable `id`, hybrid labels, optional `parent`, optional `retired` flag, and (for leaf competency nodes) `levels`.
- **JSON Schema contract** (`docs/contracts/rubric.schema.json`): the machine-readable definition of a rubric YAML file. The same artefact is validated by the pre-commit hook and by the CLI at runtime.
- **Matrix-format contract** (`docs/contracts/matrix-format.md`): the human-readable definition of the Excel workbook layout — column headers, cell semantics, what makes a workbook acceptable.
- **Rubric tree version** (a row in `rubric_tree_version`): immutable snapshot identity. Each meaningful YAML change produces a new row; old rows are never edited.
- **Tree node rows** (`stack` / `competency_block` / `competency` / `topic` / `level`): the materialised tree under one `rubric_tree_version`. Existing rows under prior versions are never edited; each new version gets its own fresh row set.
- **Audit row** (`audit_log` with `action='rubric.versioned'`): the one-row receipt that every new-version seed run emits — the `§1` auditability anchor for "when did the rubric change, and to what hash".

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new contributor can convert a fixture workbook into Git-tracked YAML, validate it, and seed a fresh database **in under 10 minutes**, following `docs/contracts/matrix-format.md` and `docs/contracts/rubric.schema.json` only — without reading source code.
- **SC-002**: The convert path is **byte-identical idempotent**: a second run against the same workbook produces a zero-line diff in the working tree — measurable by `git diff --quiet` exiting 0.
- **SC-003**: The seed path is **non-destructive idempotent**: a second seed against unchanged YAML inserts zero rows and updates zero rows — measurable by row-count assertions in the integration test.
- **SC-004**: A YAML change that bumps the file's `version` integer and modifies any level descriptor creates exactly **one** new `rubric_tree_version` row and a fresh complete node-row set; **zero** pre-existing rows are mutated — measurable by a pre/post row-byte-comparison assertion.
- **SC-005**: A renamed stable node `id` is **rejected** by the CLI with a non-zero exit and a message naming both the old and the new id; **zero** rows written — measurable by a fixture test.
- **SC-006**: **100% of `configs/rubric/*.yaml`** validate against the committed JSON Schema on every commit — measurable by running the pre-commit hook on the clean post-T08 tree and observing exit 0.
- **SC-007**: Schema violations are blocked at PR time: five distinct fixture defects (missing required field, invalid `state`, empty `label_uk`, malformed level descriptor, retired-without-retire-metadata) **all** fail the hook with a precise, file-named error.
- **SC-008**: Every seed run that creates a new `rubric_tree_version` writes **exactly one** matching `audit_log` row with `action='rubric.versioned'` — measurable by a `SELECT COUNT(*)` assertion in the integration test.
- **SC-009**: The post-T08 backend test suite, including the new CLI and seed tests, completes in **under 90 seconds** on a clean tree with the `db` profile.
- **SC-010**: The post-T08 tree carries **zero** new credentials in source control — verifiable by `gitleaks` and `detect-secrets` on the PR diff.

## Assumptions

- The Excel "matrix" format defined in `docs/contracts/matrix-format.md` is a project-specific convention introduced by this PR. The "real-world" C# and React matrices mentioned in older planning notes are not present in the repository; the fixture workbook bundled with this PR is the canonical witness, and real matrices will land via the same CLI in follow-up PRs.
- The CLI is operator-driven at MVP — invoked from a shell either locally or in a future GitHub Actions workflow. Interactive Admin UI editing is explicitly out of scope (§16 / ADR-021 — the Admin UI is read-only for rubric content).
- The post-merge GHA sync workflow that calls the seed mode on every `main` merge is owned by T16 (Configs-as-Code sync — YAML → DB on merge), not by T08. T08 ships the CLI + schema + seed mechanism; T16 wires the workflow file later, mirroring the T05a feature-flag sync workflow's shape.
- The database role used by the seed path is the existing `techscreen_migrator` from T05 (or a runtime role with INSERT on the rubric tree tables); §3 protections do not constrain the seed path because the rubric-tree tables are NOT in the append-only set, and the importer's `audit_log` writes are INSERT-only (the §3-allowed operation).
- A single canonical YAML format covers both the human-readable maintainer use case and the runtime-loader use case; no per-environment overlays are introduced (constitution §8 — production is the only environment).
- An xlsx parsing library acceptable for read-only, no-network use is available in the dev image. The exact library choice and how to handle merged cells / encoded entities are implementation-altitude decisions deferred to the planning phase.
- The seed path mutates the database when the YAML payload hash differs; this is consistent with the rubric-tree tables being mutable (`stack` / `competency_block` / etc. are NOT in the §3 append-only set — only `audit_log` is, and the importer only inserts into it).
- A YAML edit that bumps `version` but does not change content (e.g. a comment edit, a key reordering that does not affect the canonical hash) produces a hash collision with the prior version and is therefore a no-op seed — exactly as intended.
- The fixture workbook shipped with T08 is illustrative, not production-grade rubric content. Real rubric content lands via subsequent PRs that go through the same CLI; calibration of those rubrics happens in Tier 8 (calibration tier).

## Out of scope

- Admin UI for editing rubric content (Phase 2 — §16 / ADR-021 keep the Admin UI read-only for rubric).
- The post-merge GitHub Actions workflow that calls the seed mode on every `main` merge — owned by T16, which extends the T05a workflow with a rubric-sync job.
- Round-tripping FROM the DB or YAML back to a `.xlsx` — one-way for MVP. If a maintainer wants xlsx, they regenerate from YAML manually.
- Migration of real-world C# + React rubric content. The CLI is the mechanism; the content lands via follow-up PRs by the rubric owners.
- Anything beyond the rubric tree: no Position Template, no Assessor wiring, no scoring logic, no candidate-facing rendering. Those land in Tier 2+.
- Modifications to existing `rubric_tree_version` rows or to any prior-version node rows. §4 immutability is structural and tested.
- Adding a new Alembic migration. The five rubric-tree tables already exist from T05's baseline; T08 only writes rows.
