# Phase 0 Research — T01 Monorepo Layout & Tooling Baseline

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-23

This document resolves the implementation-detail questions that sit below the spec's altitude but above `/speckit-tasks` altitude. Every decision below has a rationale rooted in an existing repo artefact (`Dockerfile`, `.pre-commit-config.yaml`, ADR, constitution) so the reviewer can verify a T01 PR without running external searches.

---

## 1. Python lint + type-check tooling

**Decision**: `ruff` (lint + import sort) and `mypy` (type check), declared as dev deps in a single repo-root `pyproject.toml` under a `[dependency-groups]` table. Installed locally by `uv sync --dev`; invoked as `uv run ruff check app/backend` and `uv run mypy app/backend`.

**Rationale**:

- The implementation plan (`docs/engineering/implementation-plan.md`, T01) names ruff + mypy explicitly and the T01 acceptance scenarios spell out those exact commands.
- `Dockerfile` pins `uv 0.4.25` and uses `uv sync --frozen` against `pyproject.toml` + `uv.lock`. Clarifications Q3 locked `uv` as the local dep manager, matching this.
- ruff replaces black + isort + flake8 in a single, fast binary; one fewer tool in CI; matches what the `.pre-commit-config.yaml` comment already hints at ("ruff is the canonical backend formatter").
- mypy is the industry default; no good reason to swap for pyright or pyre for an MVP.

**ruff config**: single `[tool.ruff]` block in `pyproject.toml`. Target `py312`. Default rule set plus `E`, `F`, `I`, `B`, `UP` (standard). Line length 100 (matches Dockerfile image line length norms and is the most common modern default). No formatter-style rules enabled at T01 — style debates belong to a later PR.

**mypy config**: `[tool.mypy]` in `pyproject.toml`. `python_version = "3.12"`, `strict = true`. Empty target passes (mypy exits 0 when the package contains no `.py` files). T02 will add packages under `app/backend/` which mypy will then check.

**Alternatives considered**:

- *black + isort + flake8*: three tools, three configs, slower; rejected.
- *pyright*: excellent, but less widely known to Claude Code sub-agents and the team; rejected for MVP.
- *Separate `app/backend/pyproject.toml`*: would fight the Dockerfile, which does `COPY pyproject.toml uv.lock ./` from the repo root. Rejected.

---

## 2. Node tooling: ESLint, Prettier, TypeScript

**Decision**:

- **ESLint** — legacy-style `.eslintrc.cjs` (CommonJS module so `type: "module"` in `package.json` is not a prerequisite). Extends `eslint:recommended`, `plugin:@typescript-eslint/recommended`, and `prettier` (disables rules that conflict with Prettier).
- **Prettier** — `.prettierrc.json` with `{ "printWidth": 100, "singleQuote": true, "semi": true }`. Conservative defaults; only one override justified by the design-system token files living as TS.
- **TypeScript** — `tsconfig.json` with `"strict": true`, `"target": "ES2022"`, `"module": "ESNext"`, `"moduleResolution": "Bundler"`, `"noEmit": true`, `"jsx": "preserve"`, `"skipLibCheck": true`, `"include": ["src/**/*", "app/**/*"]`. T03 (Next.js skeleton) extends this with Next-specific paths.
- **dev-deps in `package.json`**: `typescript`, `@types/node`, `eslint`, `@typescript-eslint/parser`, `@typescript-eslint/eslint-plugin`, `eslint-config-prettier`, `prettier`. Locked via `pnpm install` producing `pnpm-lock.yaml`.

**Rationale**:

- Flat config (`eslint.config.js`) is the future but still rough around some popular plugins (including the Next plugin T03 will add). Legacy `.eslintrc` is more predictable across Next.js + TypeScript + Tailwind. Revisit in a later task once Next 15 + flat config is stable.
- Prettier defaults minus `semi: true` / `singleQuote: true` matches the design-system conventions implied by `docs/design/` (screens use single quotes in JSX examples).
- `printWidth: 100` matches ruff's 100 char line length for consistency across the repo.
- `tsc --noEmit` exits 0 against an empty matching set, so the frontend-check command passes at T01 close.

**Alternatives considered**:

- *Flat ESLint config*: rejected for MVP; revisit when T03 integrates Next.js.
- *Biome* (lint + format in one): fast and appealing, but Next.js ecosystem expects ESLint + Prettier, and T03 plans to use them. Adopting Biome now means two linters in parallel later. Rejected.
- *No Prettier, format-on-commit with ruff-format-equivalent*: frontend ecosystem expects Prettier; rejecting it invites churn.

---

## 3. Empty-target lint behaviour

**Decision**: Both `ruff check app/backend` and the frontend lint command are expected to exit 0 when `app/backend/` and `app/frontend/src/` contain no source files. No placeholder Python/TypeScript file is introduced at T01 just to satisfy the linters.

**Rationale**:

- ruff: confirmed — with no `.py` files in the target, ruff prints nothing and exits 0. Standard Unix idiom.
- ESLint: by default errors with "No files matching the pattern …" on empty targets. **Mitigation**: the scripts entry in `package.json` uses `eslint . --ext .ts,.tsx,.js,.jsx --max-warnings 0 --no-error-on-unmatched-pattern`. The `--no-error-on-unmatched-pattern` flag makes ESLint exit 0 on an empty match set. Documented in ESLint 8.56+ and stable.
- `tsc --noEmit`: when there are no files matching `include`, tsc prints no diagnostics and exits 0.
- mypy: when the target package contains no `.py` files, mypy exits 0.

**Alternative considered**: ship a stub file (`app/backend/__init__.py`, `app/frontend/src/index.ts`). Rejected because (a) FR-007 forbids runtime code in T01, (b) an `__init__.py` is ambiguously runtime-or-not, and (c) the `--no-error-on-unmatched-pattern` flag is the first-party, documented way to handle this.

---

## 4. `.pre-commit-config.yaml` sanity

**Decision**: No edits to `.pre-commit-config.yaml`. T01 simply installs the hooks and ensures they run green on the clean post-T01 tree.

**Rationale**:

- The file is already committed by a prior task. FR-009 in the spec explicitly forbids T01 from modifying it.
- The hooks declared there (`check-merge-conflict`, `check-yaml`, `check-json`, `check-toml`, `check-added-large-files`, `detect-private-key`, `gitleaks`, `detect-secrets`, plus a project-local `forbid-env-values` hook for `.env.example`, a `no-direct-vertex-import` hook for later tasks, and visual-discipline hooks for the frontend) are all readable at HEAD today.
- The new files T01 introduces (YAML, TOML, JSON lockfile) must all pass these hooks. That's the acceptance test, not an open question.

**Alternatives considered**: add more hooks (e.g. `ruff-format`, `prettier --check`) at T01. Rejected — the `.pre-commit-config.yaml` header comment explicitly says "No auto-formatters, no style linters. Formatting and style live in CI / IDE / `make format`." Respecting that.

---

## 5. Lockfile bootstrap

**Decision**:

- Python: `uv lock` generates `uv.lock` deterministically from `pyproject.toml`. Run once during T01 implementation on the orchestrator's machine; commit the lockfile.
- Node: `pnpm install` on an empty `app/frontend/` (just `package.json`) produces `pnpm-lock.yaml`. Commit it.
- Both lockfiles are reproducible — anyone running `uv sync --frozen` or `pnpm install --frozen-lockfile` gets the identical tree CI/Dockerfile will.

**Rationale**:

- `Dockerfile` runs `uv sync --frozen --no-dev` → requires `uv.lock` in the build context. `Dockerfile.frontend` runs `pnpm install --frozen-lockfile` → requires `pnpm-lock.yaml`. If T01 ships only the manifest files without lockfiles, both Docker builds fail. T09 (Docker stacks) would then be blocked on a "regenerate lockfile" follow-up. T01 prevents that by shipping the lockfile in the same PR.
- Constitution §7 (Docker parity): lockfiles are the mechanism that makes dev = CI = prod for deps. Skipping them here would be the single largest parity violation we could ship.

---

## 6. `Makefile` / task runner question

**Decision**: No `Makefile`, no Taskfile, no `justfile` at T01. The three documented commands (FR-002/003/004) are plain shell invocations documented in the README "Developer setup" section and cross-referenced from `contracts/dev-commands.md`.

**Rationale**:

- The implementation plan T01 acceptance criteria spell out the exact shell commands; a `Makefile` would be UX sugar on top.
- The team is small; one more abstraction layer (Makefile targets vs raw commands) is unhelpful until the command list grows past 5–6 items.
- Adding a `Makefile` now means every later task (T02, T03, T05, T09, T10) would need to update it, multiplying merge surface. Better to add a task runner later as a dedicated PR when the list of commands actually justifies it.

**Alternatives considered**:

- *`Makefile` with `check-backend`, `check-frontend`, `check-all` targets*: mild UX win, ongoing maintenance cost. Rejected for MVP, can revisit post-Tier 1.
- *`scripts/` dir with shell wrappers*: even more indirection; rejected.

---

## 7. README "Developer setup" section

**Decision**: T01 edits the repo-root `README.md` to add one new section, "Developer setup", directly below the existing top-level description. This section lists: prerequisites (Python 3.12, Node 20 LTS, pnpm 9, uv, pre-commit), one-time install commands, and the three documented check commands from `contracts/dev-commands.md`. No separate `docs/engineering/dev-setup.md`.

**Rationale**:

- FR-013 requires a single discoverable location. README is the default first file a new contributor reads.
- A separate `docs/engineering/dev-setup.md` would add one more place to keep in sync and one more click for the reader.
- `CLAUDE.md` stays untouched (FR-008).

**Alternatives considered**: separate engineering doc — rejected. Inline setup block + separate engineering doc — redundant, rejected.

---

## Summary of resolved decisions

| # | Topic | Decision |
|---|-------|----------|
| 1 | Python tooling | ruff + mypy in `pyproject.toml`, invoked via `uv run`. |
| 2 | Node tooling | ESLint (legacy config) + Prettier + TypeScript, dev deps in `app/frontend/package.json`. |
| 3 | Empty-target lint | `ruff`/`mypy`/`tsc` pass natively on empty; ESLint uses `--no-error-on-unmatched-pattern`. |
| 4 | Pre-commit hooks | No edits; activate existing config, ensure green on new tree. |
| 5 | Lockfiles | Commit `uv.lock` and `app/frontend/pnpm-lock.yaml` in the T01 PR. |
| 6 | Makefile | None at T01; raw shell commands documented in README. |
| 7 | README update | Add "Developer setup" section to repo-root `README.md`; no separate engineering doc. |

No open `NEEDS CLARIFICATION` markers remain. Proceed to `data-model.md`, `contracts/dev-commands.md`, and `quickstart.md`.
