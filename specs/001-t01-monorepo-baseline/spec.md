# Feature Specification: Monorepo Layout & Tooling Baseline (T01)

**Feature Branch**: `001-t01-monorepo-baseline`
**Created**: 2026-04-23
**Status**: Draft
**Input**: User description: "T01 — Monorepo layout + tooling baseline" (from `docs/engineering/implementation-plan.md`, Tier 1 / W1–W2)

## Clarifications

### Session 2026-04-23

- Q: How does T01 make empty-but-canonical folders self-explanatory to a sub-agent opening them cold? → A: Hybrid — `.gitkeep` in every otherwise-empty canonical folder + a single central index at `docs/engineering/directory-map.md` listing every canonical folder, its owner task, and its purpose.
- Q: How are local Python/Node versions pinned for contributors? → A: Native-only — `pyproject.toml` declares `requires-python`, `package.json` declares `engines.node` and `engines.pnpm`. No `.tool-versions`, `.nvmrc`, or other dedicated pin file. README documents target versions for contributors not on a version manager.
- Q: Local Python package manager — uv or pip-compatible? → A: `uv` required. README's "Developer setup" instructs `uv` install, then `uv sync --dev`; adding deps is always `uv add …`. Single documented path; matches Docker parity (ADR-010).

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the humans and AI sub-agents who will build TechScreen on top of it: `backend-engineer`, `frontend-engineer`, `infra-engineer`, `prompt-engineer`, `reviewer`, and the human developers/reviewers on the team. Until the monorepo layout and tooling baseline exist, every downstream task (T02 FastAPI skeleton, T03 Next.js skeleton, T05 DB schema, T06 Cloud Run, etc.) is blocked because there is nowhere to put their code and no way to validate it.

### User Story 1 — A backend-engineer can put Python code into a canonical location and have it validated (Priority: P1)

A sub-agent or human engineer working on any backend task needs a single, canonical location to write Python code, plus tooling that will reject code which violates project standards. Without this, every PR invents its own folder structure and lint configuration.

**Why this priority**: Without a canonical backend folder and a working lint/type-check command, T02 (FastAPI skeleton) and every later backend task cannot begin. This is the single largest unblocker in Tier 1.

**Independent Test**: A developer clones the repo, runs the documented one-liner to check backend code, and sees a green result even on an empty backend target. They then add a deliberately broken Python file and the same command fails with a clear diagnostic.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repo on a supported developer machine, **When** the developer runs the documented backend-check command, **Then** the command completes successfully without any installation or configuration steps beyond the documented prerequisites.
2. **Given** a canonical backend folder exists, **When** a developer writes a Python file with a style or typing violation and runs the backend-check command, **Then** the command fails and points at the offending file and line.
3. **Given** the backend check is green, **When** the developer inspects the repo, **Then** they find one obvious place to add new backend modules and no ambiguity about which folder is "the backend".

---

### User Story 2 — A frontend-engineer can put TypeScript/React code into a canonical location and have it validated (Priority: P1)

The frontend sub-agent needs a canonical place for Next.js/React code and a working lint pipeline. Without it, T03 (Next.js skeleton) cannot start, and the design-system discipline in `docs/design/` cannot be enforced.

**Why this priority**: Parallel to User Story 1 for the frontend half of the stack. Co-equal P1 because the two halves are symmetric and both gate Tier 1 completion.

**Independent Test**: A developer runs the documented frontend-lint command on a clean tree and sees a green result. Introducing a deliberate TypeScript or ESLint violation produces a clear failure.

**Acceptance Scenarios**:

1. **Given** a fresh clone and the documented frontend prerequisites installed, **When** the developer runs the frontend-lint command, **Then** the command exits successfully.
2. **Given** a canonical frontend folder exists, **When** a developer commits TypeScript code that violates ESLint or the configured type checker, **Then** the frontend-lint command fails with a file-and-line diagnostic.

---

### User Story 3 — Every contributor runs the same guardrail checks locally before pushing (Priority: P1)

Constitution §5–6 and ADR-013 forbid secrets in source. Constitution §15 forbids PII in logs. The reviewer sub-agent runs these checks in CI, but waiting for CI to catch a leaked secret is the wrong point at which to catch it. Every contributor needs a single, documented command that runs the guardrails locally.

**Why this priority**: Co-equal P1. The guardrails themselves already exist (`.pre-commit-config.yaml` is committed); this story is about making them executable on every developer machine with one documented command and wiring them so `git commit` invokes them automatically.

**Independent Test**: A developer runs the pre-commit install step once, then runs the "check everything" command on a clean tree and sees a green result. Attempting to commit a file containing an obvious fake secret (e.g. a plausible-looking API key) is blocked by the local hook.

**Acceptance Scenarios**:

1. **Given** a fresh clone, **When** the developer runs the documented bootstrap + check command on a clean tree, **Then** all guardrail checks pass.
2. **Given** pre-commit hooks are installed, **When** a developer stages a file containing a fake secret pattern and attempts to commit, **Then** the commit is blocked and the hook points at the offending file.
3. **Given** the project has no branches that violate invariants, **When** CI runs the same guardrail command on a PR, **Then** the CI result matches the developer's local result.

---

### User Story 4 — The repository layout matches what CLAUDE.md and the implementation plan describe (Priority: P2)

Every canonical document (CLAUDE.md "Where to find things", implementation-plan.md, ADRs) refers to folders like `app/backend/`, `app/frontend/`, `alembic/`, `configs/`, `.github/workflows/`, and `evals/` as if they already exist. Sub-agents reading those docs will fail in confusing ways if the folders are missing.

**Why this priority**: P2 because the folders being present but empty is acceptable — as long as they exist and a later task (T02, T03, T05, T06a, T10) can place files inside them. P1 tasks above already require the folders that matter most; this story ensures completeness.

**Independent Test**: A sub-agent or developer opens the repo and finds every folder that CLAUDE.md's "Where to find things" section names. No folder is missing.

**Acceptance Scenarios**:

1. **Given** the repo is checked out, **When** a sub-agent looks for any folder listed in the CLAUDE.md "Where to find things" tree, **Then** that folder exists (possibly empty, possibly with a placeholder file).
2. **Given** a folder is created by this task, **When** a downstream task writes files into it, **Then** no layout change is required.

---

### Edge Cases

- **Pre-existing scaffolding.** Several folders are already present (`adr/`, `docs/`, `prompts/`, `infra/`, `.claude/`, `.specify/`). T01 must not overwrite, renumber, or reshape them. Existing files are byte-preserved unless the task explicitly edits them.
- **Pre-existing `.pre-commit-config.yaml`.** The hooks file is already committed. T01 activates it (install + ensure it runs green) rather than authoring it.
- **Empty lint targets.** Immediately after T01, the backend and frontend folders contain nothing substantive. Lint and type-check commands must exit 0 on empty targets; they must not require at least one source file to pass.
- **Non-contributor clones.** A user cloning the repo to read the spec (no intent to build) must not be forced through the bootstrap steps. Tooling setup is opt-in for contributors, not required for readers.
- **OS portability.** Developer machines in the team include macOS (primary) and Linux (CI). Tooling must run on both. Windows is out of scope for MVP.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST contain a canonical top-level folder layout matching the tree in [CLAUDE.md](../../CLAUDE.md) "Where to find things" and the T01 description in [docs/engineering/implementation-plan.md](../../docs/engineering/implementation-plan.md). At minimum: `app/backend/`, `app/frontend/`, `alembic/`, `configs/`, `prompts/` (exists), `infra/terraform/`, `docs/` (exists), `.github/workflows/`, `evals/`.
- **FR-002**: The repository MUST provide a single documented command that lints and type-checks the backend Python code. The command MUST exit zero on a clean tree, including when the target contains no Python source files yet.
- **FR-003**: The repository MUST provide a single documented command that lints the frontend code (TypeScript + ESLint + formatter). The command MUST exit zero on a clean tree.
- **FR-004**: The repository MUST provide a single documented command that runs every pre-commit guardrail on the whole tree. The command MUST exit zero on a clean tree.
- **FR-005**: Pre-commit hooks MUST be installable with a single documented bootstrap step. Once installed, `git commit` MUST invoke them automatically.
- **FR-006**: The bootstrap MUST not require any credential, secret, cloud login, or network access to private services. Public package registries (PyPI, npm) are acceptable; anything gated by a password or token is not.
- **FR-007**: The T01 PR MUST NOT introduce any runtime feature code (no API endpoints, no UI pages, no migrations, no agents). Only layout, tooling configuration, and placeholder/marker files required by the tooling itself are permitted.
- **FR-008**: The T01 PR MUST NOT overwrite or reshape pre-existing assets: `adr/`, `docs/` content, `prompts/` content, `infra/bootstrap.sh`, `.claude/` content, `.specify/` content, the repo-root Dockerfiles and docker-compose files, `README.md`, `.env.example`, `.gitignore`, `.dockerignore`, and CLAUDE.md.
- **FR-009**: The `.pre-commit-config.yaml` file already in the repo MUST be preserved as-is. T01 activates and documents its use; T01 does not modify hook selection or rules.
- **FR-010**: For each new canonical folder created by T01 that would otherwise be empty, a `.gitkeep` marker file MUST be committed so git tracks the folder, AND a single central index at `docs/engineering/directory-map.md` MUST list every canonical folder, its owner task (the T-id that populates it), and its purpose. The map doc is the single source of truth for folder ownership; the `.gitkeep` markers are passive and contain no metadata beyond existence. A sub-agent encountering an empty folder consults the map doc to learn why it is there.
- **FR-011**: The backend tooling configuration MUST be compatible with Python 3.12 (matching the repo `Dockerfile` baseline) and MUST live in a single canonical configuration file at the repo root. That file MUST declare `requires-python = ">=3.12,<3.13"` so contributors and `uv` itself reject incompatible interpreters. The committed lockfile MUST be the one that the repo `Dockerfile` expects (i.e. `uv.lock` at the repo root); any contributor-facing bootstrap instructions MUST use `uv` (install uv → `uv sync --dev`), and adding or removing dependencies MUST go through `uv` so the lockfile stays canonical.
- **FR-012**: The frontend tooling configuration MUST use pnpm as the package manager (matching the exclude rules already in `.pre-commit-config.yaml`) and MUST live under `app/frontend/`. `package.json` MUST declare `engines.node` and `engines.pnpm` fields pinning the major versions used by `Dockerfile.frontend`. The committed lockfile MUST be `app/frontend/pnpm-lock.yaml` (already referenced by `Dockerfile.frontend`).
- **FR-013**: The documented commands for FR-002, FR-003, FR-004 MUST be discoverable in a single location (e.g. `README.md` "Developer setup" section or an equivalent engineering doc) so that a new contributor does not have to read CI workflows to learn how to run checks locally.
- **FR-014**: Running the guardrail command on a clean tree MUST NOT modify any tracked files. Pre-commit hooks that mutate files are explicitly forbidden per the comment in the existing `.pre-commit-config.yaml`; T01 MUST NOT introduce any.

### Key Entities

- **Canonical folder.** A top-level directory whose name is referenced by CLAUDE.md, the implementation plan, or an ADR, and which is therefore expected to exist in the tree. Each canonical folder has exactly one owner task that will populate it (or has already).
- **Tooling configuration file.** A single source-of-truth file for a toolchain's rules (e.g. backend lint/type-check config, frontend lint/format config). Configurations do not duplicate between files.
- **Guardrail hook.** A check defined in `.pre-commit-config.yaml` that runs before every commit and again in CI. T01 ensures these run; it does not add or remove any.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new contributor, starting from a fresh clone on a supported machine, can reach an "all checks green" state in under 10 minutes by following the documented bootstrap, assuming the prerequisites (Python 3.12, Node + pnpm, pre-commit) are installed.
- **SC-002**: Running the guardrail command on the post-T01 clean tree completes in under 60 seconds and reports zero findings.
- **SC-003**: Running the backend lint/type-check command on the empty backend target completes in under 15 seconds and exits zero.
- **SC-004**: Running the frontend lint command on the empty frontend target completes in under 30 seconds and exits zero.
- **SC-005**: After T01 merges, 100% of the folders named in the CLAUDE.md "Where to find things" tree exist in the repo. Zero of the pre-existing files listed in FR-008 are modified by the T01 PR.
- **SC-006**: A reviewer (human or sub-agent) can validate T01 acceptance using only the three commands documented in FR-002, FR-003, FR-004, without reading the implementation diff.
- **SC-007**: Zero T01-introduced files contain a secret value, a credential, or a PII sample (validated by the existing guardrail hooks running green).

## Assumptions

- Python 3.12 is the backend runtime (matches the existing `Dockerfile`). The toolchain chosen in the implementation plan (ruff + mypy) is authoritative; a plan or later task that changes this supersedes the assumption. Python dependency management is `uv` + `uv.lock` at the repo root, matching the Dockerfile and ADR-010 Docker parity (confirmed in Clarifications Q3). Contributors install `uv` as a prerequisite.
- Node 20.x with pnpm 9.x is the frontend runtime + package manager (matches `Dockerfile.frontend`: `node:20-bookworm-slim` + `pnpm@9.12.0` via corepack). Version declarations live in `package.json engines`; no `.tool-versions` or `.nvmrc` file is committed (confirmed in Clarifications Q2). The toolchain chosen in the implementation plan (ESLint + Prettier + tsc) is authoritative.
- The primary developer OS is macOS; CI is Linux. Tooling works on both.
- `pre-commit` ≥ 3.7.0 is installed by the contributor before running the bootstrap (matches the `minimum_pre_commit_version` already declared).
- The Dockerfile at the repo root already pins Python 3.12; T01 aligns with that version rather than inventing a new one.
- No changes to `CLAUDE.md`, `README.md`, ADRs, or the constitution are expected from T01. If a layout or tooling choice turns out to diverge from those documents, T01 will flag the divergence rather than silently editing the canonical source.
- T01 is a single PR owned by the `orchestrator` agent (per the implementation plan). Sub-agent fan-out begins at T02/T03/T05/T06 once this PR lands.
- Constitution §7 (test coverage) does not require tests of the tooling itself; T01 is exempt from adding feature tests because it introduces no features. The guardrail commands themselves are the test.

## Dependencies

- **Upstream**: T00 (Spec Kit scaffolding) is complete — Spec Kit skills are present, the constitution is in place, and the templates exist. Confirmed at spec-draft time.
- **Downstream (blocked until T01 merges)**: T02 (FastAPI skeleton), T03 (Next.js skeleton), T05 (DB schema + Alembic), T06 (Cloud Run + Cloud SQL + Secret Manager), T06a (deploy/rollback), T09 (Docker stacks), T10 (CI pipeline), and every task after.
- **External**: Public package registries (PyPI for Python, npm/pnpm registry for Node) must be reachable from the contributor's machine and from CI. No private registry, no authenticated install step. Contributors install `uv` (Python dep manager) and Node 20 + pnpm as prerequisites; install instructions live in the README "Developer setup" section.
