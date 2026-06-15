# Plan-time Contract Pointer: T08

Pointer document, not a contract. The actual contract artefacts live at repo paths so downstream tasks (T12+ Position Template, T16 sync workflow) reference the runtime paths.

## Runtime contracts

| Contract | Path | Owner | Notes |
| -------- | ---- | ----- | ----- |
| **YAML schema** | `docs/contracts/rubric.schema.json` | T08 | JSON Schema draft 2020-12 for every `configs/rubric/*.yaml`. Validated by the pre-commit hook AND by the CLI at runtime (defence in depth, FR-011). |
| **Matrix-format contract** | `docs/contracts/matrix-format.md` | T08 | Human-readable description of the Excel workbook layout (one sheet per stack, header convention, cell semantics, quirk rules from research §8). |
| **Database schema** | `alembic/versions/0003_rubric_payload_hash.py` | T08 | Adds `rubric_tree_version.payload_hash TEXT NOT NULL DEFAULT ''` + UNIQUE constraint. The only T08 migration. |
| **Source-of-truth YAMLs** | `configs/rubric/*.yaml` | T08 (ongoing — every rubric-touching PR appends/edits) | Git-tracked rubric content. Old versions live in git history; the runtime DB mirror is materialised by the seed path. |
| **CLI surface** | `python -m app.backend.cli.import_matrix convert|seed [--dry-run] ...` | T08 | The shell-facing contract. Exit-code rules: 0 = success / no-op; 1 = validation failure; 2 = configuration error. |
| **Service surface** | `app.backend.services.rubric_importer.RubricImporter` | T08 | The Python contract for future programmatic callers (T16 GHA workflow). |
| **Schema hook** | `scripts/check-rubric-schema.py` | T08 | Pre-commit + CI guard; validates every `configs/rubric/*.yaml` against the schema. Lives in `scripts/` (already copied into the dev image by T05). |

## T16 boundary

T16 (Configs-as-Code sync — YAML → DB on merge) extends T05a's `sync-feature-flags.yml` workflow with a parallel rubric-sync job that calls `python -m app.backend.cli.import_matrix --seed` on every push to `main`. T08 does NOT ship the workflow change; it ships the CLI that T16 will invoke. The CLI's exit-code contract above is what T16 binds to.

## Test contracts (referenced by `tasks.md`)

| Test | What it locks in | Spec ref |
| ---- | ---------------- | ------- |
| `test_import_matrix_convert.py` | Convert path: xlsx → YAML, byte-identical re-run, duplicate-id rejected non-zero | SC-002 |
| `test_import_matrix_seed.py` | Seed path: idempotent on unchanged; new version on content change; §4 prior-row-immutability assertion; rename rejection; audit-log emission | SC-003 / SC-004 / SC-005 / SC-008 |
| `test_rubric_schema.py` | 5 schema-violation fixtures + clean-tree baseline | SC-006 / SC-007 |
| `test_rubric_schema_hook.py` | Subprocess invocations of the pre-commit hook script against fixture trees | mirrors T05a |
