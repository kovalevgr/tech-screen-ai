# Phase 0 Research: T10 — CI pipeline

10 implementation-altitude decisions. Most pre-resolved by the user input on this branch; reproduced as the project's canonical record. Each carries Decision / Rationale / Alternatives.

---

## §1 — Reviewer-agent invocation

**Decision**: Ship a placeholder. `scripts/ci-reviewer.sh` prints `Reviewer agent invocation DEFERRED — see docs/engineering/ci.md §Reviewer agent` and exits 0. A workflow step calls it (so the slot is visible in the job graph) but it never blocks merge. The real Claude-in-CI integration is a documented follow-up task.

**Rationale**:
- The mechanism — running Claude Code (or an Anthropic API client) inside a GH runner against the `reviewer` agent definition — requires an **Anthropic API key in repo secrets** and **cost controls** (per-PR token ceiling, opt-out for trivial PRs). Neither is in place, and adding an uncontrolled API key to CI now would violate the spirit of §12 (cost caps) before the guardrails exist.
- Shipping the placeholder keeps the job-graph slot honest: a contributor sees "reviewer (deferred)" rather than nothing, and `ci.md` explains where the real integration is tracked.
- The implementation-plan's "reviewer sub-agent invoked on every PR" remains the target; T10 is honest that the wiring is not yet there.

**Alternatives considered**:
- *Wire the real Claude-in-CI now* — rejected: no API key + no cost controls → uncontrolled spend risk, and the secrets-management story belongs to a dedicated task.
- *Omit the step entirely* — rejected: the placeholder makes the deferral visible and self-documenting.

---

## §2 — Cache strategy

**Decision**: Buildx GitHub-Actions cache (`type=gha`) for the backend + frontend image layers; `actions/cache` for the pnpm store (`~/.local/share/pnpm/store` or the project's `.pnpm-store`). The heaviest layer — `uv sync --frozen` in the backend builder stage — is cached by buildx.

**Rationale**:
- `type=gha` is the canonical Buildx cache backend on GitHub runners; it persists layers across runs keyed by the Dockerfile + lock-file hash, turning a ~3-minute `uv sync` into a ~10-second cache restore on warm runs.
- The pnpm store cache is separate from image-layer cache because the `frontend` job runs `pnpm install` inside the container against a mounted store; caching the store directory avoids re-downloading the dependency tree.
- Combined, these keep the warm-cache run under the 5-minute SC-001 budget.

**Alternatives considered**:
- *`actions/cache` for raw Docker layers* — clunkier than buildx `type=gha`; rejected.
- *No cache* — every run pays the full `uv sync` + `pnpm install` cost (~5 min each); blows the budget. Rejected.

---

## §3 — Migration SQL offline render

**Decision**: `scripts/ci-render-migration-sql.sh` runs `alembic upgrade head --sql` inside a fresh test-stack backend container. Offline mode renders the full DDL without a live DB connection (T05 research §1 confirmed our `env.py` offline path emits all `op.execute(...)` raw SQL verbatim).

**Rationale**:
- Offline `--sql` is exactly the dry-run §10 wants: it shows the SQL that *would* run, for human review, without touching any database.
- Reusing the existing test-stack container means no new image, no new alembic config — the script is a thin wrapper.

**Alternatives considered**:
- *Run against a live ephemeral Postgres and capture the applied SQL* — heavier (needs a DB up) and offline `--sql` already gives the canonical render. Rejected.
- *Parse the migration Python AST* — fragile + duplicates what alembic already does. Rejected.

---

## §4 — Destructive-DDL regex set

**Decision**: `scripts/ci-detect-destructive-ddl.sh` scans the changed `alembic/versions/*.py` for (case-insensitive):
- `DROP\s+COLUMN`
- `DROP\s+TABLE`
- `ALTER\s+COLUMN\s+\w+\s+TYPE` (the type-narrowing case)

It scans the file contents of the changed migrations (determined by `git diff --name-only origin/main...HEAD -- 'alembic/versions/*.py'`). Sets `needs_adr=true|false` on `$GITHUB_OUTPUT`; exits 0 always (detection is informational; the label is the signal, not a hard fail).

**Rationale**:
- Our migrations express structural DDL as raw `op.execute("ALTER TABLE … DROP COLUMN …")` strings (the T05/T05a/T08 pattern). So matching **inside string literals is correct here** — that's exactly where destructive DDL lives. This is the opposite of the usual "don't match inside comments" concern: there is no false-positive risk from a docstring saying "we DROP COLUMN" because such a docstring is itself a signal worth a human glance.
- Exit-0-always keeps the job green; the `needs-adr` label is the durable signal a reviewer sees, not a red X that a contributor might bypass by reverting the detection.

**Alternatives considered**:
- *Hard-fail the job on destructive DDL* — rejected: §10 wants ADR-linked review, not an absolute block; the label + reviewer is the right gate.
- *Parse the SQL semantically* — overkill; the three regexes cover the §10-named cases.

---

## §5 — PR-comment marker

**Decision**: The migration-SQL PR comment carries a hidden HTML marker `<!-- ci:migration-sql-render -->` as its first line. `actions/github-script` lists the PR's comments, finds the one containing the marker, and updates it in place (or creates it if absent).

**Rationale**:
- An invisible HTML marker is the standard find-and-update idiom; it survives across force-pushes so the comment is updated, never duplicated (SC-003).
- `actions/github-script` runs inline JS with the `GITHUB_TOKEN`, no extra action dependency.

**Alternatives considered**:
- *A third-party "sticky comment" action* — adds a supply-chain dependency for what github-script does in ~15 lines. Rejected.
- *Always create a new comment* — clutters the PR; fails SC-003. Rejected.

---

## §6 — Branch-protection required checks

**Decision**: The four primary jobs — `backend`, `frontend`, `smoke`, `lint` — are the required status checks on `main`. The conditional `migration-sql-render` is **informational** (not required), because it only runs on migration PRs and its output is a comment + label, not a pass/fail gate. `docs/engineering/ci.md` documents the exact set; the operator configures it in GitHub repo settings (CI cannot self-configure branch protection).

**Rationale**:
- Making `migration-sql-render` required would block every non-migration PR (the job is skipped, and a skipped required check can stall merge depending on settings). Keeping it informational avoids that footgun.
- The four primary checks are always-run, so they're safe as required.

**Alternatives considered**:
- *Make all five required* — the skipped-job-blocks-merge footgun. Rejected.
- *Make none required (advisory CI)* — defeats the purpose; a red CI must block merge. Rejected.

---

## §7 — Concurrency policy

**Decision**: `concurrency: { group: "${{ github.workflow }}-${{ github.ref }}", cancel-in-progress: true }`.

**Rationale**: A force-push to a PR should cancel the in-flight run and start fresh — saves runner minutes and avoids two builds racing to comment on the same PR. Grouping by workflow+ref scopes the cancellation to the one PR.

**Alternatives considered**: No concurrency control (two runs race, double PR comments) — rejected.

---

## §8 — Smoke on host Docker (no DinD)

**Decision**: The `smoke` job runs `bash scripts/smoke-docker-stack.sh` directly on the GH runner. The runner's preinstalled Docker + Compose v2 run the dev stack; no Docker-in-Docker.

**Rationale**: GH `ubuntu-latest` runners ship Docker; the smoke script already calls `docker compose` on the host (T09 contract). DinD would add complexity for zero benefit.

**Alternatives considered**: DinD container — rejected (unnecessary).

---

## §9 — pre-commit in CI

**Decision**: The `lint` job does `pip install pre-commit` + `actions/cache` on `~/.cache/pre-commit`, then `pre-commit run --all-files`. The **frontend-scoped hooks** (`eslint`, `tokens-drift`, `visual-discipline`) are `SKIP`-listed in this job (via the pre-commit `SKIP` env var) because the dedicated `frontend` job already runs eslint + tsc + `tokens:check`; running them again in `lint` would need node+pnpm in the lint runner and duplicate work.

**Rationale**:
- The lint job's value is the project-wide hooks: `gitleaks`, `detect-secrets`, `actionlint`, `terraform_validate`, `ruff`, `ruff-format`, the pygrep guards (`no-print-statements`, `forbid-env-values`, the frontend bracket/hex/dark/shadow/animation guards on changed files), and the project's three custom hooks (`no-provider-sdk-imports`, `feature-flag-registered`, `rubric-schema`).
- `SKIP=eslint,tokens-drift,visual-discipline` keeps the lint runner Python-only (fast, no node install) and avoids double-running the frontend gates.
- Documented in `ci.md` so the SKIP list is auditable.

**Alternatives considered**:
- *Install node+pnpm in the lint job and run everything* — slower + duplicates the `frontend` job. Rejected.
- *Official `pre-commit/action@v3`* — viable, but a plain `pip install` + cache gives more control over the SKIP env. Either works; pip chosen for transparency.

---

## §10 — shellcheck for the new bash scripts

**Decision**: Add a `shellcheck` hook to `.pre-commit-config.yaml` scoped to `scripts/*.sh` (using the `shellcheck-py` mirror or the koalaman pre-commit hook). This covers the three new CI helpers AND retroactively covers T09's `smoke-docker-stack.sh`.

**Rationale**:
- The new helpers are bash; shellcheck catches the classic footguns (unquoted expansions, `set -e` interactions) before they reach CI.
- It's cheap (a fast, well-maintained hook) and keeps every future `scripts/*.sh` honest.

**Alternatives considered**:
- *Run shellcheck manually only* — relies on memory; rejected. The pre-commit hook makes it automatic.
- *Skip shellcheck* — rejected: the whole point of T10 is to raise the floor; shipping unchecked bash undercuts that.

---

## Summary of resolved decisions

| # | Decision |
| - | -------- |
| 1 | Reviewer-agent = placeholder, DEFERRED (no API key / cost controls yet — §12 honesty). |
| 2 | Buildx `type=gha` image cache + `actions/cache` pnpm store. |
| 3 | `alembic upgrade head --sql` offline render from a fresh test-stack container. |
| 4 | DDL regexes: `DROP COLUMN` / `DROP TABLE` / `ALTER COLUMN … TYPE`; matching inside `op.execute` strings is correct; exit 0 always, label is the signal. |
| 5 | `<!-- ci:migration-sql-render -->` HTML marker; github-script find-and-update. |
| 6 | Required checks: backend / frontend / smoke / lint; migration-sql-render informational. |
| 7 | Concurrency group by workflow+ref, cancel-in-progress. |
| 8 | Smoke on host Docker; no DinD. |
| 9 | pre-commit via pip + cache; SKIP frontend-scoped hooks (the frontend job owns them). |
| 10 | Add shellcheck pre-commit hook for `scripts/*.sh`. |
