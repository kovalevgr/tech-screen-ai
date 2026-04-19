# TechScreen

Internal AI-powered technical screening system for N-iX.

TechScreen conducts structured technical interviews with candidates, evaluates answers against a calibrated competency rubric, and produces reviewer-auditable reports. It augments human interviewers rather than replacing them: reviewers can override any model decision, and those overrides become training signal for the next release.

> **Status:** MVP planning phase. No production code yet. See `docs/mvp-scope.docx` for the current scope.

## What this repository is for

- Source of truth for architecture, rubrics, prompts, infra, and tests
- Entry point for AI-assisted development via [Claude Code](https://docs.claude.com/en/docs/claude-code) (see [`CLAUDE.md`](./CLAUDE.md))
- Ground truth for every decision made about the product — see [`adr/`](./adr/) and [`.specify/memory/constitution.md`](./.specify/memory/constitution.md)

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy, Alembic
- **Frontend:** Next.js (App Router), shadcn/ui, Tailwind CSS, lucide-react
- **Database:** PostgreSQL 15 with `pgvector`
- **LLMs:** Google Vertex AI — Gemini 2.5 Flash (Interviewer, Assessor) and Gemini 2.5 Pro (Pre-Interview Planner)
- **Infra:** Google Cloud Run, Cloud SQL, Secret Manager, Artifact Registry
- **IaC:** Terraform, bootstrapped via [`infra/bootstrap.sh`](./infra/bootstrap.sh)
- **CI/CD:** GitHub Actions with Workload Identity Federation (no JSON keys)

Everything in this repository runs in Docker. Local dev, CI, and production use the same multi-stage images. See principle §7 of the constitution.

## Quickstart (local, Docker-first)

> Prerequisites: Docker Desktop, a `gcloud` login with access to the TechScreen GCP project, and a populated `.env` file (copy from `.env.example`).

```bash
# 1. Clone and copy env template
git clone git@github.com:<github-user>/techscreen.git
cd techscreen
cp .env.example .env
# edit .env with your local values

# 2. Start the full stack
docker compose up --build

# 3. Open the frontend
open http://localhost:3000
```

Dev hot-reload (backend + frontend) is wired via volume mounts. To run tests:

```bash
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

## Repository layout

```
.
├── README.md                        # You are here.
├── CLAUDE.md                        # Entry point for Claude Code / AI assistants.
├── .specify/memory/constitution.md  # Project invariants. Non-negotiable.
├── adr/                             # Architecture Decision Records (Michael Nygard format).
├── docs/                            # Shared design docs (architecture, data model, roadmap, agents, etc.).
│   ├── design/                      # UI/UX design system, per-screen specs.
│   └── diagrams/                    # Source `.dot` files and rendered `.png` diagrams.
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
│   └── skills/                      # Reusable Claude Code skills.
├── docker-compose.yml               # Dev stack.
├── docker-compose.test.yml          # Test stack.
└── .github/workflows/               # CI/CD.
```

## Key documents

Start here before making a non-trivial change.

| Document                                                                 | Purpose                                                     |
| ------------------------------------------------------------------------ | ----------------------------------------------------------- |
| [`.specify/memory/constitution.md`](./.specify/memory/constitution.md)   | Project invariants. Never violate.                          |
| [`CLAUDE.md`](./CLAUDE.md)                                               | How to work in this repo with AI assistance.                |
| [`docs/mvp-scope.docx`](./docs/mvp-scope.docx)                           | What ships in the MVP.                                      |
| [`docs/architecture.docx`](./docs/architecture.docx)                     | System architecture, data flow, component diagram.          |
| [`docs/data-model.docx`](./docs/data-model.docx)                         | Database schema, key invariants, table-by-table reference.  |
| [`docs/agents.docx`](./docs/agents.docx)                                 | Interviewer / Assessor / Planner agent contracts.           |
| [`docs/assessment-methodology.docx`](./docs/assessment-methodology.docx) | Rubric, scoring, correctness approach, calibration loop.    |
| [`docs/roadmap.docx`](./docs/roadmap.docx)                               | Horizon-1/2/3 plan and deferred features.                   |
| [`docs/design/README.md`](./docs/design/README.md)                       | Design system and per-screen specs.                         |
| [`adr/`](./adr/)                                                         | Every architectural decision with context and consequences. |

## How work happens here

TechScreen uses [GitHub Spec Kit](https://github.com/github/spec-kit) for spec-driven development. Every non-trivial feature progresses through:

1. **`/specify`** — a natural-language description of what changes and why.
2. **`/plan`** — a layered implementation plan with explicit sub-agent assignments.
3. **`/tasks`** — a concrete task list, each linked to a layer and agent.
4. **`/implement`** — the orchestrator executes tasks, fanning out to sub-agents only where the plan declares `parallel: true`.

See [`CLAUDE.md`](./CLAUDE.md) for how to drive this from Claude Code.

## Deploy

Production deploys happen via the `/deploy` slash command, which:

1. Verifies the branch is green and up-to-date with `main`.
2. Builds backend and frontend images, pushes to Artifact Registry.
3. Runs the Alembic migration in `--sql` dry-run mode and posts the generated SQL for approval.
4. Creates a new Cloud Run revision at **0% traffic**.
5. Runs smoke tests against the preview revision URL.
6. Waits for explicit traffic ramp via `/promote 10`, `/promote 50`, `/promote 100`.

Rollback is one command: `/rollback` shifts traffic back to the previous revision in under a minute.

There is no staging environment — see constitution §8.

## Licensing and ownership

Internal N-iX project. Not for external distribution.

## Contact

Project lead: Ihor (humer355@gmail.com). Additional maintainers will be added as the team grows.
