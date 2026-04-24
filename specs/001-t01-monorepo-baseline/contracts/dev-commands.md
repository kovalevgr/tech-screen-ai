# Dev Commands Contract — T01 Monorepo Layout & Tooling Baseline

**Feature**: [../spec.md](../spec.md) · **Plan**: [../plan.md](../plan.md)
**Stable from**: T01 merge onwards.
**Consumers**: T02 (FastAPI skeleton), T03 (Next.js skeleton), T09 (Docker stacks), T10 (CI pipeline), every future backend/frontend PR, `reviewer` sub-agent.

This is the T01 interface contract. Three commands, stable names, stable exit semantics. A later task may add commands; it may **not** rename or remove these without an ADR. T09 and T10 rely on these exact invocations inside docker-compose and GitHub Actions respectively.

---

## Command 1 — Backend check

```bash
uv run ruff check app/backend && uv run mypy app/backend
```

| Field | Value |
|-------|-------|
| Purpose | Lint + type-check every Python file under `app/backend/`. |
| Exit 0 | No lint or type errors. Empty target (no `.py` files) is a valid 0. |
| Exit non-zero | At least one ruff or mypy diagnostic. `mypy` errors dominate ruff errors in CI reporting. |
| Side effects | None. No files are written or modified. |
| Consumers | Backend-engineer sub-agent (every backend PR), `reviewer` sub-agent gate, T10 CI step. |
| Out of scope | Code formatting (ruff-format not run); tests (pytest lives in T02's scripts). |

## Command 2 — Frontend check

```bash
pnpm --dir app/frontend lint
```

where `app/frontend/package.json` declares:

```jsonc
{
  "scripts": {
    "lint": "eslint . --ext .ts,.tsx,.js,.jsx --max-warnings 0 --no-error-on-unmatched-pattern && tsc --noEmit"
  }
}
```

| Field | Value |
|-------|-------|
| Purpose | ESLint (incl. `@typescript-eslint`) + `tsc --noEmit` over every TS/JS file under `app/frontend/`. |
| Exit 0 | No ESLint errors **and** no TypeScript diagnostics. Empty target (no source files) is a valid 0 thanks to `--no-error-on-unmatched-pattern` and `tsc`'s empty-match behaviour. |
| Exit non-zero | At least one ESLint error (warnings escalated via `--max-warnings 0`) or at least one TS diagnostic. |
| Side effects | None. `tsc --noEmit` does not write files. |
| Consumers | Frontend-engineer sub-agent (every frontend PR), `reviewer` sub-agent gate, T10 CI step. |
| Out of scope | Prettier formatting (run separately when needed); Next.js build (T09's docker build owns that). |

## Command 3 — Guardrails (pre-commit)

```bash
pre-commit run --all-files
```

| Field | Value |
|-------|-------|
| Purpose | Run every hook in `.pre-commit-config.yaml` against the full tree. Guardrails include: merge-conflict check, YAML/JSON/TOML validity, private-key detection, `gitleaks`, `detect-secrets`, plus project-local hooks (`forbid-env-values`, `no-direct-vertex-import`, visual-discipline for frontend). |
| Exit 0 | No hook reports a finding. |
| Exit non-zero | At least one hook failed. Output points at the offending file + line. |
| Side effects | None — pre-commit config's header comment forbids mutating hooks, and T01 must not introduce any. |
| Consumers | Every contributor before commit; T10 CI step runs the same command in Docker. |
| Out of scope | Running ruff/mypy/eslint/tsc — those live in commands 1 and 2 (kept out of pre-commit to avoid duplicate runs during CI). |

---

## Stability guarantees

- The three invocations above are the committed contract. Breaking them (rename, remove, change exit semantics) requires an ADR and a plan update referencing this contract file.
- Additional helper commands MAY be added later (e.g. `pnpm --dir app/frontend format`, `pytest`) without touching this contract.
- The exact content of tool configurations (ruff rule set, ESLint extends list, pre-commit hook list) MAY evolve in later tasks as long as the three commands still satisfy their exit semantics on the then-current tree.

## Invocation preconditions

1. Python 3.12 installed; `uv` installed (prerequisite, see README).
2. Node 20 LTS installed; pnpm 9.x activated via corepack.
3. `uv sync --dev` has run at least once (creates `.venv/` with dev deps).
4. `pnpm install --frozen-lockfile` has run inside `app/frontend/` at least once (creates `node_modules`).
5. `pre-commit install` has run at least once (installs git hooks).

Steps 1–5 are documented in the README "Developer setup" section added by T01.
