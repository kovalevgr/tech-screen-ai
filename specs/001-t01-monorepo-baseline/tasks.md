---
description: "Task list for T01 — Monorepo Layout & Tooling Baseline"
---

# Tasks: Monorepo Layout & Tooling Baseline (T01)

**Input**: Design documents from [`specs/001-t01-monorepo-baseline/`](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/dev-commands.md](./contracts/dev-commands.md), [quickstart.md](./quickstart.md)

**Tests**: Not generated. The spec explicitly states "no tests are authored in T01" (plan.md Technical Context). The three documented check commands (FR-002/003/004) ARE the acceptance tests. Unit tests begin in T02/T03.

**Agent ownership**: All tasks below are owned by `agent: orchestrator` (main Claude) with `parallel: false` at the sub-agent level, per `docs/engineering/implementation-plan.md` T01. The `[P]` marker inside this file means "different files, no intra-phase ordering constraint" — the orchestrator may open these files in any order within a phase, not that they go to different sub-agents.

**Organization**: Tasks are grouped by user story. The implementation order follows dependency (folder tree → per-toolchain config → docs/verification → layout audit → polish), which happens to align with picking US4 folder work into the Foundational phase so US1/US2/US3 can each land a complete toolchain slice.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can edit/create in any order inside the same phase (different files, no in-phase dependency).
- **[Story]**: Which user story this task serves (`US1`, `US2`, `US3`, `US4`). Setup, Foundational, and Polish tasks carry no story label.
- All paths are **relative to the repo root** (`/Users/kovalevgr/project_new/TechScreen/.claude/worktrees/eloquent-elion-f0bc91/`).

## Path Conventions

- Backend Python tooling: repo root (`pyproject.toml`, `uv.lock`).
- Frontend tooling: `app/frontend/` (`package.json`, `pnpm-lock.yaml`, `tsconfig.json`, `.eslintrc.cjs`, `.prettierrc.json`, `.gitignore`).
- Documentation: repo root `README.md`, `docs/engineering/directory-map.md`.
- Empty canonical folders receive a `.gitkeep` marker.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Verify the workspace is ready to receive T01 changes. No files created yet.

- [X] T001 Verify the current branch is `001-t01-monorepo-baseline` with a clean working tree and `.specify/feature.json` points at `specs/001-t01-monorepo-baseline` (run `git rev-parse --abbrev-ref HEAD`, `git status --short`, `cat .specify/feature.json`). If any check fails, stop and investigate before continuing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the canonical folder tree and the central directory map. Every later phase writes into folders created here.

**⚠️ CRITICAL**: Phases 3–6 cannot begin until this phase is complete — the per-story tasks assume the canonical folders already exist.

- [X] T002 Create the missing canonical directories and mark them with `.gitkeep` so git tracks the empty folders. Paths to create: `app/backend/.gitkeep`, `app/frontend/.gitkeep`, `alembic/.gitkeep`, `configs/.gitkeep`, `evals/.gitkeep`, `infra/terraform/.gitkeep`, `.github/workflows/.gitkeep`. Each `.gitkeep` file is zero-byte. Confirm with `find app/backend app/frontend alembic configs evals infra/terraform .github/workflows -name .gitkeep`.
- [X] T003 [P] Create the central folder index at `docs/engineering/directory-map.md` with one row per canonical folder — columns: **Path**, **Owner task (T-id)**, **Purpose**, **Populated by**. Include every folder listed in `CLAUDE.md` "Where to find things" (both new and pre-existing). Reference this doc as the source of truth for folder ownership per Clarifications Q1 in [spec.md](./spec.md).

**Checkpoint**: Every folder named in CLAUDE.md's "Where to find things" tree exists; the map doc lists every one of them.

---

## Phase 3: User Story 1 — Backend tooling (Priority: P1) 🎯 MVP slice 1 of 3

**Goal**: A backend-engineer can put Python code under `app/backend/` and run one documented command to lint + type-check it. The command must exit 0 on an empty target.

**Independent Test**: From a fresh clone, run the documented bootstrap steps (see [quickstart.md](./quickstart.md) Step 2) and then `uv run ruff check app/backend && uv run mypy app/backend` — expect exit 0 in under 15 s (SC-003).

### Implementation for User Story 1

- [X] T004 [US1] Create `pyproject.toml` at the repo root. Required content: `[project]` table with `name = "techscreen"`, `version = "0.0.0"`, `requires-python = ">=3.12,<3.13"`, empty `dependencies = []`; `[dependency-groups.dev]` with `ruff`, `mypy`; `[tool.ruff]` with `target-version = "py312"`, `line-length = 100`, and select rules `E`, `F`, `I`, `B`, `UP`; `[tool.mypy]` with `python_version = "3.12"`, `strict = true`, `files = ["app/backend"]`. No runtime dependencies — T02 adds FastAPI later. Reference: [research.md](./research.md) §1.
- [X] T005 [US1] Generate the Python lockfile by running `uv lock` at the repo root (after T004). Commit `uv.lock` exactly as produced — the file must match what `Dockerfile` `COPY pyproject.toml uv.lock ./` expects. Reference: [research.md](./research.md) §5.
- [X] T006 [US1] Run `uv sync --dev` at the repo root and confirm it creates `.venv/` with `ruff` and `mypy` installed. `.venv/` is already ignored by the repo-root `.gitignore`; confirm with `git status --short` (no `.venv/` entry expected). If `.venv/` appears as untracked, extend `.gitignore` minimally (but per FR-008 `.gitignore` is protected — so instead verify the existing `.gitignore` already covers it).
- [X] T007 [US1] Run the US1 acceptance command `uv run ruff check app/backend && uv run mypy app/backend`. Expect exit 0 in under 15 s against the empty `app/backend/` target (currently only `.gitkeep`). If mypy emits "no files to check" and exits non-zero, adjust `[tool.mypy]` to allow empty packages (e.g. set `files` to a glob that tolerates zero matches, or invoke mypy against a specific module path). Reference: [research.md](./research.md) §3, [contracts/dev-commands.md](./contracts/dev-commands.md) Command 1.

**Checkpoint**: Backend check command documented in [contracts/dev-commands.md](./contracts/dev-commands.md) exits 0; `pyproject.toml` + `uv.lock` committed; `Dockerfile` build no longer fails at the `COPY pyproject.toml uv.lock ./` step.

---

## Phase 4: User Story 2 — Frontend tooling (Priority: P1) 🎯 MVP slice 2 of 3

**Goal**: A frontend-engineer can put TypeScript/React code under `app/frontend/` and run one documented command to lint + type-check it. The command must exit 0 on an empty target.

**Independent Test**: After bootstrap (`pnpm --dir app/frontend install --frozen-lockfile`), run `pnpm --dir app/frontend lint` — expect exit 0 in under 30 s (SC-004).

### Implementation for User Story 2

- [X] T008 [US2] Create `app/frontend/package.json`. Required fields: `name = "@techscreen/frontend"`, `private = true`, `version = "0.0.0"`, `engines.node = "20.x"`, `engines.pnpm = "9.x"`, `packageManager = "pnpm@9.12.0"` (match `Dockerfile.frontend` exactly), `scripts.lint = "eslint . --ext .ts,.tsx,.js,.jsx --max-warnings 0 --no-error-on-unmatched-pattern && tsc --noEmit"`, `devDependencies` with `typescript`, `@types/node`, `eslint`, `@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`, `eslint-config-prettier`, `prettier`. No runtime deps — T03 adds Next.js later. Reference: [research.md](./research.md) §2.
- [X] T009 [P] [US2] Create `app/frontend/tsconfig.json`. Required compiler options: `"strict": true`, `"target": "ES2022"`, `"module": "ESNext"`, `"moduleResolution": "Bundler"`, `"noEmit": true`, `"jsx": "preserve"`, `"esModuleInterop": true`, `"skipLibCheck": true`, `"isolatedModules": true`. `"include": ["**/*.ts", "**/*.tsx"]`, `"exclude": ["node_modules", ".next", "dist"]`. Reference: [research.md](./research.md) §2.
- [X] T010 [P] [US2] Create `app/frontend/.eslintrc.cjs`. Required content: CommonJS export with `root: true`, `parser: "@typescript-eslint/parser"`, `parserOptions: { ecmaVersion: "latest", sourceType: "module", project: false }`, `plugins: ["@typescript-eslint"]`, `extends: ["eslint:recommended", "plugin:@typescript-eslint/recommended", "prettier"]`, `env: { browser: true, node: true, es2022: true }`. Legacy `.eslintrc` format (not flat config) per [research.md](./research.md) §2.
- [X] T011 [P] [US2] Create `app/frontend/.prettierrc.json` with `{ "printWidth": 100, "singleQuote": true, "semi": true, "trailingComma": "all" }`. Matches 100-char limit used by ruff; single-quote + semi conventions from `docs/design/`.
- [X] T012 [P] [US2] Create `app/frontend/.gitignore` with `node_modules/`, `.next/`, `dist/`, `out/`, `*.log`, `.turbo/`, `coverage/`. Repo-root `.gitignore` already covers most of these, but a folder-local ignore keeps the frontend self-contained for tooling that ignores parent gitignores.
- [X] T013 [US2] Generate `app/frontend/pnpm-lock.yaml` by running `pnpm --dir app/frontend install` (after T008–T012 all exist). Commit the lockfile exactly as produced — it must match what `Dockerfile.frontend` `COPY app/frontend/package.json app/frontend/pnpm-lock.yaml ./` expects. Once complete, remove `app/frontend/.gitkeep` created in T002 because the folder is no longer empty. Reference: [research.md](./research.md) §5.
- [X] T014 [US2] Run the US2 acceptance command `pnpm --dir app/frontend lint`. Expect exit 0 in under 30 s against the empty `app/frontend/src/` target. If ESLint errors "No files matching", confirm `--no-error-on-unmatched-pattern` is present in the lint script; if `tsc --noEmit` fails on zero matches, confirm the `include` glob allows zero matches. Reference: [research.md](./research.md) §3, [contracts/dev-commands.md](./contracts/dev-commands.md) Command 2.

**Checkpoint**: Frontend check command exits 0; `package.json` + `pnpm-lock.yaml` committed; `Dockerfile.frontend` build no longer fails at the `COPY app/frontend/package.json app/frontend/pnpm-lock.yaml ./` step.

---

## Phase 5: User Story 3 — Guardrails active and documented (Priority: P1) 🎯 MVP slice 3 of 3

**Goal**: Every contributor runs the same guardrail checks locally before pushing. Bootstrap is one documented command; the hooks fire on every `git commit`.

**Independent Test**: From a fresh clone, run the documented bootstrap (including `pre-commit install`) and then `pre-commit run --all-files` — expect exit 0 in under 60 s (SC-002). Attempting to commit a file containing a fake secret pattern is blocked by the local hook.

### Implementation for User Story 3

- [X] T015 [US3] Edit `README.md` to add a new top-level section `## Developer setup` directly after the existing introduction. Section contents (verbatim from [research.md](./research.md) §7): prerequisites (Python 3.12, Node 20 LTS, pnpm 9 via corepack, `uv`, `pre-commit` ≥ 3.7.0 with install hints), one-time bootstrap commands (`uv sync --dev`, `pnpm --dir app/frontend install --frozen-lockfile`, `pre-commit install && pre-commit install --hook-type commit-msg`), and a "Check commands" subsection listing the three contracted commands verbatim from [contracts/dev-commands.md](./contracts/dev-commands.md). Do not modify any other part of `README.md`. FR-008 forbids changes to `CLAUDE.md`, `.env.example`, ADRs, etc.
- [X] T016 [US3] Run `pre-commit run --all-files` on the T01-complete tree. Expect exit 0 in under 60 s. If any hook fires on a T01-new file (e.g. a lockfile flagged as large, a JSON config malformed, a secret-shaped string detected), fix the offending file rather than modifying the hook — FR-009 forbids editing `.pre-commit-config.yaml`. Reference: [contracts/dev-commands.md](./contracts/dev-commands.md) Command 3.

**Checkpoint**: All three documented commands exit 0 in their SC budgets. MVP (US1 + US2 + US3) is complete and independently usable.

---

## Phase 6: User Story 4 — Layout matches CLAUDE.md (Priority: P2)

**Goal**: The repository layout the implementation plan and CLAUDE.md describe is actually present — sub-agents reading those docs do not encounter missing folders.

**Independent Test**: Run the layout audit from [quickstart.md](./quickstart.md) Step 4 — expect zero `MISSING:` lines and both lockfiles reported as present.

### Implementation for User Story 4

- [X] T017 [US4] Run the folder-existence audit from [quickstart.md](./quickstart.md) Step 4 (the `for d in … do [ -d "$d" ]` loop). Verify every folder named in the CLAUDE.md "Where to find things" tree exists. If any `MISSING:` line appears, re-run T002 to add the missing `.gitkeep`.
- [X] T018 [P] [US4] Audit `docs/engineering/directory-map.md` for completeness: every folder returned by `ls -d */ */*/` at the repo root (filtered to canonical folders) must have exactly one row in the map. Every row must name a real folder. No orphan rows, no missing rows. Update the map in place if drift is found.

**Checkpoint**: 100% of folders in CLAUDE.md's "Where to find things" tree exist; `docs/engineering/directory-map.md` is complete and accurate (SC-005).

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: End-to-end validation against success criteria. No new files introduced by this phase beyond trivial fixes flagged during validation.

- [X] T019 Run the full [quickstart.md](./quickstart.md) walkthrough Steps 1–5 end-to-end on the T01 branch. Record the wall-clock time for Step 3 commands and compare to SC-002 / SC-003 / SC-004 budgets. Any step that fails is a merge-blocker.
- [X] T020 [P] Verify the FR-008 / FR-009 "pre-existing assets untouched" invariant by running the diff audit from [quickstart.md](./quickstart.md) Step 5. Expected output: only `README.md` shows modifications among the protected list; every other protected file reports 0 changes. Any unexpected modification is a merge-blocker (SC-005).
- [X] T021 [P] Spot-check SC-007 by grepping every T01-new file for credential-shaped strings using the existing guardrail hooks (`pre-commit run gitleaks --all-files` and `pre-commit run detect-secrets --all-files`). Expect zero findings. If any, fix the offending file; do not suppress the hook.

**Checkpoint**: All success criteria satisfied. The PR is ready for `reviewer` sub-agent handoff.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 Setup** (T001): No dependencies.
- **Phase 2 Foundational** (T002–T003): depends on Setup.
- **Phase 3 US1** (T004–T007): depends on Foundational (needs `app/backend/.gitkeep` to exist so mypy has a target).
- **Phase 4 US2** (T008–T014): depends on Foundational (needs `app/frontend/` to exist).
- **Phase 5 US3** (T015–T016): depends on Phases 3 and 4 (T015 README references the check commands; T016 pre-commit runs against the post-T01 tree including lockfiles from T005 and T013).
- **Phase 6 US4** (T017–T018): depends on Foundational and all MVP phases (needs the folder tree and any folder-changing edits from T013 reflected in the map).
- **Phase 7 Polish** (T019–T021): depends on everything prior.

### User story dependencies

- **US1** and **US2** are independent — they touch disjoint files and could be completed in either order. Both share the Foundational phase.
- **US3** consumes US1 + US2 outputs (documents their commands; runs pre-commit over their lockfiles) so it follows them.
- **US4** is a validation story; it follows US1/US2/US3 completion to avoid false negatives from in-flight changes.

### Within each phase

- `[P]`-marked tasks inside a phase may be opened in any order.
- Non-`[P]` tasks inside a phase are strictly sequential.
- T005 depends on T004 (lockfile needs a manifest).
- T013 depends on T008–T012 (lockfile needs package.json + configs + frontend gitignore).
- T014 depends on T013 (lint needs node_modules).

### Parallel opportunities within this task set

- T002 and T003 are `[P]` — folder creation and map doc can happen in either order once Setup is done.
- T009, T010, T011, T012 are all `[P]` within Phase 4 — different files, no shared state.
- T020 and T021 are `[P]` within Polish — independent audits.

**Constitution §18 reminder**: all `[P]` markers inside this file are intra-orchestrator hints. No sub-agent fan-out is declared for T01 (implementation-plan states `agent: orchestrator, parallel: false`). Sub-agent fan-out starts with T02/T03 once T01 lands.

---

## Parallel Example: User Story 2

Inside Phase 4, once T008 (`package.json`) exists, the four dependent config files can be written in any order:

```bash
# The orchestrator opens these four files in any order — none depends on the others.
Task: "T009 — write app/frontend/tsconfig.json"
Task: "T010 — write app/frontend/.eslintrc.cjs"
Task: "T011 — write app/frontend/.prettierrc.json"
Task: "T012 — write app/frontend/.gitignore"
# Only after all four are committed does T013 (`pnpm install` → lockfile) run.
```

---

## Implementation Strategy

### MVP slice (US1 + US2 + US3)

1. Complete Phase 1 Setup (T001).
2. Complete Phase 2 Foundational (T002–T003) — unblocks every story.
3. Complete Phase 3 US1 (T004–T007) — backend check green.
4. Complete Phase 4 US2 (T008–T014) — frontend check green.
5. Complete Phase 5 US3 (T015–T016) — guardrails documented + verified.
6. **STOP and VALIDATE** — the PR is MVP-complete. Run [quickstart.md](./quickstart.md) to confirm all three contracted commands exit 0 and the bootstrap takes < 10 min.

At this point T01's acceptance criteria from `docs/engineering/implementation-plan.md` are met and the PR could ship without US4 — US4 strengthens auditability but is not on the critical path.

### Incremental delivery (add US4 and Polish)

7. Complete Phase 6 US4 (T017–T018) — layout audit.
8. Complete Phase 7 Polish (T019–T021) — end-to-end validation, diff audit, secret scan.
9. Hand off to `reviewer` sub-agent for merge gate.

### Rollback posture

Every task in this list is a pure file edit or a deterministic re-runnable command (`uv lock`, `pnpm install`, `pre-commit run`). Reverting T01 is a single `git revert` of the T01 commit(s) — no data migration, no Cloud Run state change, no Vertex state change (§19).

---

## Notes

- All `[P]` tasks in this file edit different files; no task in this list requires a sub-agent other than the orchestrator.
- File paths are absolute-ish relative to the repo root; no need for `cd` manoeuvres during implementation.
- Verify quickstart.md runs green before handing off for review.
- Commit cadence: one commit per phase is the suggested default; larger PRs can be squashed at merge time. We commit manually (see CLAUDE.md — `auto_commit: false`).
- Any task whose acceptance fails in a way not covered by the spec: surface the ambiguity to the user before working around it; do not silently broaden T01's scope.
