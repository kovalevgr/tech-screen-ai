# Implementation Plan: Monorepo Layout & Tooling Baseline (T01)

**Branch**: `001-t01-monorepo-baseline` | **Date**: 2026-04-23 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/001-t01-monorepo-baseline/spec.md`

## Summary

T01 is the one-off scaffolding PR that turns the repo from "docs + specs only" into a workspace every downstream task can build in. It creates the canonical folder tree (`app/backend/`, `app/frontend/`, `alembic/`, `configs/`, `infra/terraform/`, `.github/workflows/`, `evals/`), commits the baseline tooling configs (`pyproject.toml` + `uv.lock` at the repo root; `app/frontend/package.json` + `pnpm-lock.yaml`), activates the already-committed `.pre-commit-config.yaml` guardrails, and documents the three check commands so a new contributor can reach "all green" in under 10 minutes. No runtime feature code ships in this PR.

Three decisions were locked in during `/speckit-clarify`:

1. Empty canonical folders are marked with `.gitkeep` + indexed in a single new doc at `docs/engineering/directory-map.md`.
2. Runtime versions are pinned via native mechanisms only (`pyproject.toml requires-python`, `package.json engines.node` + `engines.pnpm`). No `.tool-versions` / `.nvmrc`.
3. `uv` is the Python package manager for local dev, matching the existing `Dockerfile`. Contributors install `uv` as a prerequisite.

## Technical Context

**Language/Version**: Python 3.12 (backend lint/type-check targets; matches `Dockerfile`) · TypeScript 5.x on Node 20 LTS (frontend; matches `Dockerfile.frontend`)
**Primary Dependencies** (dev-only, no runtime deps in T01):

- Python dev group: `ruff`, `mypy`, managed by `uv` against `pyproject.toml` + `uv.lock`.
- Node dev deps: `typescript`, `eslint`, `@typescript-eslint/*`, `prettier`, `eslint-config-prettier`. Managed by `pnpm` against `package.json` + `pnpm-lock.yaml`.
- Pre-commit ≥ 3.7.0 (already required by `.pre-commit-config.yaml`).

**Storage**: N/A (tooling only; Postgres arrives with T05).
**Testing**: N/A at the T01 layer — the acceptance tests are the three check commands themselves. Unit/integration tests begin in T02/T03 once source files exist. No tests are authored in T01.
**Target Platform**: macOS (primary dev), Linux (CI, prod Cloud Run). Windows is out of scope.
**Project Type**: Monorepo web (backend + frontend in one repo, separate toolchains).
**Performance Goals**: guardrails < 60 s · backend check < 15 s on empty target · frontend check < 30 s on empty target · bootstrap reachable in < 10 min (SC-001 – SC-004).
**Constraints**:

- No runtime feature code may ship in this PR (FR-007).
- Pre-existing assets (ADRs, docs, prompts, Dockerfiles, compose files, `.env.example`, CLAUDE.md, `README.md`, `.pre-commit-config.yaml`) must not be reshaped (FR-008, FR-009).
- Lint/type-check commands must exit 0 on empty targets (Edge Case).
- No pre-commit hook may mutate tracked files (FR-014; also stated in `.pre-commit-config.yaml` header comment).

**Scale/Scope**: Single PR, ~15-20 new files, ~300 lines of config. One committer (orchestrator). No sub-agent fan-out.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

T01 is a scaffolding PR with no runtime behaviour, no data writes, no LLM calls, and no deploy artefacts. Most invariants are not in scope; the ones that are, pass cleanly:

| § | Principle | Applies to T01? | Status |
|---|-----------|-----------------|--------|
| 1 | Candidates first | Indirectly — better tooling shortens feedback loops | Pass |
| 2 | Deterministic orchestration | No | N/A |
| 3 | Append-only audit trail | No (no DB code) | N/A |
| 4 | Immutable rubric snapshots | No | N/A |
| 5 | No plaintext secrets | Yes — every new T01 file must pass `gitleaks` and `detect-secrets` (already wired in `.pre-commit-config.yaml`). SC-007 validates. | Pass |
| 6 | Workload Identity Federation only | No (no SA keys touched) | N/A |
| 7 | Docker parity dev → CI → prod | Yes — `pyproject.toml` + `uv.lock` must be the exact pair `Dockerfile` expects; `package.json` + `pnpm-lock.yaml` the pair `Dockerfile.frontend` expects. Clarifications Q2/Q3 pin the mechanism. | Pass |
| 8 | Production-only topology | No | N/A |
| 9 | Dark launch by default | No (no features) | N/A |
| 10 | Migration approval | No (no migrations) | N/A |
| 11 | Hybrid language | No (no prompts) | N/A |
| 12 | LLM cost and latency caps | No | N/A |
| 13 | Calibration never blocks merge | No | N/A |
| 14 | Contract-first for parallel work | T01 has `contract: none` in the implementation plan and no sub-agent fan-out, so the rule does not engage. Still, the three documented commands (FR-002/003/004) are written out as a contract artefact (`contracts/dev-commands.md`) so T02 and T03 can rely on a stable entrypoint. | Pass |
| 15 | PII containment | No (no user data) | N/A |
| 16 | Configs as code | Yes — every T01 file lives in Git; the new `docs/engineering/directory-map.md` is the canonical index. | Pass |
| 17 | Specifications precede implementation | Yes — `/speckit-specify` and `/speckit-clarify` ran before this plan. | Pass |
| 18 | Multi-agent orchestration is explicit | Yes — plan declares `agent: orchestrator, parallel: false`. No sub-agent fan-out. | Pass |
| 19 | Rollback is a first-class operation | Indirectly — a T01-only PR is trivially reverted with `git revert`. No migration, no Cloud Run state change. | Pass |
| 20 | Floor, not ceiling | Pass | Pass |

**Gate result**: PASS. No violations, no justifications required in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-t01-monorepo-baseline/
├── spec.md                         # Feature spec (+ Clarifications section)
├── plan.md                         # This file
├── research.md                     # Phase 0 — tool-choice decisions
├── data-model.md                   # Phase 1 — canonical entities (trivial: 3 entities from spec)
├── contracts/
│   └── dev-commands.md             # Phase 1 — the 3 documented check commands (interface contract for T02/T03)
├── quickstart.md                   # Phase 1 — reviewer-facing validation walkthrough
├── checklists/
│   └── requirements.md             # From /speckit-specify (passed)
└── tasks.md                        # Created by /speckit-tasks (NOT this command)
```

### Source Code (repository root)

After T01 merges, the repo root looks like this. Every bold entry is created or edited by T01; everything else is pre-existing and untouched.

```text
.                                        # repo root
├── .env.example                         # pre-existing, unchanged
├── .dockerignore                        # pre-existing, unchanged
├── .gitignore                           # pre-existing, unchanged
├── .pre-commit-config.yaml              # pre-existing, unchanged
├── .github/
│   └── workflows/                       # NEW (empty, .gitkeep marker)
│       └── .gitkeep
├── .claude/                             # pre-existing (agents + skills), unchanged
├── .specify/                            # pre-existing (templates + memory), unchanged
├── CLAUDE.md                            # pre-existing, unchanged
├── README.md                            # EDITED — adds "Developer setup" section
├── Dockerfile                           # pre-existing, unchanged
├── Dockerfile.frontend                  # pre-existing, unchanged
├── Dockerfile.vertex-mock               # pre-existing, unchanged
├── docker-compose.yml                   # pre-existing, unchanged
├── docker-compose.test.yml              # pre-existing, unchanged
├── pyproject.toml                       # NEW — Python tooling (ruff + mypy), dev deps via uv
├── uv.lock                              # NEW — uv lockfile (matches Dockerfile expectation)
├── adr/                                 # pre-existing, unchanged
├── docs/
│   ├── engineering/
│   │   └── directory-map.md             # NEW — central index of canonical folders (Q1)
│   ├── specs/                           # pre-existing, unchanged
│   ├── design/                          # pre-existing, unchanged
│   └── kickoff/                         # pre-existing, unchanged
├── prompts/                             # pre-existing, unchanged
├── infra/
│   ├── bootstrap.sh                     # pre-existing, unchanged
│   └── terraform/                       # NEW (empty, .gitkeep marker)
│       └── .gitkeep
├── alembic/                             # NEW (empty, .gitkeep marker)
│   └── .gitkeep
├── configs/                             # NEW (empty, .gitkeep marker)
│   └── .gitkeep
├── evals/                               # NEW (empty, .gitkeep marker)
│   └── .gitkeep
└── app/
    ├── backend/                         # NEW (empty, .gitkeep marker)
    │   └── .gitkeep
    └── frontend/
        ├── package.json                 # NEW — pnpm + eslint + prettier + tsc devDeps, engines pinned
        ├── pnpm-lock.yaml               # NEW — pnpm lockfile (matches Dockerfile.frontend expectation)
        ├── tsconfig.json                # NEW — minimal TS config so `tsc --noEmit` works on empty target
        ├── .eslintrc.cjs                # NEW — ESLint flat-compat config
        ├── .prettierrc.json             # NEW — Prettier config (defaults + 1 override for tokens)
        └── .gitignore                   # NEW — node_modules, .next, build artefacts
```

**Structure Decision**: Monorepo web (backend + frontend). Toolchains are intentionally partitioned — repo-root `pyproject.toml` + `uv.lock` govern Python; `app/frontend/package.json` + `pnpm-lock.yaml` govern TypeScript. This mirrors the two Dockerfiles exactly (ADR-010 Docker parity) and avoids pulling Node tooling into the Python virtualenv or vice versa. The backend folder itself stays empty at T01 close — T02 (FastAPI skeleton) is its first real inhabitant. Frontend ships tsconfig/eslint/prettier configs now (without them `tsc --noEmit` fails on an empty target) but no application code — T03 (Next.js skeleton) adds that.

**Single committer**: `agent: orchestrator`, `parallel: false`. T01 is the seed that unblocks parallel fan-out; it does not itself fan out.

## Phase 0 — Outline & Research

Research output: [research.md](./research.md) (generated as part of this plan run).

The spec had no `[NEEDS CLARIFICATION]` markers after Q1–Q3 were answered. Phase 0 resolves implementation-detail questions that are below the spec's altitude but above `/speckit-tasks` altitude:

1. **Python tooling choice** — ruff config preset, mypy strictness level, how dev deps are declared in `pyproject.toml` so `uv sync --dev` populates them.
2. **Node tooling choice** — ESLint flavour (legacy `.eslintrc` vs flat `eslint.config.js`), Prettier config surface, minimum `tsconfig.json` to let `tsc --noEmit` pass on zero files.
3. **Empty-target lint behaviour** — both `ruff check` and `tsc --noEmit` must exit 0 when they find no files. Verify each tool's behaviour here so we don't need a placeholder source file.
4. **`.pre-commit-config.yaml` already-installed sanity check** — the file exists; research confirms every hook declared there can actually run after T01's new files land (i.e. `gitleaks`, `detect-secrets`, merge-conflict, yaml/json/toml checks) without additional configuration.
5. **Lockfile bootstrap** — exact commands to produce `uv.lock` and `pnpm-lock.yaml` deterministically on the orchestrator's machine.

All resolved in `research.md` with rationale and rejected alternatives.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T01 has no application data, but the spec's "Key Entities" section (canonical folder, tooling configuration file, guardrail hook) are re-expressed as a minimal entity map so the reviewer has a single surface to check.

### Contracts

See [contracts/dev-commands.md](./contracts/dev-commands.md). The three documented commands (FR-002/003/004) are the interface T01 hands off to T02/T03/T10. Fixing them in a contract file makes it impossible for a later task to silently change the entrypoint without an obvious PR diff.

### Quickstart

See [quickstart.md](./quickstart.md) — a 5-step walkthrough a reviewer (human or `reviewer` agent) can follow to validate the T01 PR in under 5 minutes. Exactly mirrors SC-006 ("validate using only the three documented commands").

### Agent context update

`CLAUDE.md` does **not** carry `<!-- SPECKIT START -->` / `<!-- SPECKIT END -->` markers — T00 deliberately stripped them (see `docs/engineering/implementation-plan.md` T00 "Trim before commit"). The project's existing "How work happens here (Spec Kit)" section in CLAUDE.md already points sub-agents at the Spec Kit flow, so T01 does not re-introduce the auto-generated block. No CLAUDE.md edit from this step.

### Re-evaluate Constitution Check (post-design)

Nothing in Phase 0/1 changes the Constitution Check result. Gate remains PASS.

## Complexity Tracking

Not applicable — no Constitution Check violations. This table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| *(none)* | — | — |
