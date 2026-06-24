# Feature Specification: CI pipeline + migration approval gate (T10)

**Feature Branch**: `012-t10-ci-pipeline`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: T10 — CI pipeline (lint + test on PR) + migration approval gate, per `docs/engineering/implementation-plan.md` Tier 1 / W1–W2

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are every human and AI sub-agent who opens a PR against `main`: the `backend-engineer` shipping a Tier 2+ feature, the `infra-engineer` editing compose files, the `prompt-engineer` editing a YAML rubric, the `reviewer` sub-agent gating the merge, the project owner watching the merge queue. T10 delivers the routine safety net every later PR depends on — a single GitHub Actions workflow that fails the PR if the project no longer builds, lints, type-checks, or passes its tests, and a label-based migration-approval gate that surfaces destructive DDL for human review before `/deploy` (T06a) ever runs.

### User Story 1 — Every PR earns its merge through an automated checkpoint (Priority: P1)

A contributor opens a PR. Within five minutes of the push, GitHub Actions reports the verdict of four required jobs (backend tests + lint + typecheck + format + OpenAPI parity; frontend lint + typecheck + tests; end-to-end Docker smoke; project-wide pre-commit chain). If any required check fails, branch protection blocks merge. The contributor sees a clear, actionable failure in the PR UI.

**Why this priority**: P1 because this is the regression net that every later Tier 2+ task assumes. Without T10, a PR that breaks the 138-test backend suite (T08 baseline) or a `mypy --strict` invariant or the OpenAPI byte-identical contract can merge silently. The constitution's invariants (§3 append-only, §11 hybrid language, §16 configs as code) are already encoded in tests and pre-commit hooks; T10 makes those gates *mandatory at merge time*.

**Independent Test**: A trivial PR (one-line README typo fix) opens; the four required jobs all pass within the documented budget; the merge button turns green. A second PR that deliberately breaks one invariant (e.g. adds a `print()` call in `app/backend/`) fails the lint job; the merge button stays red; the PR author sees the failing check's stderr in the GitHub UI.

**Acceptance Scenarios**:

1. **Given** a trivial PR with no migration changes, **When** the contributor pushes, **Then** the workflow runs four required jobs (backend / frontend / smoke / lint), all four pass on warm cache in under 5 minutes, and branch protection allows merge.
2. **Given** a PR that introduces a `print()` in `app/backend/`, **When** CI runs, **Then** the lint job fails with the offending file + line; merge is blocked.
3. **Given** a PR that breaks an existing test (e.g. an §3 append-only invariant), **When** CI runs, **Then** the backend job fails with the failing test name; merge is blocked.
4. **Given** a PR that adds `is_enabled("undeclared_flag")` without the YAML entry, **When** CI runs, **Then** the lint job's `feature-flag-registered` hook fails; merge is blocked (T05a contract honoured).
5. **Given** a PR that introduces a YAML in `configs/rubric/` violating the schema, **When** CI runs, **Then** the lint job's `rubric-schema` hook fails; merge is blocked (T08 contract honoured).
6. **Given** a PR whose author force-pushes during a CI run, **When** the new push arrives, **Then** the prior in-flight CI run is cancelled and the new run starts (concurrency policy honoured).

---

### User Story 2 — A migration PR surfaces its SQL for human review before merge (Priority: P1)

The contributor introduces a new file under `alembic/versions/`. Within minutes the CI workflow renders the migration's SQL (offline mode, no live DB needed) and posts it as a collapsed `<details>` block in a PR comment. A human reviewer expands the comment, scans the DDL, and — if satisfied — applies the `migration-approved` label. The label is the explicit go/no-go signal for the `/deploy` slash command (T06a, future): `/deploy` refuses to proceed on a PR that touched `alembic/versions/` without the label.

**Why this priority**: P1 because constitution §10 makes migration approval non-negotiable. Production data lives in the schema; a silent destructive migration is a recoverable disaster only if discovered before deploy. Surfacing the SQL in the PR puts the reviewer's eyes on the exact change that will run in prod, in the same view where they're already reviewing the code that produced it.

**Independent Test**: A fixture PR that adds a no-op migration (e.g. adds a single nullable column to a non-audit table) under `alembic/versions/`. The CI workflow detects the touched path, runs the migration-SQL render job, and posts a PR comment with the rendered DDL inside a `<details>` block. A force-push updates the same comment (not duplicated). Without the `migration-approved` label, the documented `/deploy` contract (T06a) refuses to proceed — the spec ships the contract; T06a enforces.

**Acceptance Scenarios**:

1. **Given** a PR that touches `alembic/versions/*.py`, **When** CI runs, **Then** a dedicated job (`migration-sql-render`) executes; within 90 seconds it posts a PR comment containing the rendered SQL inside a `<details>` block.
2. **Given** the same PR after a force-push, **When** CI runs again, **Then** the prior PR comment is updated in place (find-by-marker pattern) — not duplicated.
3. **Given** a PR that does NOT touch `alembic/versions/`, **When** CI runs, **Then** the migration-SQL-render job is skipped (its status appears as "skipped" or is conditional-on-path); the four required jobs still run.
4. **Given** the `migration-approved` label is documented as "human-applied", **When** a PR with a migration is open, **Then** CI never auto-applies the label — only a maintainer can.

---

### User Story 3 — Destructive DDL is automatically flagged for ADR review (Priority: P1)

Constitution §10 forbids destructive DDL (`DROP COLUMN`, `DROP TABLE`, type-narrowing `ALTER`) without a linked ADR. T10's CI detects these patterns in changed migration files and auto-applies the `needs-adr` label to the PR. The reviewer agent (or a human reviewer) blocks merge until an ADR is linked.

**Why this priority**: Co-equal P1. The whole reason §10 exists is that destructive DDL is the highest-stakes operation a PR can land. An auto-label keeps the human-review path honest: a contributor cannot quietly slip a `DROP COLUMN` past the reviewer because the label appears on the PR before the reviewer scrolls.

**Independent Test**: A fixture PR introducing a migration with `DROP COLUMN feature_flag.owner` (just an example — would not be merged). CI's destructive-DDL detection step matches the pattern; the workflow auto-adds the `needs-adr` label via `actions/github-script`. The PR's UI now shows `needs-adr` in the labels area. Without a linked ADR in the PR description (a documented convention), the reviewer agent blocks merge.

**Acceptance Scenarios**:

1. **Given** a PR with a migration containing `DROP COLUMN`, **When** CI runs, **Then** the `needs-adr` label appears on the PR within 60 seconds.
2. **Given** a PR with a migration containing `DROP TABLE` or a type-narrowing `ALTER COLUMN ... TYPE …` pattern, **When** CI runs, **Then** the `needs-adr` label appears with a workflow annotation naming the offending pattern.
3. **Given** an existing PR that adds an additive `ADD COLUMN` migration, **When** CI runs, **Then** the `needs-adr` label is NOT applied (additive DDL is fine).
4. **Given** a PR with `needs-adr` applied, **When** the contributor adds a link to an ADR in the PR description (matching `adr/<NNN>-.*\.md`), **Then** the reviewer agent's documented contract is satisfied — block lifts (mechanics are documented; full enforcement may be a follow-up integration).

---

### User Story 4 — The CI contract is documented in one place; reviewer-agent integration is honestly deferred (Priority: P2)

A new contributor needs to understand what CI does, how to debug a failing check, and what `migration-approved` / `needs-adr` mean as labels. A reviewer agent invocation is *part of the eventual flow* but the practical wiring (Anthropic API key in CI secrets, Claude Code in the runner, cost controls) is operationally not yet in place — T10 ships a clear documented placeholder and a follow-up task for the real integration.

**Why this priority**: P2 because it serves long-tail value (every later contributor benefits a little). But the cost of NOT writing the doc now is everyone re-deriving the workflow from the YAML; and the cost of NOT flagging the reviewer-agent deferral is contributors expecting an automated review that never arrives.

**Independent Test**: A first-time contributor opens `docs/engineering/ci.md`, reads the page, and can answer in writing: (a) which checks block merge; (b) how to fix a failing migration-SQL-render job; (c) what `migration-approved` and `needs-adr` labels mean; (d) why the reviewer agent is "placeholder today" and where the real integration is tracked. The placeholder step in the workflow prints "Reviewer agent invocation DEFERRED" with a link to the follow-up.

**Acceptance Scenarios**:

1. **Given** the post-T10 tree, **When** a contributor opens `docs/engineering/ci.md`, **Then** they find a clear section per CI job, per label, plus a troubleshooting cheatsheet.
2. **Given** the CI run, **When** the reviewer-agent placeholder step executes, **Then** it prints "Reviewer agent invocation DEFERRED — see docs/engineering/ci.md §Reviewer agent" and exits 0; merge is not blocked by it.
3. **Given** the README, **When** the contributor reaches the project-overview Docker section, **Then** the CI subsection points at `docs/engineering/ci.md` for the deep dive.

---

### Edge Cases

- **A PR that touches a workflow file (`.github/workflows/*.yml`)**: `actionlint` (already in the pre-commit chain) catches syntax issues at the lint job. CI re-runs against the new workflow definition on the next push.
- **A PR with both a migration and destructive DDL**: both gates fire — the SQL is rendered + posted (US2) AND the `needs-adr` label is applied (US3). The two are independent.
- **A PR that reverts a migration**: the migration-SQL-render job runs and posts the (potentially empty) diff. The reviewer evaluates whether the revert is itself destructive.
- **A force-push that arrives during a CI run**: the concurrency policy cancels the in-flight run for the same PR head ref; the new push starts a fresh run.
- **CI runner has a cold cache (first run, or cache evicted)**: the build can take 5–12 minutes wall-clock. Documented; not a failure mode.
- **The PR-comment GitHub token lacks comment permissions**: the migration-SQL-render job fails loudly with a workflow annotation; the maintainer fixes repo settings (GitHub Actions read+write permission).
- **A test that legitimately depends on Docker Compose v2 syntax not present on the runner**: GitHub-hosted Ubuntu runners ship Docker Compose v2 by default; if a self-hosted runner is ever introduced, this becomes a documented prerequisite in `docs/engineering/ci.md`.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST run a single GitHub Actions workflow on every `pull_request` against `main` and on every `push` to `main`.
- **FR-002**: System MUST cancel an in-flight CI run for the same PR head ref when a new push arrives (concurrency policy with `cancel-in-progress: true`).
- **FR-003**: System MUST run a `backend` job that, inside the test-stack container, applies the Alembic baseline, runs the full backend test suite, runs `ruff check` + `ruff format --check`, runs `mypy --strict`, and runs the OpenAPI byte-identical regen check. All five steps must pass for the job to pass.
- **FR-004**: System MUST run a `frontend` job that, inside the frontend test-stack container, installs deps with `pnpm install --frozen-lockfile`, runs `pnpm exec eslint . --max-warnings=0`, runs `pnpm exec tsc --noEmit`, runs `pnpm test`, and runs `pnpm tokens:check`. All five steps must pass for the job to pass.
- **FR-005**: System MUST run a `smoke` job that invokes `bash scripts/smoke-docker-stack.sh` on the host runner. The script's existing exit-code contract (0 success / 1 failure) determines the job's status.
- **FR-006**: System MUST run a `lint` job that executes the project's pre-commit chain (`pre-commit run --all-files`). Every existing hook from T05/T05a/T08 (and all base hooks) must pass for the job to pass.
- **FR-007**: When (and only when) a PR touches `alembic/versions/*.py`, the system MUST run a dedicated job that brings up a fresh Postgres, renders the migration's SQL via the existing offline path (`alembic upgrade head --sql`), and posts the SQL as a PR comment inside a collapsed `<details>` block. On a re-run for the same PR, the system MUST update the existing comment (find-by-marker) rather than append a new one.
- **FR-008**: When a PR's migration files contain destructive DDL patterns (`DROP COLUMN`, `DROP TABLE`, or type-narrowing `ALTER COLUMN ... TYPE …`), the system MUST automatically apply the `needs-adr` label to the PR via the workflow's GitHub token.
- **FR-009**: The system MUST NOT auto-apply the `migration-approved` label. That label is a human-applied gate; the workflow only renders the SQL.
- **FR-010**: The system MUST ship a placeholder reviewer-agent step that prints a deferral message and exits 0. The real integration is owned by a follow-up task and is OUT OF SCOPE for T10.
- **FR-011**: The four primary jobs (`backend`, `frontend`, `smoke`, `lint`) MUST be configurable as required-status-checks on the `main` branch protection rule. T10 documents which checks must be required; the operator applies the rule on the repo.
- **FR-012**: The workflow MUST NOT contain any inline credential. Secrets management is limited to the existing WIF binding (T05a placeholders) and the GitHub-provided `GITHUB_TOKEN` for PR comments + labels.
- **FR-013**: System MUST ship `docs/engineering/ci.md` as the canonical CI reference: which jobs run, what each enforces, the migration-approval workflow end-to-end, the destructive-DDL pattern set, the meaning of `migration-approved` and `needs-adr`, the branch-protection contract, troubleshooting.
- **FR-014**: System MUST update `README.md` with a short CI subsection pointing at `docs/engineering/ci.md`.
- **FR-015**: The workflow's runtime on warm cache MUST complete in under 5 minutes wall-clock (the four required jobs in parallel). Cold cache MUST complete in under 12 minutes. The migration-SQL-render job (when triggered) MUST complete in under 90 seconds.

### Key Entities

- **CI workflow** (`.github/workflows/ci.yml`): one YAML file declaring the five jobs + the concurrency policy + the conditional on-paths trigger for the migration job.
- **Jobs**: `backend` (tests + lint + typecheck + OpenAPI), `frontend` (lint + typecheck + tests + tokens), `smoke` (Docker smoke), `lint` (pre-commit chain), `migration-sql-render` (conditional).
- **Required status checks**: the operator-configured set of branch-protection rules naming the four required jobs (the conditional fifth is informational, not required).
- **PR labels**:
  - `migration-approved` — human-applied gate signalling deploy go/no-go.
  - `needs-adr` — auto-applied by the destructive-DDL detection step; cleared by a maintainer once an ADR is linked.
- **PR comment** (the rendered migration SQL): one comment per PR with a stable HTML marker, updated in place on re-runs.
- **CI reference doc** (`docs/engineering/ci.md`): sibling to T09's `docker.md`; the canonical "what does CI do, and how do I debug it" reference.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A trivial PR (no migration) completes the four required CI jobs in **under 5 minutes** on warm cache (median across 5 runs).
- **SC-002**: A migration PR completes the migration-SQL-render job and posts the PR comment in **under 90 seconds** after the workflow starts (measured from "Job started" to the GitHub comment timestamp).
- **SC-003**: A PR force-push updates the existing migration-SQL PR comment **in place** (zero duplicate comments after N force-pushes) — verifiable by comment-count assertion in a fixture-PR test.
- **SC-004**: A PR that introduces a known invariant break (a deliberately-failing test, a `print()` call, an undeclared `is_enabled("…")`, a malformed YAML) is **blocked from merge** by the corresponding required job — verifiable on 4 fixture PRs.
- **SC-005**: A PR containing a `DROP COLUMN` migration receives the `needs-adr` label **automatically** within 60 seconds of the workflow starting — verifiable on a fixture PR.
- **SC-006**: A new contributor can read `docs/engineering/ci.md` only and answer **all four** of the following in writing: (a) which checks block merge; (b) how to fix a migration-SQL-render failure; (c) what `migration-approved` and `needs-adr` mean; (d) why the reviewer-agent step is a placeholder + where the follow-up integration is tracked.
- **SC-007**: After T10 merges, the existing post-T09 138-test backend suite still passes byte-identically inside the test stack (regression baseline).
- **SC-008**: The post-T10 tree carries **zero** new credentials in source control — verified by `gitleaks` and `detect-secrets` on the PR diff.
- **SC-009**: The CI workflow file itself passes `actionlint` (run as part of the `lint` job on the same PR that introduces it — self-verifying).
- **SC-010**: Branch protection on `main` is configured to require the four primary checks (`backend`, `frontend`, `smoke`, `lint`) before merge — verifiable by reading the repo settings. T10 documents the contract; the operator applies it.

## Assumptions

- GitHub Actions runners (Ubuntu-latest) carry Docker + Docker Compose v2 by default. Self-hosted runners are not in scope.
- The `GITHUB_TOKEN` provided to the workflow has the permissions needed to create + update PR comments and to apply labels (`pull-requests: write`, `issues: write`).
- The `migration-approved` label is human-applied; who is authorised to apply it is enforced via GitHub roles, not via CI logic. T10 documents the convention; the operator applies the GitHub role configuration.
- A new contributor can read GitHub Actions UI output well enough to understand a failure once the failing step is named clearly. The CI does not need to forward failures to Slack or email at T10 — that is operational tooling for later tiers.
- The Anthropic API key for the real reviewer-agent integration is intentionally NOT added to repo secrets in T10. The placeholder step ships; the real integration is a separate follow-up with explicit cost controls.
- The test-stack image already includes everything CI needs (T05's Dockerfile + T05a's `ripgrep` + T05's `COPY docs/contracts ./docs/contracts` + `COPY scripts ./scripts`).
- The `smoke` job runs on the GitHub runner's host Docker (NOT inside a container). This is consistent with `scripts/smoke-docker-stack.sh` which calls `docker compose --profile db --profile web up` on the host.
- CI does NOT need to run Playwright e2e tests at T10. The e2e service exists in `docker-compose.test.yml` but exercising it from CI is a separate task (T11 / T48a).
- The migration-SQL-render job uses the same `alembic upgrade head --sql` offline path that already works locally (verified by T05's research §1). No new alembic config is needed.
- A `migration-approved` label policy (who can apply, how it's removed on force-push) is encoded as a project convention in `docs/engineering/ci.md`. GitHub does not enforce label-permissions natively at the free tier; the convention relies on maintainer discipline + the reviewer agent's eventual enforcement.

## Out of scope

- The `/deploy` slash command (T06a). T10 ships the migration-approval label contract; T06a enforces it at deploy time.
- The real Claude-in-CI reviewer-agent invocation. T10 ships a placeholder step + docs; the actual Anthropic API key + cost controls + workflow integration lands as a follow-up task.
- Cloud Run preview deployments per PR (T06a / T11).
- Frontend Playwright e2e tests in CI (T11 / T48a).
- Changes to existing pre-commit hooks (they continue to run on the host + in CI via the `lint` job).
- Changes to existing test code; T08's 138-pass baseline is the regression target.
- Notification routing (Slack, email) — operational tooling for later tiers.
- Self-hosted runner configuration — out of scope.
- A separate CI workflow for nightly / scheduled runs — out of scope. T10 ships `on: pull_request` + `on: push to main` only.

## Plan-phase research items (handle in `plan.md` / `research.md`)

- Reviewer-agent invocation mechanism — placeholder + DEFERRED (clear rationale + follow-up task pointer).
- Cache strategy — Buildx GHA cache for image layers + `actions/cache` for pnpm store; rationale grounded in cold-vs-warm timings.
- Migration SQL rendering offline path — `alembic upgrade head --sql` from a fresh container.
- Destructive-DDL regex set — exact patterns, including line-anchored to avoid false positives in comments / docstrings.
- PR-comment marker strategy — HTML comment delimiter like `<!-- migration-sql-render -->` so the script can find & update its prior comment.
- Branch-protection contract — which checks must be required; documented in `docs/engineering/ci.md` for the operator.
- Concurrency policy — group by `${{ github.workflow }}-${{ github.ref }}` with `cancel-in-progress: true`.
- Whether the smoke job needs Docker-in-Docker — no; runs on the host's docker compose.
- pnpm install caching — separate from Docker layer cache.
- The `migration-approved` label policy — documented convention; GitHub roles enforce.
