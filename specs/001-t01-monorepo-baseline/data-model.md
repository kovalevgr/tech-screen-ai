# Phase 1 Data Model — T01 Monorepo Layout & Tooling Baseline

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Date**: 2026-04-23

T01 introduces no application-level data (no tables, no files storing candidate/session state). The "entities" below are the spec's `## Key Entities` re-expressed as a concrete, reviewer-checkable list. Each row maps an entity to the file(s) that represent it in the PR.

---

## Entities

### 1. Canonical folder

| Field | Value |
|-------|-------|
| Definition | A top-level directory named in `CLAUDE.md` "Where to find things", the implementation plan, or an ADR, whose presence is a precondition for a later task. |
| Instances created by T01 | `app/backend/`, `app/frontend/`, `alembic/`, `configs/`, `infra/terraform/`, `.github/workflows/`, `evals/` |
| Instances pre-existing (untouched) | `adr/`, `docs/`, `prompts/`, `infra/`, `.claude/`, `.specify/` |
| Marker | `.gitkeep` file inside the folder when otherwise empty (per Clarifications Q1). Contains no metadata — presence-only. |
| Index | Single row in `docs/engineering/directory-map.md` per canonical folder, with columns: folder path, owner task (T-id), purpose, populated-by. |
| Validation | After T01 merges, every folder named in `CLAUDE.md` "Where to find things" exists and is git-tracked. `docs/engineering/directory-map.md` has one row per folder. |
| State transitions | `not-created` → `created-empty` (T01) → `populated` (owner task). Once populated, the `.gitkeep` is removed by the owner task. |

### 2. Tooling configuration file

| Field | Value |
|-------|-------|
| Definition | A single source-of-truth file that configures one toolchain. Configurations do not duplicate across files; each tool reads one file. |
| Instances (new in T01) | `pyproject.toml` (ruff + mypy + uv dep groups + `requires-python`), `app/frontend/package.json` (deps + engines + scripts), `app/frontend/tsconfig.json`, `app/frontend/.eslintrc.cjs`, `app/frontend/.prettierrc.json`, `app/frontend/.gitignore` |
| Instances (pre-existing, untouched) | `.pre-commit-config.yaml` (guardrail hooks), repo-root `.gitignore`, `.dockerignore`, `.env.example`, `Dockerfile`, `Dockerfile.frontend`, `Dockerfile.vertex-mock`, `docker-compose.yml`, `docker-compose.test.yml`. |
| Validation | Each new config file is readable by its tool without further flags; each tool's check command exits 0 on the T01-clean tree (see SC-002 – SC-004). |
| Constraints | (a) Docker-parity: lockfiles committed must match `Dockerfile` / `Dockerfile.frontend` expectations (`uv.lock` at repo root, `app/frontend/pnpm-lock.yaml`). (b) Version-pin: `pyproject.toml requires-python = ">=3.12,<3.13"`, `package.json engines.node = "20.x"`, `engines.pnpm = "9.x"`. (c) No secret values anywhere — SC-007 guardrail. |

### 3. Guardrail hook

| Field | Value |
|-------|-------|
| Definition | A check declared in `.pre-commit-config.yaml` that runs before every commit and again in CI. |
| Instances | Declared at HEAD in `.pre-commit-config.yaml` — T01 does not add, remove, or modify any. |
| Touch points | T01 activates the hooks via `pre-commit install` (run by the contributor during bootstrap) and ensures the post-T01 tree passes `pre-commit run --all-files` cleanly. |
| Validation | `pre-commit run --all-files` exits 0 on the T01 tree (SC-002). No T01-introduced file triggers a secret, key, merge-conflict, or large-file warning. |
| State transitions | N/A — guardrails are stateless checks. |

---

## Relationships

```text
Canonical folder ──indexed-by──► docs/engineering/directory-map.md
                  └─marked-by──► .gitkeep (when empty)

Tooling configuration file ──referenced-by──► Guardrail hook (yaml/json/toml validity hooks)
                             └─consumed-by──► Dockerfile / Dockerfile.frontend (lockfiles, manifests)
                             └─invoked-by──► contracts/dev-commands.md (the 3 documented commands)

Guardrail hook ──declared-in──► .pre-commit-config.yaml (unchanged by T01)
                └─runs-against──► Every file in the tree, including T01's new files
```

## Validation rules (collected)

1. Every canonical folder in `CLAUDE.md` "Where to find things" exists on HEAD after T01 merges.
2. Every folder in the project tree that lacks content has a `.gitkeep` (so git tracks it) AND a row in `docs/engineering/directory-map.md`.
3. `pre-commit run --all-files` exits 0 on the T01-clean tree.
4. `uv sync --dev` installs the dev dep group declared in `pyproject.toml` without errors, and `uv run ruff check app/backend && uv run mypy app/backend` exits 0.
5. `pnpm install --frozen-lockfile` inside `app/frontend/` installs the declared dev deps without errors, and `pnpm --dir app/frontend lint` exits 0, and `pnpm --dir app/frontend tsc --noEmit` exits 0.
6. No new T01 file contains a secret value, a credential, or PII (SC-007; enforced by `gitleaks` and `detect-secrets` hooks already in `.pre-commit-config.yaml`).
7. Zero pre-existing files listed in FR-008 are modified (diff check).

No other data-model concerns — T01 has no domain entities, no state, no persistence.
