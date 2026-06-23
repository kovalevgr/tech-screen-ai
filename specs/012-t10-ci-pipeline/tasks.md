---
description: "Task list for T10 — CI pipeline + migration approval gate"
---

# Tasks: CI pipeline + migration approval gate (T10)

**Input**: Design documents from `specs/012-t10-ci-pipeline/`
**Prerequisites**: spec.md, plan.md, research.md, data-model.md, contracts/plan-contract.md, quickstart.md

**Tests**: T10 ships YAML + bash + docs (no new Python). "Tests" = `actionlint` on the workflow, `shellcheck` on the bash helpers, local dry-runs of the two functional helpers, the 138-test regression re-run, `pre-commit` clean. The GitHub-only behaviours (PR comment, labels, concurrency-cancel) are validated by a documented manual first-PR checklist (quickstart Part B), NOT by local execution — called out honestly.

**Agent / parallelism**: every task is `agent: infra-engineer`, executed sequentially in one PR. `[P]` marks tasks that touch *different files*; NOT sub-agent fan-out (§18 — `parallel: false`).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

No setup needed. T10 adds no new dependency to `pyproject.toml` / `uv.lock` / `package.json`. Tooling (Docker, pre-commit, actionlint, shellcheck-via-pre-commit) is provided by the runner / the existing chain.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The three helper scripts + the shellcheck hook must exist before `ci.yml` can reference the scripts and before pre-commit can pass.

**⚠️ CRITICAL**: `ci.yml` (US1/US2/US3) references these scripts; they must land first.

- [x] T001 [P] Create `scripts/ci-render-migration-sql.sh` (executable, `set -euo pipefail`). Renders the full migration DDL via the test-stack backend container: `docker compose -f docker-compose.test.yml run --rm backend alembic upgrade head --sql` (offline mode; T05 research §1). Writes the SQL to stdout. Clear stderr + non-zero exit on failure. (spec FR-007)
- [x] T002 [P] Create `scripts/ci-detect-destructive-ddl.sh` (executable, `set -euo pipefail`). Accepts changed migration file paths as args (or derives them via `git diff --name-only "${BASE_REF:-origin/main}"...HEAD -- 'alembic/versions/*.py'`). Greps for `DROP[[:space:]]+COLUMN`, `DROP[[:space:]]+TABLE`, `ALTER[[:space:]]+COLUMN[[:space:]]+[A-Za-z_]+[[:space:]]+TYPE` (case-insensitive). Writes `needs_adr=true|false` to `$GITHUB_OUTPUT` (and echoes the matched pattern + file to stdout). Exits 0 always — the label is the signal, not the exit code. (spec FR-008; research §4)
- [x] T003 [P] Create `scripts/ci-reviewer.sh` (executable, `set -euo pipefail`). Prints `Reviewer agent invocation DEFERRED — see docs/engineering/ci.md §Reviewer agent` to stdout and exits 0. (spec FR-010; research §1)
- [x] T004 Edit `.pre-commit-config.yaml`: add a `shellcheck` hook scoped to `^scripts/.*\.sh$` (use the `koalaman/shellcheck-precommit` mirror or `shellcheck-py`). This covers the three new helpers + T09's `smoke-docker-stack.sh`. (research §10)

**Checkpoint**: the helpers exist + shellcheck guards them; `ci.yml` can now reference them.

---

## Phase 3: User Story 1 — Routine pre-merge checkpoint (Priority: P1) 🎯 MVP

**Goal**: Four required jobs (`backend`, `frontend`, `smoke`, `lint`) run on every PR + push to main; any failure blocks merge.

**Independent Test**: `actionlint .github/workflows/ci.yml` exits 0; each of the four jobs is present with the documented steps; the concurrency block cancels in-progress runs.

### Implementation for User Story 1

- [x] T005 [US1] Create `.github/workflows/ci.yml` with the workflow header (`on: pull_request [main] + push [main]`; `concurrency: { group: "${{ github.workflow }}-${{ github.ref }}", cancel-in-progress: true }`; minimal top-level `permissions: { contents: read }`) and the `backend` job: checkout; `docker/setup-buildx-action@v3` with `type=gha` cache; build the test backend image; `docker compose -f docker-compose.test.yml --profile db up -d postgres`; `alembic upgrade head`; `pytest app/backend/tests`; `ruff check app/backend`; `ruff format --check app/backend alembic scripts`; `mypy --strict app/backend`; `python -m app.backend.generate_openapi --check`. (spec FR-001/002/003; research §2/§7)
- [x] T006 [US1] Add the `frontend` job to `.github/workflows/ci.yml`: checkout; buildx + `actions/cache` for the pnpm store; build the frontend image; `pnpm install --frozen-lockfile`; `pnpm exec eslint . --max-warnings=0`; `pnpm exec tsc --noEmit`; `pnpm test`; `pnpm tokens:check`. (spec FR-004; research §2)
- [x] T007 [US1] Add the `smoke` job to `.github/workflows/ci.yml`: checkout; `bash scripts/smoke-docker-stack.sh` on the host runner (no DinD). (spec FR-005; research §8)
- [x] T008 [US1] Add the `lint` job to `.github/workflows/ci.yml`: checkout; `pip install pre-commit`; `actions/cache` for `~/.cache/pre-commit`; `SKIP=eslint,tokens-drift,visual-discipline pre-commit run --all-files` (the `frontend` job owns those three; research §9). (spec FR-006)

**Checkpoint**: the four required jobs exist; `actionlint` is clean; a green PR can merge, a broken one cannot.

---

## Phase 4: User Story 2 — Migration SQL surfaced for review (Priority: P1)

**Goal**: A PR touching `alembic/versions/**` renders its SQL into a collapsed, in-place-updated PR comment.

**Independent Test**: The `migration-sql-render` job is conditional on the path filter; it calls `ci-render-migration-sql.sh` and posts via `actions/github-script` using the `<!-- ci:migration-sql-render -->` marker.

### Implementation for User Story 2

- [x] T009 [US2] Add the conditional `migration-sql-render` job to `.github/workflows/ci.yml`: gated by a `dorny/paths-filter` (or `git diff`) step detecting `alembic/versions/**`; `permissions: { pull-requests: write, contents: read }`; brings up postgres; runs `scripts/ci-render-migration-sql.sh` capturing stdout; an `actions/github-script@v7` step finds the prior comment by the `<!-- ci:migration-sql-render -->` marker and updates-or-creates it, wrapping the SQL in a `<details><summary>Rendered migration SQL</summary>…</details>` block. (spec FR-007/FR-009; research §3/§5)

**Checkpoint**: migration PRs surface their SQL; non-migration PRs skip the job.

---

## Phase 5: User Story 3 — Destructive DDL auto-flagged (Priority: P1)

**Goal**: A migration with destructive DDL auto-applies the `needs-adr` label.

**Independent Test**: The label step runs `ci-detect-destructive-ddl.sh`; on `needs_adr=true` it applies the `needs-adr` label via github-script.

### Implementation for User Story 3

- [x] T010 [US3] Extend the `migration-sql-render` job in `.github/workflows/ci.yml` with a destructive-DDL step: run `scripts/ci-detect-destructive-ddl.sh` (reads `$GITHUB_OUTPUT` `needs_adr`); an `actions/github-script@v7` step applies the `needs-adr` label when `needs_adr == 'true'` and emits a workflow `::warning::` naming the offending pattern. Never auto-applies `migration-approved` (FR-009). (spec FR-008; research §4)

**Checkpoint**: a `DROP COLUMN` PR is auto-labelled `needs-adr`; an additive PR is not.

---

## Phase 6: User Story 4 — Single docs source + honest reviewer deferral (Priority: P2)

**Goal**: One canonical CI doc; README points at it; the reviewer-agent step is a visible, documented placeholder.

**Independent Test**: `docs/engineering/ci.md` answers the four contributor questions; the workflow has a reviewer placeholder step calling `ci-reviewer.sh`; README links the doc.

### Implementation for User Story 4

- [x] T011 [US4] Create `docs/engineering/ci.md` (7 sections per plan §Phase 1 / data-model.md): (0) Why; (1) The five jobs + what each enforces; (2) Required-status-checks branch-protection contract (backend/frontend/smoke/lint required; migration-render informational) — operator-applied; (3) Migration-approval gate end-to-end (PR → SQL rendered + posted → reviewer applies `migration-approved` → T06a `/deploy` enforces); (4) Destructive-DDL detection + `needs-adr` + ADR requirement (the §10 pattern set); (5) Reviewer agent — DEFERRED placeholder today, follow-up task tracked, rationale (no API key + no cost controls yet); (6) Troubleshooting (failing migration render, cold-cache timing, GITHUB_TOKEN permissions); (7) Caching strategy. (spec FR-013)
- [x] T012 [US4] Add a reviewer placeholder step to a job in `.github/workflows/ci.yml` (e.g. an informational `reviewer` step in the `lint` job or its own non-required job) that runs `bash scripts/ci-reviewer.sh` (prints DEFERRED, exits 0, never blocks). Then edit `README.md`: add a short "CI pipeline" subsection (≤ 3 sentences) linking `docs/engineering/ci.md`. (spec FR-010/FR-014)

**Checkpoint**: the CI contract is documented in one place; the reviewer deferral is visible + honest.

---

## Phase 7: Polish & Verification

- [x] T013 Run the verification matrix (quickstart Part A): `actionlint` on `ci.yml` (SC-009); `shellcheck` on `scripts/ci-*.sh` + `scripts/smoke-docker-stack.sh`; dry-run `ci-render-migration-sql.sh` (produces SQL) + `ci-detect-destructive-ddl.sh` (flags a DROP-COLUMN fixture, passes an ADD-COLUMN fixture); `ci-reviewer.sh` prints DEFERRED + exit 0; re-run the full 138-test backend suite in the test stack (SC-007); `pre-commit run --all-files` clean with the new shellcheck hook (SC-006/SC-008); read `ci.md` and confirm the four contributor questions are answered. Document that quickstart Part B (the GitHub-only first-PR checklist) is the operator's one-time manual step after branch protection is configured (SC-001..005, SC-010).

---

## Dependencies & Execution Order

### Phase dependencies
- **Setup (P1)** → empty.
- **Foundational (P2)** → T001/T002/T003 are `[P]` (separate script files); T004 (shellcheck hook) lands with/after them so pre-commit passes. All four block US1's `ci.yml`.
- **US1 (P3)** → T005 creates `ci.yml` + the backend job; T006/T007/T008 add jobs to the SAME file (sequential, not `[P]`).
- **US2 (P4)** → T009 adds the migration-render job to `ci.yml` (sequential after US1's edits).
- **US3 (P5)** → T010 extends the SAME migration-render job (sequential after T009).
- **US4 (P6)** → T011 (ci.md) then T012 (workflow placeholder step + README link — README depends on ci.md existing).
- **Polish (P7)** → T013 after everything.

### Parallel opportunities (file-level, single committer)
- T001 ∥ T002 ∥ T003 (three separate script files).
- Never parallel: any two edits to `.github/workflows/ci.yml` (T005→T006→T007→T008→T009→T010→T012); `.pre-commit-config.yaml` (T004); `README.md` (T012); `docs/engineering/ci.md` (T011).

---

## Implementation Strategy

### MVP first (US1)
1. Foundational (helpers + shellcheck) → US1 (the four required jobs).
2. **STOP and VALIDATE**: `actionlint` clean; the four jobs are well-formed; locally the steps each pass.

### Incremental delivery
1. Foundational → helpers exist.
2. US1 → the routine checkpoint (MVP — blocks broken PRs).
3. US2 → migration SQL surfaced.
4. US3 → destructive DDL auto-labelled.
5. US4 → docs + reviewer deferral.
6. Polish → verification matrix + the documented operator checklist.

### Suggested commit grouping (manual commits, our norm)
- `feat(T10): CI helper scripts (migration SQL render + destructive-DDL detect + reviewer placeholder) + shellcheck hook` (T001–T004)
- `feat(T10): ci.yml — backend / frontend / smoke / lint jobs` (T005–T008)
- `feat(T10): ci.yml — migration-SQL-render + destructive-DDL auto-label` (T009–T010)
- `docs(T10): docs/engineering/ci.md + README CI subsection + reviewer placeholder step` (T011–T012)

---

## Notes
- `[P]` = different files, no ordering hazard; NOT sub-agent fan-out (§18).
- T10 ships no new Python; the 138-test suite is the regression baseline.
- The reviewer-agent step is a placeholder (ci-reviewer.sh) — real Claude-in-CI is a follow-up task with API key + cost controls.
- The GitHub-only behaviours (PR comment, labels, concurrency) are validated by the operator's one-time manual first-PR checklist (quickstart Part B), not by local execution — honest boundary.
