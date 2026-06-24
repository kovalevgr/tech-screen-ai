# Phase 1 Data Model: T10 — CI pipeline

No database entities. T10's "entities" are operational — the moving parts of the CI contract a reviewer can grep against `.github/workflows/ci.yml`.

---

## 1. Job matrix

| Job | Required for merge? | Runs when | Enforces |
| --- | ------------------- | --------- | -------- |
| `backend` | **yes** | every PR + push to main | `alembic upgrade head`; full `pytest app/backend/tests`; `ruff check`; `ruff format --check`; `mypy --strict`; OpenAPI byte-identical regen |
| `frontend` | **yes** | every PR + push to main | `pnpm install --frozen-lockfile`; `pnpm exec eslint . --max-warnings=0`; `pnpm exec tsc --noEmit`; `pnpm test` (jest); `pnpm tokens:check` |
| `smoke` | **yes** | every PR + push to main | `bash scripts/smoke-docker-stack.sh` (dev stack up → /health 200 → :3000 200 → teardown) |
| `lint` | **yes** | every PR + push to main | `pre-commit run --all-files` (gitleaks, detect-secrets, actionlint, terraform_validate, ruff, ruff-format, the pygrep guards, no-provider-sdk-imports, feature-flag-registered, rubric-schema, shellcheck; frontend-scoped hooks SKIP-listed) |
| `migration-sql-render` | **no** (informational) | only when `alembic/versions/**` changed | renders the migration SQL into a PR comment; auto-applies `needs-adr` on destructive DDL |

---

## 2. PR label set

| Label | Applied by | Cleared by | Meaning |
| ----- | ---------- | ---------- | ------- |
| `migration-approved` | **human** (maintainer) | human, or auto on a new migration push (convention) | The maintainer has reviewed the rendered SQL and approves it for deploy. `/deploy` (T06a, future) refuses to proceed on a migration PR without this label. |
| `needs-adr` | **CI** (auto, via `ci-detect-destructive-ddl.sh` + github-script) | human, once an ADR is linked in the PR | The PR's migration contains destructive DDL (`DROP COLUMN` / `DROP TABLE` / type-narrowing `ALTER`). Merge is blocked (by reviewer agent / human) until an ADR is linked. |

CI never auto-applies `migration-approved` (FR-009). CI auto-applies `needs-adr` (FR-008).

---

## 3. PR-comment marker contract

- The migration-SQL comment's first line is the hidden HTML marker: `<!-- ci:migration-sql-render -->`.
- The SQL body lives inside a collapsed `<details><summary>Rendered migration SQL</summary> ... </details>` block.
- On a re-run, `actions/github-script` finds the comment by the marker substring and **edits it in place** (SC-003 — no duplicates).

---

## 4. Destructive-DDL pattern table

| Pattern (case-insensitive) | §10 concern |
| -------------------------- | ----------- |
| `DROP\s+COLUMN` | Column removal — data loss |
| `DROP\s+TABLE` | Table removal — catastrophic data loss |
| `ALTER\s+COLUMN\s+\w+\s+TYPE` | Type narrowing — potential truncation / cast failure |

Scanned across the changed `alembic/versions/*.py` (diff against the PR base). Matching inside `op.execute("…")` string literals is intended (that is where our DDL lives). The detector sets `needs_adr=true|false` on `$GITHUB_OUTPUT` and always exits 0 (the label, not the exit code, is the signal).

---

## 5. Required-status-checks set (operator-configured)

The operator configures GitHub branch protection on `main` to require:

```
backend
frontend
smoke
lint
```

`migration-sql-render` is **not** in the required set (it's skipped on non-migration PRs; a skipped required check can stall merge). Documented in `docs/engineering/ci.md` §2; applied by the operator in repo settings — CI cannot self-configure branch protection.

---

## 6. Concurrency contract

- `group`: `${{ github.workflow }}-${{ github.ref }}`
- `cancel-in-progress`: `true`

A new push to a PR head ref cancels the prior in-flight run for that ref.

---

## 7. Cross-reference to prior work

- **T09** (`scripts/smoke-docker-stack.sh`, `docs/engineering/docker.md`): the smoke job invokes the script; `ci.md` is a sibling of `docker.md`.
- **T05** (Dockerfile `COPY scripts ./scripts`): the migration-render helper is in the image automatically.
- **T05a / T08** (the `feature-flag-registered` + `rubric-schema` pre-commit hooks): the `lint` job runs them every PR.
- **T06a** (`/deploy`, future): binds to the `migration-approved` label contract this task documents.
- **T11** (Tier-1 smoke gate, future): invokes the same `scripts/smoke-docker-stack.sh` and depends on CI being green.
