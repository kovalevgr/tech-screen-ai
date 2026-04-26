# TechScreen

Internal AI-powered technical screening system.

TechScreen conducts structured technical interviews with candidates, evaluates answers against a calibrated competency rubric, and produces reviewer-auditable reports. It augments human interviewers rather than replacing them: reviewers can override any model decision, and those overrides become training signal for the next release.

> **Status:** MVP planning phase. No production code yet. See `docs/specs/mvp-scope.docx` for the current scope.

## Developer setup

Once per machine, install the prerequisites:

- **Python 3.12** — `brew install python@3.12` on macOS.
- **Node 20 LTS** — install via your Node version manager of choice (nvm, asdf, mise). The image and CI use Node 20; your local can be newer but you will see an engine warning.
- **pnpm 9** via corepack (ships with Node) — `corepack enable pnpm && corepack prepare pnpm@9.12.0 --activate`.
- **uv** (Python dep manager) — `brew install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- **pre-commit ≥ 3.7.0** — `pipx install pre-commit` or `brew install pre-commit`.

Once per clone, bootstrap the two toolchains and activate the guardrail hooks:

```bash
# Python dev deps (ruff, mypy) into .venv
uv sync --dev

# Frontend dev deps (eslint, prettier, typescript, @types/node) into app/frontend/node_modules
pnpm --dir app/frontend install --frozen-lockfile

# Git hooks: pre-commit + commit-msg
pre-commit install
pre-commit install --hook-type commit-msg
```

### Check commands

Three commands validate the repo before you push. All three are also what CI runs; all three exit 0 on a clean tree. See [`specs/001-t01-monorepo-baseline/contracts/dev-commands.md`](./specs/001-t01-monorepo-baseline/contracts/dev-commands.md) for the stable contract.

```bash
# Guardrails (secrets, YAML/JSON/TOML, merge-conflict, project-local hooks)
pre-commit run --all-files

# Backend — ruff + mypy over app/backend/
uv run ruff check app/backend && uv run mypy app/backend

# Frontend — ESLint + tsc --noEmit over app/frontend/
pnpm --dir app/frontend lint
```

Run these from the repo root. Internet access to PyPI and the pnpm/npm registry is required for the one-time bootstrap; afterwards the check commands are fully local.

### Backend dev loop (Docker-first)

Constitution §7 (Docker parity dev → CI → prod) is non-negotiable. **All backend run/test/regen workflows happen inside the same multi-stage image that CI and production use.** No native `uv run` for the canonical loop — Docker Desktop (or any Docker Engine) is the only contributor prerequisite for this layer.

The Dockerfile has three stages: `builder` (deps + project), `dev` (builder + dev deps; default for local + CI), `runtime` (lean image deployed to Cloud Run). `docker-compose.yml` builds `dev`; `docker-compose.test.yml` builds `dev` and runs pytest; only Cloud Run gets `runtime`.

The backend skeleton (T02) ships a FastAPI app with `GET /health`, a structlog-based PII-safe logger, and a committed OpenAPI contract. See [`specs/005-t02-fastapi-skeleton/contracts/backend-contract.md`](./specs/005-t02-fastapi-skeleton/contracts/backend-contract.md) for the stable interface.

```bash
# Run the backend (port 8000, hot reload via bind-mount).
docker compose up backend
#   …or rebuild then run if pyproject.toml or uv.lock changed:
docker compose up --build backend

# Run the backend test suite (health smoke, PII redaction × 4, OpenAPI drift).
docker compose -f docker-compose.test.yml run --rm --build backend \
    pytest app/backend/tests/

# Regenerate the committed OpenAPI contract after changing routes or schemas.
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi
#   …or detect drift without overwriting (exits 1 on mismatch).
docker compose -f docker-compose.test.yml run --rm backend \
    python -m app.backend.generate_openapi --check

# Lint + type-check inside the container (ruff + mypy --strict).
docker compose -f docker-compose.test.yml run --rm backend \
    sh -c "ruff check app/backend && mypy app/backend"
```

Profiles let later tasks add Postgres / Vertex mock / Next.js without forcing them on T02 today: `docker compose --profile db up` (T05+), `--profile llm` (T04+), `--profile web` (T03+), `--profile full` (everything; the Tier-1 gate / T11 smoke).

The OpenAPI drift check also runs as part of the pytest suite — you will see a test failure if the committed `app/backend/openapi.yaml` disagrees with the live FastAPI app, with a unified-diff head in the failure message.

> **Native `uv run` is intentionally undocumented.** Editor / IDE integrations (mypy daemon, ruff in your editor) may still use the host-side `uv sync --dev` venv — that's a tooling convenience, not a documented dev path. The canonical commands above are what CI runs and what every PR description references.

### Frontend dev loop (Docker-first)

Constitution §7 (Docker parity dev → CI → prod) is non-negotiable. **All frontend run/test/regen workflows happen inside the same multi-stage image that CI and production use.** No native `pnpm --dir app/frontend …` for the canonical loop — Docker Desktop (or any Docker Engine) is the only contributor prerequisite for this layer.

`Dockerfile.frontend` has five stages: `base` (Node 20 + pnpm 9 via corepack), `deps` (`pnpm install --frozen-lockfile`), `dev` (full source + dev deps; default for local + CI), `build` (`pnpm build`), `runtime` (lean image deployed to Cloud Run). `docker-compose.yml` builds `dev` for `--profile web`; `docker-compose.test.yml` builds `dev` and runs Jest, lint, and the token-drift check; only Cloud Run gets `runtime` (T06+).

The frontend skeleton (T03) ships the admin shell chrome, a token generator with drift detection, the nine shadcn/ui primitives, and a visual-discipline guardrail. See [`specs/006-t03-nextjs-skeleton/contracts/frontend-contract.md`](./specs/006-t03-nextjs-skeleton/contracts/frontend-contract.md) for the stable interface.

```bash
# Run the frontend (port 3000, hot reload via bind-mount).
docker compose --profile web up -d frontend && open http://127.0.0.1:3000
#   …or rebuild then run if package.json or pnpm-lock.yaml changed:
docker compose --profile web up --build -d frontend
```

```bash
# Run the frontend test suite (Jest + RTL — admin-shell smoke + token drift).
docker compose -f docker-compose.test.yml run --rm frontend pnpm test
```

```bash
# Regenerate the committed design tokens after editing docs/design/tokens/*.md.
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:generate
#   …or detect drift without overwriting (exits 1 on mismatch).
docker compose -f docker-compose.test.yml run --rm frontend pnpm tokens:check
```

The `tokens-drift` pre-commit hook calls `pnpm tokens:check` automatically before every `git commit`; the `visual-discipline` pre-commit hook scans `app/frontend/src/` for raw hex outside the token file and for `dark:` Tailwind variants. Both fail the commit on any drift; both are also part of `pre-commit run --all-files`.

> **Native `pnpm --dir app/frontend …` is intentionally undocumented as the canonical path** — Docker is canonical (constitution §7). Editor / IDE integrations (TypeScript server, ESLint in your editor) may still use the host-side `pnpm --dir app/frontend install` `node_modules` — that's a tooling convenience, not a documented dev path.

#### Notes on host vs container Node, and supply-chain audit

- **Host Node**: `engines.node` is set to `>=20.0.0`. The canonical container always runs Node 20 LTS; the host can be on 20 or 22 (LTS lines). pnpm install warnings about "wanted" mismatches are expected on Node 22 hosts and harmless — production parity is enforced by the container image.
- **Supply-chain audit**: `pnpm --dir app/frontend audit --audit-level=high` exits 0 on the post-T03 lockfile (no HIGH or CRITICAL CVEs). Two known low-impact advisories at T03 close, both deferred:
  - `postcss@8.4.31` (MODERATE — XSS via unescaped `</style>` in CSS Stringify) — bundled inside `next@15.5.x`, not our direct dep. Realisation requires processing untrusted CSS, which T03 never does. Resolves when Next.js bumps its bundled postcss in a patch release.
  - `@tootallnate/once@2.0.0` (LOW — Incorrect Control Flow Scoping) — transitive 4 levels deep under `jest-environment-jsdom`, dev/test toolchain only; the production `runtime` Dockerfile stage never executes it.
- **shadcn CLI**: pinned at major `pnpm dlx shadcn@2 add …` (NOT `@latest`) so future shadcn 3.x template changes do not silently land. Bumping the major is its own ADR-discussed task.

## What this repository is for

- Source of truth for architecture, rubrics, prompts, infra, and tests
- Entry point for AI-assisted development via [Claude Code](https://docs.claude.com/en/docs/claude-code) (see [`CLAUDE.md`](./CLAUDE.md))
- Ground truth for every decision made about the product — see [`adr/`](./adr/) and [`.specify/memory/constitution.md`](./.specify/memory/constitution.md)

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Frontend:** Next.js (App Router), shadcn/ui, Tailwind CSS, lucide-react
- **Database:** PostgreSQL 17 with `pgvector`
- **LLMs:** Google Vertex AI — Gemini 2.5 Flash (Interviewer, Assessor) and Gemini 2.5 Pro (Pre-Interview Planner)
- **Infra:** Google Cloud Run, Cloud SQL, Secret Manager, Artifact Registry
- **IaC:** Terraform, bootstrapped via [`infra/bootstrap.sh`](./infra/bootstrap.sh)
- **CI/CD:** GitHub Actions with Workload Identity Federation (no JSON keys)

Everything in this repository runs in Docker. Local dev, CI, and production use the same multi-stage images. See principle §7 of the constitution.

## Quickstart (local, Docker-first)

> **Status: partial today.** `app/backend/` and `app/frontend/` are scaffolded in Tier 1 (tasks T02 / T03 of the implementation plan). Until those land, only `postgres` and `vertex-mock` come up cleanly; `docker compose up` of `backend` / `frontend` will fail on missing Dockerfile targets. Treat the steps below as the target dev loop.

Prerequisites: Docker Engine with Compose v2 (Docker Desktop works too) and a populated `.env` file (copy from `.env.example`). No `gcloud` needed on day one — the dev stack uses the in-repo `vertex-mock` service.

```bash
# 1. Clone and copy env template
git clone git@github.com:<github-user>/techscreen.git
cd techscreen
cp .env.example .env

# 2. Fill the two dev-only signing secrets in .env:
openssl rand -hex 32   # paste as MAGIC_LINK_SIGNING_KEY=
openssl rand -hex 32   # paste as SESSION_COOKIE_SECRET=
# DATABASE_URL is overridden by docker-compose.yml — leave it empty in .env.
# SENDGRID_API_KEY, GCP_PROJECT, CALIBRATION_DATASET_KEY stay empty for mock-backed dev.

# 3. Start the stack
docker compose up --build

# 4. Open in your browser:
#    frontend:     http://localhost:3000
#    backend API:  http://localhost:8000/health
#    vertex mock:  http://localhost:8080/healthz
```

Dev hot-reload (backend + frontend) is wired via volume mounts. To run tests:

```bash
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

To point dev at real Vertex (rare — most work uses the mock): set `LLM_BACKEND=vertex` in `.env`, authenticate with `gcloud auth application-default login`, and ensure your account has `roles/aiplatform.user` on the TechScreen GCP project.

## Repository layout

```
.
├── README.md                        # You are here.
├── CLAUDE.md                        # Entry point for Claude Code / AI assistants.
├── .specify/memory/constitution.md  # Project invariants. Non-negotiable.
├── adr/                             # Architecture Decision Records (Michael Nygard format).
├── docs/
│   ├── specs/                       # Canonical .docx specs (architecture, data-model, agents, methodology, mvp-scope, roadmap).
│   ├── engineering/                 # Agent-readable operational refs (.md): conventions, playbooks, glossary, implementation plan, workflow.
│   ├── design/                      # UI/UX design system, per-screen specs.
│   └── kickoff/                     # One-time launch artefacts (dev briefings).
├── prompts/                         # Agent prompt templates (Interviewer, Assessor, Planner).
├── configs/                         # Rubrics, position templates, feature flag defaults.
├── app/
│   ├── backend/                     # FastAPI service.
│   └── frontend/                    # Next.js service.
├── alembic/                         # Database migrations.
├── infra/
│   ├── bootstrap.sh                 # One-time GCP bootstrap.
│   └── terraform/                   # All managed infra.
├── .claude/
│   ├── agents/                      # Specialised Claude Code sub-agents.
│   └── skills/                      # Reusable Claude Code skills (project-specific + Spec Kit `speckit-*`).
├── docker-compose.yml               # Dev stack.
├── docker-compose.test.yml          # Test stack.
└── .github/workflows/               # CI/CD.
```

## Key documents

Start here before making a non-trivial change.

| Document                                                                               | Purpose                                                     |
| -------------------------------------------------------------------------------------- | ----------------------------------------------------------- |
| [`.specify/memory/constitution.md`](./.specify/memory/constitution.md)                 | Project invariants. Never violate.                          |
| [`CLAUDE.md`](./CLAUDE.md)                                                             | How to work in this repo with AI assistance.                |
| [`docs/specs/mvp-scope.docx`](./docs/specs/mvp-scope.docx)                             | What ships in the MVP.                                      |
| [`docs/specs/architecture.docx`](./docs/specs/architecture.docx)                       | System architecture, data flow, component diagram.          |
| [`docs/specs/data-model.docx`](./docs/specs/data-model.docx)                           | Database schema, key invariants, table-by-table reference.  |
| [`docs/specs/agents.docx`](./docs/specs/agents.docx)                                   | Interviewer / Assessor / Planner agent contracts.           |
| [`docs/specs/assessment-methodology.docx`](./docs/specs/assessment-methodology.docx)   | Rubric, scoring, correctness approach, calibration loop.    |
| [`docs/specs/roadmap.docx`](./docs/specs/roadmap.docx)                                 | Horizon-1/2/3 plan and deferred features.                   |
| [`docs/engineering/implementation-plan.md`](./docs/engineering/implementation-plan.md) | 12-week MVP task breakdown (59 tasks).                      |
| [`docs/design/README.md`](./docs/design/README.md)                                     | Design system and per-screen specs.                         |
| [`adr/`](./adr/)                                                                       | Every architectural decision with context and consequences. |

## How work happens here

TechScreen uses [GitHub Spec Kit](https://github.com/github/spec-kit) for spec-driven development. Every non-trivial feature progresses through:

1. **Specify** — a natural-language description of what changes and why.
2. **Clarify** (optional) — iterate on the spec when the ask is still ambiguous.
3. **Plan** — a layered implementation plan with explicit sub-agent assignments.
4. **Tasks** — a concrete task list, each linked to a layer and agent.
5. **Implement** — the orchestrator executes tasks, fanning out to sub-agents only where the plan declares `parallel: true`.

Trivial changes (typos, dependency bumps, formatting) skip the flow — see constitution §17.

### Using Spec Kit from Claude Code

Spec Kit `0.7.4` integrates with Claude Code as **skills**, not slash commands. From any Claude Code session in this repo, invoke them through the skill picker:

| Skill                                    | When to use                                                            |
| ---------------------------------------- | ---------------------------------------------------------------------- |
| `speckit-constitution`                   | Edit `.specify/memory/constitution.md` (rare — always ADR-gated).      |
| `speckit-specify <description>`          | Start a new feature. Produces `.specify/specs/<slug>/spec.md`.         |
| `speckit-clarify`                        | Iterate on an ambiguous spec before planning.                          |
| `speckit-plan`                           | Turn the spec into `plan.md` with `agent:` / `parallel:` / `depends_on:` fields. |
| `speckit-tasks`                          | Break the plan into an ordered `tasks.md`.                             |
| `speckit-analyze`                        | Cross-check that `spec.md`, `plan.md`, `tasks.md` agree.               |
| `speckit-checklist`                      | Generate a pre-merge / pre-implement checklist.                        |
| `speckit-implement`                      | Execute tasks marked ready. Fan-out respects `parallel: true` only.    |
| `speckit-taskstoissues`                  | Export `tasks.md` to GitHub issues (when the team wants a board view). |

Feature artefacts land under `.specify/specs/<slug>/` — `spec.md`, `plan.md`, `tasks.md`, `checklist.md`. Commit the full folder with the feature PR.

Five `speckit-git-*` helpers are also installed but `auto_commit` is **off** by default (see `.specify/extensions/git/git-config.yml`). We commit manually so CODEOWNERS, message style, and pre-commit hooks stay in our control. Do not flip `auto_commit` on without a PR that explains why.

For the full flow — sub-agent assignments, `reviewer` gating, parallel fan-out rules — see [`CLAUDE.md`](./CLAUDE.md) and [`docs/engineering/multi-agent-workflow.md`](./docs/engineering/multi-agent-workflow.md).

## Deploy

> **Status: planned.** The commands below are the designed deploy shape; they land in task T37 of the implementation plan. Until then, deploys happen via manual `gcloud run deploy` on a branch PR-reviewed by `infra-engineer` + `reviewer`.

The target workflow — a `/deploy` command (slash-command or `scripts/deploy.sh`, to be decided in T37) that:

1. Verifies the branch is green and up-to-date with `main`.
2. Builds backend and frontend images, pushes to Artifact Registry.
3. Runs the Alembic migration in `--sql` dry-run mode and posts the generated SQL for approval.
4. Creates a new Cloud Run revision at **0% traffic**.
5. Runs smoke tests against the preview revision URL.
6. Waits for explicit traffic ramp: `/promote 10`, `/promote 50`, `/promote 100`.

Rollback: one command — `/rollback` — shifts traffic back to the previous Cloud Run revision in under a minute.

There is no staging environment — see constitution §8. Full runbook lives in [`docs/engineering/deploy-playbook.md`](./docs/engineering/deploy-playbook.md).


## Contact

Project lead: Ihor (kovalevgr@gmail.com). Additional maintainers will be added as the team grows.
