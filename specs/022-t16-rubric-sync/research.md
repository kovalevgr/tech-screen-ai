# Research — T16 Configs-as-Code sync: rubric job

Decisions verified against the working tree of 2026-07-05 (main = PR #18 merge). Live-GCP claims are marked — nothing cloud-side was executed during this phase.

## R1. Renaming the workflow file — safe, with known cosmetic cost

**Decision**: rename `sync-feature-flags.yml` → `sync-configs.yml` (via `git mv`).

**Evidence**:
- The workflow triggers on `push` to `main` + `workflow_dispatch` only — it never runs on `pull_request`, so it cannot be (and a repo sweep shows nothing configures it as) a required PR status check. Required checks key off **job names** anyway, not filenames.
- `grep -rn "sync-feature-flags"` across the repo: references live in `infra/terraform/outputs.tf`/`iam.tf` (comments/description), `docs/engineering/cloud-setup.md`, `docs/engineering/feature-flags.md`, `docs/engineering/implementation-plan.md`, `scripts/sync_feature_flags_to_db.py` (docstring), the workflow's own `paths:` self-entry — all updated in this PR — plus historical records under `specs/009` and `specs/018`, which are deliberately left as-is (they describe the state of their time; same convention as ADR-009's preserved body).
- No `workflow_run:`/`workflow_call:`/`needs:` edges from any other workflow (`ci.yml` checked).
- Costs accepted: the Actions UI lists pre-rename runs under the old workflow name (cosmetic); file history needs `git log --follow -M30%` — verified: the T16 rewrite is R031 (31 % similar), below the default 50 % rename threshold, so plain `--follow` stops at the rename commit.
- One real Terraform diff: the SA resource `description` string was updated (no longer claims feature_flag-only privileges) — the operator's next `terraform apply` shows a single in-place SA update.

## R2. Reuse the importer — wrap, don't reimplement

**Decision**: `scripts/sync_rubric_to_db.py sync` wraps `RubricImporter.seed()` directly; the T08 CLI (`app/backend/cli/import_matrix.py seed`) is NOT invoked because it routes the DSN through `app.backend.settings.Settings` (pydantic-settings — an extra CI dependency for no benefit) and its output/exit contract lacks the cost-idle guidance T16 needs.

**Evidence**: the importer module's import closure is exactly `asyncpg` + `pyyaml` + `jsonschema` (openpyxl is a function-local import on the convert path; `app/backend/__init__.py` is empty; `app/` is a namespace package). The `sync-rubric` job therefore installs the same three wheels the flags job already installs. The wrapper inserts the repo root into `sys.path`, keeping the job free of `PYTHONPATH` plumbing.

Idempotency, §4 immutability, the advisory lock, FR-009 rename rejection, and the FR-010 audit receipt all come from the importer unchanged — T16 adds zero write-path logic.

## R3. Destructive taxonomy — aligned with specs/010, defined where the plan was vague

specs/010 defines one hard structural rule (FR-009: a stable id may never disappear or be renamed — retire + introduce) which the importer enforces against the DB. The T16 plan text names "removed topic, retyped level" as ADR-gated. Reconciliation:

| Kind | Trigger | Class | Rationale |
| --- | --- | --- | --- |
| `NODE_REMOVED` | id in baseline, absent from payload | **FORBIDDEN** (exit 2, ADR irrelevant) | FR-009 is absolute; the gate gives the actionable message *before* the importer's DB error would |
| `NODE_RETIRED` | `retired` false→true (node- or file-level) | DESTRUCTIVE | this *is* "removed topic/competency" in a codebase where deletion is impossible |
| `NODE_UNRETIRED` | `retired` true→false | DESTRUCTIVE | schema: ids are "never reused after retire" — resurrection needs governance |
| `LEVEL_REMOVED` | rank present in baseline's active node, absent now | DESTRUCTIVE | shrinks the scoring scale going forward |
| `LEVEL_RETYPED` | same rank, `descriptor_en` differs | DESTRUCTIVE | the descriptor is the Assessor's input (§11/ADR-008); rewording it changes scoring semantics — yes, even a typo fix needs a citation, which is the honest reading of the plan text |
| label/evidence/`version` edits, new nodes/levels/files | — | benign | presentation or pure addition |

Level checks are suppressed for nodes retired on either side (the retire finding covers the node once).

## R4. Baseline resolution in a push-triggered run

**Decision**: baseline = `github.event.before`, extracted by the workflow (`git ls-tree`/`git show` at `fetch-depth: 0`) into a temp dir the Python gate reads — the gate itself stays git-free (and therefore unit-testable with plain directories).

Why not the DB as baseline: the materialised tree stores neither `retired` flags nor `label_*`/`descriptor_en` provenance sufficient to reconstruct the YAML projection (competency/topic rows carry only `name`; retired nodes are materialised indistinguishably) — a DB baseline would be lossy exactly where the taxonomy needs precision. The DB check remains the importer's job.

Fallback chain (each with a `::warning::`): `before` missing / all-zeros / unresolvable (force push) → `HEAD~1` (correct for single-PR merge pushes, approximate for multi-commit pushes) → no parent at all (initial commit) → empty baseline, everything counts as new. Documented recovery for the degraded case: **Re-run failed jobs** re-uses the original event payload including `before`, so wake-the-DB reruns keep the true baseline; only a fresh `workflow_dispatch` degrades.

## R5. Getting the PR body in a push-triggered run

There is no `github.event.pull_request` on `push`. **Decision**: scan two sources, both collected into a file (never interpolated into script text — commit messages and PR bodies are attacker-influenced):

1. Head commit message via `git log -1 --format=%B "$GITHUB_SHA"` (covers squash merges, which inline the PR title/description, and direct pushes).
2. Bodies+titles of PRs associated with the head SHA via `gh api repos/{repo}/commits/{sha}/pulls` (GA endpoint; returns the merged PR for both merge-commit and squash strategies). Requires `pull-requests: read` — added to the workflow's permissions block.

Documented fallback: if the API call fails (rate limit, token scope), a warning is emitted and the commit message alone decides. Citation regex `\bADR-\d{3}\b` (word-bounded so `BADR-123`/`ADR-12`/`ADR-1234` don't satisfy the gate).

## R6. Grants — least privilege, derived from the importer's actual statements

Read from `rubric_importer.py` line by line: the seed path executes `SELECT` on `rubric_tree_version` (latest hash) and `competency` (prior-version names), `INSERT .. RETURNING id` on `rubric_tree_version`/`stack`/`competency_block`/`competency` (PostgreSQL requires SELECT privilege for the columns a RETURNING clause reads), plain `INSERT` on `topic`/`level`, and one plain `INSERT` on `audit_log`. Zero UPDATE, zero DELETE, anywhere. `pg_advisory_xact_lock` needs no grant; PG17 grants schema `public` USAGE to PUBLIC (the live flags job already proves the IAM user resolves the schema).

**The `audit_log` INSERT is a deliberate, narrow §3-table grant** — deviation from the T06-era "the §3 tables are not touched by this script" posture, resolved as follows: specs/010 FR-010 makes the receipt row mandatory (skipping it would silently break §1 auditability); §3's invariant is *append-only*, i.e. INSERT is the exactly-permitted verb; and migration 0001's `reject_audit_mutation()` trigger blocks UPDATE/DELETE for **every** role irrespective of grants, so this grant cannot weaken the invariant even in principle. No SELECT is granted (the importer never reads audit_log). The five remaining §3 tables get nothing.

## R7. Sleeping-instance failure mode (cost-idle)

With `activation-policy=NEVER`, the Auth Proxy still binds 127.0.0.1:5432 (the workflow's TCP wait loop passes) but the instance dial fails at connect time. **Decision**: the sync wrapper does a bounded pre-flight `asyncpg.connect(timeout=20)`; on any `OSError`/timeout/`PostgresError` it emits one `::error::` containing the literal `scripts/cloud-sql-power.sh wake <matrix.env>` command (env name injected via the job's `SYNC_ENV`) and the re-run guidance, exit 1. The gate and schema validation run *before* any cloud step, so policy failures cost no GCP round-trips at all.

## R8. Merge-order dependency: branch `019-cloud-sql-idle`

Cost-idle mode (cloud-setup.md § Cost-idle, `scripts/cloud-sql-power.sh`, the Terraform `ignore_changes[settings.activation_policy]`) lives on the unmerged branch `019-cloud-sql-idle` (commit f49f7ae). T16's docs and error messages reference the wake script by path. **Decision**: reference it anyway (the owner's cost-idle decision of 2026-07-05 is in force operationally) and record here: **merge 019 before or with T16**; if 019 is abandoned, replace the wake references with the raw `gcloud sql instances patch <instance> --activation-policy ALWAYS` command. Follow-up for 019 (or a trailing commit): its "wake before merging configs" rule names only `configs/feature-flags.yaml` — extend it to `configs/rubric/**`.

## R9. Explicitly out of scope

- Renaming the `techscreen-flag-sync@` service account to match its widened role — a live-resource churn (new SA, WIF rebinding, SQL user re-creation, grants re-apply) with zero security benefit; the display name already says "configs-as-code sync". Revisit if a second CI identity ever becomes necessary.
- Retrofitting the cost-idle pre-flight/wake-hint into `scripts/sync_feature_flags_to_db.py` — its generic connect error already fails fast; worth a small follow-up, not a T16 blocker.
- Any importer behaviour change (e.g. `is_active` handling of prior versions) — T08's contract, not T16's.
- Per-job path filtering (flags-only merge also runs the rubric job): both jobs are idempotent no-ops on unchanged payloads; a `dorny/paths-filter` dependency buys nothing but supply-chain surface.
