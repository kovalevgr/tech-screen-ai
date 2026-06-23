# CI

The canonical reference for the TechScreen CI pipeline: which jobs run, what they enforce, how the §10 migration-approval gate works, and how to debug a failing check. Sibling of [`docker.md`](./docker.md).

## 0. Why this doc exists

Every PR against `main` runs `.github/workflows/ci.yml`. Four jobs gate merge; a conditional fifth surfaces migration SQL and flags destructive DDL. This page is the contract — read it when a check fails or before you configure branch protection. T10 introduced it; see [`specs/012-t10-ci-pipeline/`](../../specs/012-t10-ci-pipeline/).

## 1. The jobs

| Job | Required? | What it enforces |
| --- | --------- | ---------------- |
| **backend** | yes | Inside the test-stack `dev` image: `alembic upgrade head`, the full `pytest app/backend/tests` suite, `ruff check`, `ruff format --check`, `mypy --strict`, and the OpenAPI byte-identical regen (`generate_openapi --check`). |
| **frontend** | yes | Inside the frontend image: `pnpm install --frozen-lockfile`, `pnpm exec eslint . --max-warnings=0`, `pnpm exec tsc --noEmit`, `pnpm test` (jest), `pnpm tokens:check` (design-token drift). |
| **smoke** | yes | `bash scripts/smoke-docker-stack.sh` on the runner's host Docker — brings up the dev stack, asserts `/health` 200 + frontend 200, tears down. |
| **lint** | yes | `pre-commit run --all-files` — gitleaks, detect-secrets, actionlint, ruff, ruff-format, shellcheck, the pygrep guards, and the project's custom hooks (`no-provider-sdk-imports`, `feature-flag-registered`, `rubric-schema`). `SKIP`-listed here: the frontend-scoped hooks (`eslint`, `tokens-drift`, `visual-discipline`) — covered by the `frontend` job — and `terraform_validate` (see §Terraform validation below). |
| **migration-sql-render** | no (informational) | Only when a PR touches `alembic/versions/**`: renders the migration SQL into a PR comment + auto-applies `needs-adr` on destructive DDL. |

All jobs run in parallel. The four required jobs target < 5 minutes on warm cache.

## 2. Branch-protection contract (operator-applied)

Configure GitHub → Settings → Branches → branch protection for `main` to **require these status checks**:

```
backend
frontend
smoke
lint
```

Do **not** add `migration-sql-render` to the required set — it is skipped on non-migration PRs, and a skipped required check can stall merge. It is informational: its output is a PR comment + a label, not a pass/fail gate. CI cannot self-configure branch protection; this is a one-time operator action.

## Terraform validation (deferred to a dedicated job)

`terraform_validate` lives in `.pre-commit-config.yaml` and runs in **local** pre-commit for contributors who have the `terraform`/`tofu` binary. It is **`SKIP`-listed in the CI `lint` job on purpose**: the hook shells out to `terraform`, and its `terraform init` would try to configure the **`gcs` remote backend** (`infra/terraform/backend.tf`), which needs live GCP credentials the CI runner does not have. Forcing it into the Python-only lint runner would either fail (no binary) or hang/error (no backend auth).

CI enforcement of Terraform is therefore deferred to a **dedicated `terraform` job** — a follow-up task — that does an offline check: `hashicorp/setup-terraform` → `terraform -chdir=infra/terraform init -backend=false` → `terraform validate`. It runs in its own runner with its own settings (`-backend=false` is scoped to that job and never touches real state) and does not affect any other job. Until that job lands, Terraform is **not** validated in CI — only locally. (`infra/terraform` is 222 lines with a committed `.terraform.lock.hcl`; the follow-up is ~15 lines of YAML, no infra-code changes expected. This mirrors the §5 reviewer-agent and the live-GCP-only honesty in the plan.)

## 3. The migration-approval gate (§10)

Constitution §10 requires human review of every schema change before it reaches prod. The flow:

1. A PR adds/edits a file under `alembic/versions/`.
2. The `migration-sql-render` job runs `scripts/ci-render-migration-sql.sh` (offline `alembic upgrade head --sql`) and posts the rendered DDL as a PR comment inside a collapsed `<details>` block. The comment carries the hidden marker `<!-- ci:migration-sql-render -->` and is **updated in place** on every push (never duplicated).
3. A human reviewer expands the comment, reads the SQL, and — if satisfied — applies the **`migration-approved`** label. CI never applies this label; it is a human gate.
4. `/deploy` (T06a, future) refuses to deploy a PR that touched `alembic/versions/` without the `migration-approved` label.

## 4. Destructive-DDL detection + `needs-adr`

`scripts/ci-detect-destructive-ddl.sh` scans the changed migrations for the §10-forbidden patterns:

| Pattern | Concern |
| ------- | ------- |
| `DROP COLUMN` | Column removal — data loss |
| `DROP TABLE` | Table removal — catastrophic data loss |
| `ALTER COLUMN … TYPE` | Type narrowing — truncation / cast failure |

On a match, CI auto-applies the **`needs-adr`** label. The PR cannot merge (reviewer / human gate) until an ADR is linked in the PR description (a `adr/<NNN>-*.md` reference). Additive DDL (`ADD COLUMN`, `CREATE TABLE`) is fine and is not flagged.

> Our migrations express DDL as raw `op.execute("…")` strings, so the detector matches inside string literals — that is exactly where the destructive DDL lives.

## 5. Reviewer agent — DEFERRED (placeholder today)

The implementation plan calls for the `reviewer` sub-agent to run on every PR. The real integration (running Claude Code / the Anthropic API against the `reviewer` agent definition inside CI) needs:

- an Anthropic API key in repo secrets, and
- per-PR cost controls (token ceiling, trivial-PR opt-out),

neither of which is in place yet. Shipping an uncontrolled API key to CI would violate the spirit of constitution §12 (cost caps) before the guardrails exist.

So T10 ships an **honest placeholder**: `scripts/ci-reviewer.sh` prints a DEFERRED message and exits 0; the `lint` job calls it so the slot is visible in the job graph. **The real Claude-in-CI integration is a follow-up task** with the API-key + cost-control story. Until then, human review is the gate.

## 6. Troubleshooting

**The `backend` job fails on a test.** Reproduce locally: `docker compose -f docker-compose.test.yml --profile db run --rm backend sh -c "alembic upgrade head && pytest app/backend/tests -v"`. Fix the test or the code; CI re-runs on push.

**The `migration-sql-render` job fails to post a comment.** The job needs `pull-requests: write` permission (granted in the workflow). If the repo's default `GITHUB_TOKEN` permissions are set to read-only in Settings → Actions, raise them to "Read and write".

**The migration render errors.** Run `bash scripts/ci-render-migration-sql.sh` locally; it shells out to `docker compose ... alembic upgrade head --sql`. A render failure usually means the migration file has a Python error — fix it first.

**Cold-cache CI is slow (~12 min).** Expected on the first run after a cache eviction or a Dockerfile/lockfile change. Warm-cache runs are < 5 min. The Buildx `type=gha` cache restores the heavy `uv sync` / `pnpm install` layers.

**`lint` fails on a hook you didn't touch.** Run `pre-commit run --all-files` locally to reproduce; the failing hook names the file. The frontend hooks (eslint/tokens/visual-discipline) run in the `frontend` job, not `lint`.

## 7. Caching strategy

- **Image layers**: Buildx `type=gha` cache, scoped per image (`scope=backend` / `scope=frontend`). Keyed by the Dockerfile + lockfile hashes; turns a ~3-minute `uv sync` into a ~10-second restore.
- **pnpm store**: `actions/cache` on the pnpm store path, keyed by the lockfile.
- **pre-commit envs**: `actions/cache` on `~/.cache/pre-commit`, keyed by `.pre-commit-config.yaml`.
