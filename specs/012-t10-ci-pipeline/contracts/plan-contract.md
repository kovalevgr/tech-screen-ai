# Plan-time Contract Pointer: T10

Pointer document. The runtime artefacts at the repo root ARE the contract.

## Runtime contracts

| Contract | Path | Owner | Notes |
| -------- | ---- | ----- | ----- |
| **CI workflow** | `.github/workflows/ci.yml` | T10 | 5 jobs (backend / frontend / smoke / lint / migration-sql-render); concurrency-cancel; minimal permissions. |
| **Migration SQL renderer** | `scripts/ci-render-migration-sql.sh` | T10 | `alembic upgrade head --sql` → stdout (offline). |
| **Destructive-DDL detector** | `scripts/ci-detect-destructive-ddl.sh` | T10 | scans changed migrations; sets `needs_adr` output; exit 0 always. |
| **Reviewer placeholder** | `scripts/ci-reviewer.sh` | T10 (placeholder) / follow-up (real) | prints DEFERRED, exits 0. |
| **CI reference** | `docs/engineering/ci.md` | T10 | the human-readable contract: jobs, labels, gate, troubleshooting. |
| **Smoke script** | `scripts/smoke-docker-stack.sh` | T09 (unchanged) | invoked by the `smoke` job. |

## Consumer contracts (what later tasks bind to)

| Consumer | Binds to | How |
| -------- | -------- | --- |
| **T06a** (`/deploy`, future) | the `migration-approved` label | `/deploy` refuses on a PR that touched `alembic/versions/` without the label. |
| **T11** (Tier-1 smoke gate) | the green CI + `scripts/smoke-docker-stack.sh` | the Tier-1 checkpoint requires CI green + runs the smoke. |
| **The operator** | the required-status-checks set | configures branch protection on `main` to require backend / frontend / smoke / lint. |
| **The follow-up reviewer-agent task** | `scripts/ci-reviewer.sh` + the workflow slot | swaps the placeholder for the real Claude-in-CI invocation with API key + cost controls. |

## Honest scope boundary

The GitHub-only behaviours — PR comment posted + updated-in-place, label application, concurrency-cancel, branch protection — can only be exercised on GitHub, not locally. T10 validates by: `actionlint` (workflow syntax), `shellcheck` (the bash helpers), local dry-runs of the two functional helpers, the 138-test regression re-run, and a documented **manual first-PR-on-GitHub checklist** (`quickstart.md`) the operator runs once. This is the same honesty as T05a's inert WIF workflow and T06's "apply needs a live project".

## Verification contracts (referenced by `tasks.md`)

| Check | What it locks in | Spec ref |
| ----- | ---------------- | ------- |
| `actionlint .github/workflows/ci.yml` exits 0 | workflow is syntactically valid | SC-009 |
| `shellcheck scripts/ci-*.sh scripts/smoke-docker-stack.sh` clean | bash helpers are sound | research §10 |
| `ci-render-migration-sql.sh` produces SQL locally | the render path works | SC-002 (proxy) |
| `ci-detect-destructive-ddl.sh` flags a DROP-COLUMN fixture, passes an ADD-COLUMN fixture | the detector works | SC-005 (proxy) |
| 138-test backend suite green in the test stack | regression baseline | SC-007 |
| `pre-commit run --all-files` clean (with SKIP for frontend hooks documented) | the lint job will pass | SC-006 / SC-008 |
| `docs/engineering/ci.md` answers the 4 contributor questions | the docs are sufficient | SC-006 |
