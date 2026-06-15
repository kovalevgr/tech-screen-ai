# Implementation Plan: Matrix importer — xlsx → YAML → DB (T08)

**Branch**: `010-t08-matrix-importer` | **Date**: 2026-04-28 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/010-t08-matrix-importer/spec.md`

## Summary

T08 lights up the rubric content pipeline. In a single PR, in the order a reviewer should validate them:

1. **Schema contract** committed first (§14): `docs/contracts/rubric.schema.json` formalises the YAML entry shape (JSON Schema draft 2020-12) — every node carries a stable `id`, hybrid labels (`label_uk` / `label_en`), `retired` flag, optional `parent`, and (for leaf competencies) `levels` arrays with `descriptor_en` + `evidence_examples_en` + a UK label per level. `docs/contracts/matrix-format.md` is the human-readable contract describing the Excel workbook layout (one sheet per stack, documented header columns), so a maintainer can produce a conforming `.xlsx` from a single document.
2. **Additive migration** `alembic/versions/0003_rubric_payload_hash.py` (forward-only per §10, `down_revision='0002_feature_flags'`): adds `payload_hash TEXT NOT NULL UNIQUE` to `rubric_tree_version`. This is the only T08 migration. The column is the idempotency anchor for the seed path — equal hash → no-op; different hash → new version row. Reversible downgrade for local resets.
3. **`RubricImporter` service** at `app/backend/services/rubric_importer.py` — three orthogonal capabilities: `convert(xlsx_path, out_dir)` (xlsx → canonical YAML), `seed(yaml_dir, *, dry_run=False)` (YAML → DB, idempotent), and a `compute_payload_hash(yaml_dir)` helper used by both. The canonical YAML emitter is shared (single source of truth, research §7) so convert output and seed input cannot drift.
4. **CLI** `app/backend/cli/import_matrix.py` — thin argparse wrapper. Modes: `convert` (xlsx → YAML files); `seed` (YAML → DB); `--dry-run` (validate + report change set, write nothing). Errors are CLI-shaped (non-zero exit + precise stderr line; no traceback on the success path).
5. **`scripts/check-rubric-schema.py`** — pre-commit + CI guard that validates every `configs/rubric/*.yaml` against `docs/contracts/rubric.schema.json` (FR-011). Mirrors the T05a `feature-flag-registered` hook pattern; wired in `.pre-commit-config.yaml`.
6. **`configs/rubric/`** ships with a minimal hand-authored example file plus a `.gitkeep` so the clean-tree baseline (SC-006) holds before any real rubric arrives. No real-world rubric content lands in T08 — that comes via follow-up PRs through the same CLI.
7. **Tests**:
   - `app/backend/tests/cli/test_import_matrix_convert.py` — programmatically builds a fixture xlsx in `tmp_path` with `openpyxl` (no committed binary), exercises convert, asserts byte-identical re-run, exit 0, schema validation passes, duplicate-id fixture rejected non-zero.
   - `app/backend/tests/cli/test_import_matrix_seed.py` — seeds against the migrated test DB; asserts the §4 immutability invariant (pre/post row-byte comparison after a content change creates a new version), the no-op second-seed, the rename rejection (FR-009 / SC-005), and the audit-log emission (FR-010 / SC-008).
   - `app/backend/tests/contracts/test_rubric_schema.py` — five fixture YAML defects each fail the schema with a precise message (SC-007); the post-T08 clean tree validates (SC-006).
   - `app/backend/tests/contracts/test_rubric_schema_hook.py` — subprocess invocations of the pre-commit hook script against fixture trees, mirroring T05a's pattern.

The PR adds **no** HTTP endpoint (the CLI is shell-invoked; the importer is a service, not a route), **no** OpenAPI diff (the T02 regen-and-diff guardrail must stay byte-identical), **no** prompt content, **no** Docker / compose changes (the existing `db` profile picks up 0003 automatically; `openpyxl` is pure Python and needs no new system deps). Single-committer PR — `agent: backend-engineer`, `parallel: false`. The parallel fan-out T08 enables is post-merge: Tier 2 (T12+ Position Template) can finally reference real rubric content.

## Technical Context

**Language/Version**: Python 3.12 (unchanged; `pyproject.toml` pins `>=3.12,<3.13`).

**Primary Dependencies** added to `[project].dependencies`:

- `openpyxl >= 3.1, < 4` — pure-Python xlsx parser; read-only is well-supported, no native compile, lightweight (~250 KB). Research §1 documents alternatives (`pandas` rejected for weight; `xlrd` rejected for xlsx-format support gap).

No other new runtime deps. `pyyaml` and `jsonschema` already shipped in T01–T05a.

**Dev dependencies**: none new (`pytest`, `pytest-asyncio` already configured).

**Storage**: Postgres 17 + `pgvector` + `pgcrypto` from T05's baseline; `feature_flag` table from T05a. T08 adds one additive column (`rubric_tree_version.payload_hash`) and writes rows into the existing rubric-tree + `audit_log` tables. No new tables, no new triggers.

**Testing**: `pytest` + `pytest-asyncio` (auto-mode). The new tests live under:
- `app/backend/tests/cli/test_import_matrix_convert.py` — pure-fs; no DB needed.
- `app/backend/tests/cli/test_import_matrix_seed.py` — gated by the existing `db_available` fixture (skips without DB; established T05 pattern).
- `app/backend/tests/contracts/test_rubric_schema.py` — pure-fs schema check tests.
- `app/backend/tests/contracts/test_rubric_schema_hook.py` — subprocess against the hook script in fixture trees.

**Target Platform**: Linux container (existing `dev` Docker target). `openpyxl` is pure Python; no Dockerfile change required (research §1 confirms).

**Project Type**: Backend slice within the existing FastAPI monorepo. No frontend changes. No infra/Terraform changes.

**Performance Goals**:
- Convert path: parse + emit < 1 second for a workbook with ~10 stacks × 10 blocks × 50 competencies (realistic upper bound for the MVP).
- Seed path: full round-trip < 5 seconds on the test DB for the same scale.
- Hash computation: < 100 ms for the full `configs/rubric/` directory (file IO dominates).
- Full T08 test suite: < 30 seconds (SC-009 is < 90 s for the whole post-T08 suite — well within budget).

**Constraints**:
- **§4 immutability** — old `rubric_tree_version` rows and every child node row MUST remain byte-identical across all seed runs. A pre/post row-byte-hash test asserts this (SC-004).
- **§3 carve-out vs append-only** — the rubric-tree tables (`stack`, `competency_block`, `competency`, `topic`, `level`) are NOT in the §3 set; the importer inserts new rows per version (mutation across versions is the design). `audit_log` IS in the §3 set; the importer ONLY inserts there (one row per new version) — never UPDATE/DELETE. The migration adds no new trigger.
- **§9 dark-launch** — N/A. T08 ships a CLI, not user-facing behaviour. No feature flag needed (the seed path is operator-driven, not request-time).
- **§10 forward-only** — 0003 is purely additive; reversible `downgrade()` for local/CI resets only.
- **§11 hybrid language** — the schema MUST require non-empty `label_uk` on active nodes and non-empty `descriptor_en` on every level of an active competency.
- **§14 contract-first** — `docs/contracts/rubric.schema.json` + `docs/contracts/matrix-format.md` committed in this PR before any consumer (T12+) references rubric content.
- **§16 configs as code** — `configs/rubric/*.yaml` is the source of truth.
- **§18 explicit orchestration** — single committer (`backend-engineer`), `parallel: false`.
- **OpenAPI diff is zero** — the importer has no HTTP surface. T02 regen-and-diff guardrail stays clean.
- **`mypy --strict` clean** — every public symbol in `rubric_importer.py` + CLI is fully typed.
- **Pre-commit guardrails** from T01–T05a all pass; T08 adds **one** new local hook (`rubric-schema`) without weakening any existing one.

**Scale/Scope**: Single PR, ≈ 14 new files (≈ 700 LOC source + ≈ 600 LOC tests + the JSON schema + the human contract + the hook + one example YAML). One committer (`agent: backend-engineer`), `parallel: false`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| §   | Principle                              | Applies to T08?                                                                                                                                                                                       | Status |
| --- | -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first    | Indirect — the `audit_log` row per new version is the §1 anchor for "when did the rubric change". Old session snapshots remain interpretable (FR-008).                                                  | Pass   |
| 2   | Deterministic orchestration            | N/A — no LLM, no routing.                                                                                                                                                                              | N/A    |
| 3   | Append-only audit trail                | Yes — `audit_log` is INSERT-only from the importer (FR-010). Rubric-tree tables are NOT in the §3 set; mutation across versions is by design. The migration adds no trigger.                            | Pass   |
| 4   | Immutable rubric snapshots             | **Primary purpose.** Versioning + `payload_hash` + fresh row sets per version (FR-007/FR-008). SC-004 asserts pre-existing rows are byte-identical after a new version is created.                     | Pass   |
| 5   | No plaintext secrets                   | Yes — no secret added. Pre-commit `gitleaks`/`detect-secrets` pass.                                                                                                                                    | Pass   |
| 6   | Workload Identity Federation only      | N/A — no GCP auth.                                                                                                                                                                                     | N/A    |
| 7   | Docker parity dev → CI → prod          | Yes — same image runs everywhere; `db` profile picks up 0003 automatically; `openpyxl` is pure Python.                                                                                                  | Pass   |
| 8   | Production-only topology               | Yes — the CLI is shell-invoked and serves prod-only when wired by T16; no staging implied.                                                                                                              | Pass   |
| 9   | Dark launch by default                 | N/A — operator-driven CLI; no request-time behaviour to flag.                                                                                                                                          | N/A    |
| 10  | Migration approval                     | Yes — 0003 is additive (one column + UNIQUE constraint). Forward-only; reversible downgrade for local resets.                                                                                          | Pass   |
| 11  | Hybrid language                        | **Enforced at the schema.** `label_uk` required on active nodes; `descriptor_en` required on every level of active competencies (FR-012).                                                              | Pass   |
| 12  | LLM cost and latency caps              | N/A — no LLM call.                                                                                                                                                                                     | N/A    |
| 13  | Calibration never blocks merge         | N/A — no calibration here.                                                                                                                                                                             | N/A    |
| 14  | Contract-first for parallel work       | Yes — `docs/contracts/rubric.schema.json` + `docs/contracts/matrix-format.md` committed in this PR before any consumer fans out.                                                                       | Pass   |
| 15  | PII containment                        | Yes — `audit_log.subject_hash` carries the rubric payload hash, never candidate PII. The rubric tables themselves carry only labels/descriptors, no PII.                                                | Pass   |
| 16  | Configs as code                        | **Primary purpose.** `configs/rubric/*.yaml` is the source of truth; the Admin UI does not write here (out of scope).                                                                                  | Pass   |
| 17  | Specifications precede implementation  | Yes — `speckit-specify` → this `speckit-plan`; implementation follows `speckit-tasks`.                                                                                                                 | Pass   |
| 18  | Multi-agent orchestration is explicit  | Yes — `agent: backend-engineer`, `parallel: false`. Fan-out happens on T12+ post-merge.                                                                                                                | Pass   |
| 19  | Rollback is a first-class operation    | Indirect — a bad rubric change is reversed by a new PR that re-introduces the prior content (which produces yet another new version). Old session snapshots remain bound to the version they froze.    | Pass   |
| 20  | Floor, not ceiling                     | Pass.                                                                                                                                                                                                  | Pass   |

**Gate result**: PASS. No violations. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/010-t08-matrix-importer/
├── spec.md                                # Feature spec (speckit-specify)
├── plan.md                                # This file
├── research.md                            # Phase 0 — 10 implementation-altitude decisions
├── data-model.md                          # Phase 1 — payload_hash column + YAML + audit row schema
├── contracts/
│   └── plan-contract.md                   # Phase 1 — pointer to runtime contracts at the repo root
├── quickstart.md                          # Phase 1 — reviewer validation walkthrough (<10 min)
├── checklists/
│   └── requirements.md                    # From speckit-specify (passed)
└── tasks.md                               # Created by speckit-tasks (NOT this command)
```

### Source Code (repository root, after T08 merges)

```text
.
├── alembic/
│   └── versions/
│       └── 0003_rubric_payload_hash.py    # NEW — additive: + payload_hash TEXT NOT NULL UNIQUE on rubric_tree_version
├── app/
│   └── backend/
│       ├── cli/
│       │   ├── __init__.py                # NEW — package marker
│       │   └── import_matrix.py           # NEW — argparse wrapper: convert / seed / --dry-run
│       ├── db/
│       │   └── models/
│       │       └── rubric.py              # EDITED — add payload_hash Mapped[] column to RubricTreeVersion
│       ├── services/
│       │   └── rubric_importer.py         # NEW — convert + seed + canonical YAML emitter + hash; the importer engine
│       └── tests/
│           ├── cli/
│           │   ├── __init__.py            # NEW — package marker
│           │   ├── test_import_matrix_convert.py  # NEW — xlsx → YAML, byte-identical re-run, duplicate-id rejection
│           │   └── test_import_matrix_seed.py     # NEW — YAML → DB, idempotency, new-version, rename rejection, audit row
│           └── contracts/
│               ├── test_rubric_schema.py          # NEW — 5 schema-violation matrix + clean-tree baseline (SC-006/007)
│               └── test_rubric_schema_hook.py     # NEW — subprocess tests of scripts/check-rubric-schema.py
├── configs/
│   └── rubric/
│       ├── .gitkeep                       # NEW — directory placeholder
│       └── example.yaml                   # NEW — minimal valid example (sunset-equivalent: a placeholder area)
├── docs/
│   └── contracts/
│       ├── rubric.schema.json             # NEW — JSON Schema draft 2020-12 for configs/rubric/*.yaml
│       └── matrix-format.md               # NEW — human-readable xlsx layout contract
├── scripts/
│   └── check-rubric-schema.py             # NEW — pre-commit + CI guard; validates configs/rubric/*.yaml
├── .pre-commit-config.yaml                # EDITED — add new local hook `rubric-schema`
├── pyproject.toml                         # EDITED — add `openpyxl>=3.1,<4` to [project].dependencies
└── uv.lock                                 # EDITED — regenerated by `uv lock`
```

**Structure Decision**: The importer engine lives in `app/backend/services/rubric_importer.py` (mirroring T05a's services pattern); the CLI is a thin argparse wrapper at `app/backend/cli/import_matrix.py` (new sub-package — first CLI in the project; future CLIs from later tiers land alongside). The schema contract lives at the repo root (`docs/contracts/`, consistent with T05a). The new pre-commit hook script lives in `scripts/` (already copied into the dev image by T05's `COPY scripts ./scripts`).

### Task labelling (for §18 / `/speckit-tasks`)

| Task slice                                                                       | Agent              | Parallel? | Depends on                                       | Contract reference                                       |
| -------------------------------------------------------------------------------- | ------------------ | --------- | ----------------------------------------------- | -------------------------------------------------------- |
| `pyproject.toml` `openpyxl` dep + `uv lock`                                      | `backend-engineer` | false     | T01 (`pyproject.toml` exists)                   | research §1                                              |
| `docs/contracts/rubric.schema.json`                                              | `backend-engineer` | false     | spec committed                                  | the schema IS the contract                               |
| `docs/contracts/matrix-format.md`                                                | `backend-engineer` | false     | spec committed                                  | the workbook IS the contract                             |
| `app/backend/db/models/rubric.py` (+ `payload_hash`)                             | `backend-engineer` | false     | T05 model exists                                | data-model §payload_hash                                 |
| `alembic/versions/0003_rubric_payload_hash.py` (additive col + UNIQUE)           | `backend-engineer` | false     | model edited                                    | research §4 + §10 + data-model.md                         |
| `configs/rubric/.gitkeep` + `configs/rubric/example.yaml`                        | `backend-engineer` | false     | schema committed                                | clean-tree baseline (SC-006)                              |
| `scripts/check-rubric-schema.py`                                                 | `backend-engineer` | false     | schema + example committed                      | research §6 (mirrors T05a's hook)                         |
| `.pre-commit-config.yaml` add new local hook `rubric-schema`                     | `backend-engineer` | false     | hook script committed                           | T05a hook entry shape                                     |
| `app/backend/services/rubric_importer.py` (convert + canonical YAML emitter)     | `backend-engineer` | false     | openpyxl dep + schema                            | research §2/§7/§8                                        |
| `app/backend/services/rubric_importer.py` (seed + hash + new-version logic)      | `backend-engineer` | false     | convert path                                    | research §3/§4/§5/§6                                     |
| `app/backend/cli/__init__.py` + `app/backend/cli/import_matrix.py`               | `backend-engineer` | false     | importer service                                | CLI shape from this plan                                  |
| Convert tests (`test_import_matrix_convert.py` — xlsx fixture programmatic)      | `backend-engineer` | false     | importer convert                                | SC-002 + research §9                                      |
| Seed tests (`test_import_matrix_seed.py` — DB e2e, immutability, rename)         | `backend-engineer` | false     | importer seed + migration                       | SC-003/004/005/008                                        |
| Schema tests (`test_rubric_schema.py` — 5 failures + clean-tree)                 | `backend-engineer` | false     | schema + example committed                      | SC-006/007                                                |
| Hook tests (`test_rubric_schema_hook.py` — subprocess matrix)                    | `backend-engineer` | false     | hook script                                     | mirrors T05a hook tests                                   |

All T08 slices are sequential inside one PR; no sub-agent fan-out. The parallelism boundary is "T08 as a whole → afterwards, T12+ consumers of rubric content".

## Phase 0 — Outline & Research

Research output: [research.md](./research.md). 10 implementation-altitude decisions enumerated by the user input:

1. **xlsx parser library** — `openpyxl ≥ 3.1` over `pandas`/`xlrd`. Lean, pure-Python, read-only is well-supported.
2. **Canonical YAML output** — `yaml.safe_dump(sort_keys=True, default_flow_style=False, allow_unicode=True, indent=2, width=120)` + explicit list-of-nodes sort by `id`; same emitter used by convert and seed paths to guarantee deterministic re-runs.
3. **Payload hash algorithm** — SHA-256 of the concatenated canonical YAML bytes (filename-sorted), recorded in `rubric_tree_version.payload_hash` so future seed runs can replay the comparison.
4. **`rubric_tree_version.payload_hash` migration shape** — additive column NOT NULL with UNIQUE constraint; safe on empty-table prod; the migration uses a server-side default of the empty string for any pre-existing rows (academic at T08 time but defensive).
5. **Rename detection** — strict post-state check: any node id active in the prior `rubric_tree_version` payload but absent from the new payload, without being marked `retired: true` in the new payload, is a rename — reject with a precise error.
6. **Advisory lock** — fixed deterministic `int8` lock id (`hashtext('rubric.seed')::bigint` or a hard-coded constant); the seed path takes it with `pg_advisory_xact_lock` so two concurrent seed runs serialise.
7. **Single source-of-truth canonical emitter** — both `convert` and `seed` import the same `_emit_canonical_yaml(...)` helper from `rubric_importer.py`; no duplication.
8. **Workbook quirks** — merged cells spanning a key column are rejected; non-NFC unicode is normalised to NFC; semicolon-separated `evidence_examples` cells split on `;` then trimmed; HTML entities not interpreted (raw passthrough; the contract says "plain text").
9. **Fixture workbook generation** — tests build the xlsx in `tmp_path` with `openpyxl.Workbook()` at setup time; never commit a binary.
10. **Prod-DB backward-compat for `payload_hash`** — at T08-time the table is empty in prod (T05 just landed schema; no rubric seeded yet), but the migration is safe even if rows existed: it would set `payload_hash=''` for legacy rows on first apply, then a follow-up `UPDATE` could backfill if needed; UNIQUE constraint applies post-backfill. Documented in the migration docstring.

All ten decisions are resolved in `research.md` with Decision / Rationale / Alternatives Considered.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T08's design-altitude entities:
- The YAML entry shape (mirrors the JSON Schema; canonical key order).
- The `payload_hash` column added to `rubric_tree_version`.
- The `audit_log` row schema for `action='rubric.versioned'`.
- The advisory lock id used by the seed transaction.
- A cross-reference to T05's data-model.md confirming which rubric tables get NEW rows per version and which stay untouched.

### Contracts

See [contracts/plan-contract.md](./contracts/plan-contract.md) — a pointer document referencing the runtime contract artefacts at the repo root:
- `docs/contracts/rubric.schema.json` — the YAML entry contract (FR-002).
- `docs/contracts/matrix-format.md` — the workbook layout contract (FR-003).
- The CLI surface (`python -m app.backend.cli.import_matrix convert|seed [--dry-run]`) and its exit-code contract.
- The `RubricImporter` service API (consumer-facing surface for future programmatic callers in T16's GHA workflow).

### Quickstart

See [quickstart.md](./quickstart.md) — reviewer-facing walkthrough that validates T08 end-to-end in under 10 minutes: write a fixture xlsx → convert → observe YAMLs → run schema check → seed → observe DB rows + audit row → mutate descriptor + bump version → re-seed → observe new version + audit row + untouched prior version → attempt rename → observe rejection.

### Agent context update

`CLAUDE.md` carries no `<!-- SPECKIT START/END -->` markers (verified earlier; same as T05/T05a). No auto-generated block is reintroduced. **No `CLAUDE.md` edit in this step.**

### Re-evaluate Constitution Check (post-design)

The Phase 0/1 commitments (`openpyxl` for xlsx, canonical YAML emitter with `safe_dump(sort_keys=True)`, SHA-256 payload hash, additive `payload_hash` column with UNIQUE, strict rename detection, advisory lock, single source-of-truth emitter, NFC normalisation + merged-cell rejection, programmatic fixture generation, defensive backfill for legacy rows) are all consistent with §3, §4, §10, §11, §14, §16, §17, §18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
