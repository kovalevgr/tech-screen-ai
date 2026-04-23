# Quickstart — Validating the T01 PR

**Feature**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Contract**: [contracts/dev-commands.md](./contracts/dev-commands.md)
**Audience**: Human reviewer or `reviewer` sub-agent validating the T01 PR before merge.
**Target time**: under 5 minutes end-to-end.

---

## Prerequisites (one-time per machine)

- Python 3.12 available on `PATH`.
- Node 20 LTS available on `PATH`.
- `corepack` enabled (`corepack enable`) so pnpm 9 activates automatically.
- `uv` installed (`curl -LsSf https://astral.sh/uv/install.sh | sh` or Homebrew `brew install uv`).
- `pre-commit` ≥ 3.7.0 (`pipx install pre-commit` or `brew install pre-commit`).

You don't need GCP credentials, Vertex access, or Postgres for T01 — it's tooling only.

---

## Step 1 — Check out the PR branch

```bash
git fetch origin
git switch 001-t01-monorepo-baseline
git status --short   # expect: clean tree
```

## Step 2 — Bootstrap the two toolchains (one-time, ~2 minutes)

```bash
# Python: install dev deps into .venv
uv sync --dev

# Node: install dev deps into app/frontend/node_modules
pnpm --dir app/frontend install --frozen-lockfile

# Activate pre-commit git hooks
pre-commit install
pre-commit install --hook-type commit-msg
```

## Step 3 — Run the three contracted check commands

```bash
# Guardrails (merge-conflict / YAML / JSON / secrets / large files / project-local hooks)
pre-commit run --all-files

# Backend lint + type-check (empty target must still exit 0)
uv run ruff check app/backend && uv run mypy app/backend

# Frontend lint + type-check (empty target must still exit 0)
pnpm --dir app/frontend lint
```

**Expected**: all three exit with status 0. If any command fails, the PR is not ready to merge — annotate the failure in the review.

## Step 4 — Spot-check the structural claims

```bash
# Every canonical folder named in CLAUDE.md "Where to find things" must exist.
for d in app/backend app/frontend alembic configs prompts infra/terraform docs .github/workflows evals adr .claude .specify; do
  [ -d "$d" ] || echo "MISSING: $d"
done

# Every otherwise-empty canonical folder carries a .gitkeep.
find app/backend alembic configs evals infra/terraform .github/workflows -type d -empty -print

# Central index doc exists.
test -f docs/engineering/directory-map.md && echo "map: present"

# Lockfiles committed.
test -f uv.lock && echo "uv.lock: present"
test -f app/frontend/pnpm-lock.yaml && echo "pnpm-lock.yaml: present"
```

**Expected**: no `MISSING:` lines; no output from `find … -type d -empty` (every empty folder should have `.gitkeep` so it's not "empty" to find's `-empty` predicate — wait, it is, because `.gitkeep` is a hidden-ish file but `-empty` counts it as a file, so the folder is NOT empty to `find`. Adjust: if `find` prints any directory here, the `.gitkeep` is missing); both lockfiles present; `map: present`.

## Step 5 — Verify no pre-existing file was reshaped (FR-008, FR-009)

```bash
git diff --stat origin/main..HEAD -- \
  CLAUDE.md README.md \
  .pre-commit-config.yaml .env.example .gitignore .dockerignore \
  Dockerfile Dockerfile.frontend Dockerfile.vertex-mock \
  docker-compose.yml docker-compose.test.yml \
  adr/ prompts/ docs/specs/ docs/design/ docs/kickoff/ \
  .claude/agents/ .claude/skills/vertex-call/ \
  .claude/skills/agent-prompt-edit/ .claude/skills/rubric-yaml/ \
  .claude/skills/calibration-run/ \
  .specify/memory/ .specify/templates/
```

**Expected**: only `README.md` shows changes in the stat (new "Developer setup" section added, per FR-013 and research decision §7). Every other line shows 0 insertions / 0 deletions.

If any other file appears with changes, investigate before approving.

---

## Acceptance summary

| Check | Tied to | Passes when |
|-------|---------|-------------|
| Step 3 command 1 (pre-commit) | SC-002, guardrail hooks | Exit 0 in under 60 s. |
| Step 3 command 2 (backend) | SC-003, FR-002 | Exit 0 in under 15 s. |
| Step 3 command 3 (frontend) | SC-004, FR-003 | Exit 0 in under 30 s. |
| Step 4 folder + lockfile check | FR-001, FR-010, Clarifications Q1 | No missing folders or missing `.gitkeep`s; both lockfiles present. |
| Step 5 diff audit | FR-008, FR-009, SC-005 | Only `README.md` shows edits among protected files. |

If every row is ✅, the PR satisfies T01 acceptance and can be approved.
