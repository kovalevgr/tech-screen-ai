# Data model — T16 Configs-as-Code sync: rubric job

CI/policy feature: the "entities" are the gate's classification model, the CLI contract, the DB-privilege matrix, and the workflow contract. Application tables are untouched (zero migrations).

## Destructive-change taxonomy (`scripts/sync_rubric_to_db.py check`)

Input: baseline dir (YAMLs at the push's `before` commit) vs current dir (`configs/rubric/`). Nodes are flattened across files by stable id; a file-level `retired: true` marks every node inside as retired.

| Kind | Condition (baseline → current) | Severity | Gate behaviour |
| --- | --- | --- | --- |
| `NODE_REMOVED` | id present → id absent | FORBIDDEN | exit 2 always; message: retire (`retired: true`), never delete (specs/010 FR-009) |
| `NODE_RETIRED` | active → retired | DESTRUCTIVE | exit 1 unless ADR cited |
| `NODE_UNRETIRED` | retired → active | DESTRUCTIVE | exit 1 unless ADR cited (ids never reused after retire) |
| `LEVEL_REMOVED` | rank present → rank absent (node active both sides) | DESTRUCTIVE | exit 1 unless ADR cited |
| `LEVEL_RETYPED` | same rank, `descriptor_en` differs (node active both sides) | DESTRUCTIVE | exit 1 unless ADR cited |
| — | new ids/levels/files; `label_uk`/`label_en`/`evidence_examples_en`/`version` edits; retired-node level diffs | benign | not reported |

ADR citation regex: `\bADR-\d{3}\b` scanned over the collected context (head commit message + associated PR titles/bodies). Findings are emitted as GitHub annotations: `::error::` (blocking), `::notice::` (authorised destructive).

## CLI contract (`scripts/sync_rubric_to_db.py`)

```
check --baseline-dir <dir> [--rubric-dir configs/rubric] [--adr-context-file <file>]
sync  [--rubric-dir configs/rubric] [--dry-run]        # reads DATABASE_URL
```

| Exit | Meaning |
| --- | --- |
| 0 | check: no destructive change, or destructive + citation · sync: seeded or hash-match no-op |
| 1 | check: destructive without citation · sync: DB unreachable (cost-idle hint) or importer refusal (schema/rename) |
| 2 | check: FORBIDDEN removal · both: configuration error (missing dir / `DATABASE_URL`) |

`sync` internals: 20 s pre-flight `asyncpg.connect` (owns the wake-hint message, `SYNC_ENV` names the environment) → `RubricImporter.seed(configs/rubric, dsn)`. All write semantics are the importer's (T08): payload-hash no-op, new `rubric_tree_version` + full fresh tree per change, advisory lock 987654321, one `audit_log` receipt.

## DB privileges (`scripts/cloud-db-grants.sql`, user `techscreen-flag-sync@tech-screen-493720.iam`)

| Table | Grant | Why exactly this |
| --- | --- | --- |
| `feature_flag` | SELECT, INSERT, UPDATE | T05a upsert (unchanged; the only UPDATE in the file) |
| `rubric_tree_version` | SELECT, INSERT | latest-hash no-op check; INSERT..RETURNING id |
| `stack` | SELECT, INSERT | INSERT..RETURNING id (RETURNING needs SELECT) |
| `competency_block` | SELECT, INSERT | INSERT..RETURNING id |
| `competency` | SELECT, INSERT | INSERT..RETURNING id + prior-version name read (FR-009 rename check) |
| `topic` | INSERT | plain INSERT; no reads, no RETURNING |
| `level` | INSERT | plain INSERT; no reads, no RETURNING |
| `audit_log` | INSERT | FR-010 receipt; the one §3-permitted verb; UPDATE/DELETE trigger-blocked for every role (migration 0001) |
| other five §3 tables | — | nothing, ever |

No UPDATE/DELETE on any rubric table exists to be misused — §4/ADR-018 enforced at the privilege layer too.

## Workflow contract (`.github/workflows/sync-configs.yml`)

Renamed from `sync-feature-flags.yml` (T16). Shared push triggers: `configs/feature-flags.yaml`, `docs/contracts/feature-flag.schema.json`, `configs/rubric/**`, `docs/contracts/rubric.schema.json`, the workflow self-path; plus `workflow_dispatch`. Permissions: `id-token: write`, `contents: read`, `pull-requests: read` (new — PR-body lookup).

| Job id | Matrix | Steps (order) |
| --- | --- | --- |
| `sync-feature-flags` | dev, prod · fail-fast: false | unchanged from T06 (checkout → python → deps → flag-schema check → guard → WIF → pinned proxy → upsert) |
| `sync-rubric` | dev, prod · fail-fast: false | checkout `fetch-depth: 0` → python → deps → rubric-schema check → **baseline extraction** (`github.event.before` via env; fallbacks `HEAD~1`/empty with warnings) → **ADR-context collection** (`git log -1` + `gh api commits/{sha}/pulls`, output to file) → **destructive gate** → guard → WIF → pinned proxy → seed (`SYNC_ENV` = matrix env) |

Invariants: no `needs:` between jobs; identical WIF/instance/user env blocks (values from the T06 contract, `specs/018` data-model); proxy binary sha256 `90fb6229…df39` pinned in both jobs; no `github.event.*` string ever interpolated into `run:` text (env/file indirection only).

## State transitions (per environment, per merge)

1. **Benign diff, awake DB**: gate 0 → seed creates version N+1 (or no-op) → green.
2. **Destructive diff, no citation**: gate 1 → job red **before** WIF/proxy/DB; DB state unchanged.
3. **Destructive diff, citation**: gate 0 (notice) → seed applies → green; audit receipt + ADR reference in the merged PR form the trail.
4. **Forbidden removal**: gate 2 → red; even if bypassed, importer's `RenameForbiddenError` refuses at seed.
5. **Sleeping DB**: gate 0 → pre-flight fails ≤ 20 s → red with wake command → operator wakes → **Re-run failed jobs** (baseline preserved) → path 1/3.
