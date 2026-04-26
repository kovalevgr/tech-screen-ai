# Repository Directory Map

**Version**: 1.0 · **Created**: 2026-04-24 · **Owner task**: T01 (`specs/001-t01-monorepo-baseline/`)

This is the single source of truth for which canonical folder belongs to which owner task and why it exists. Sub-agents opening an empty folder consult this file to learn its purpose. Whenever a task introduces a new top-level folder, it adds a row here in the same PR; when a task deletes a folder it removes the row.

The tree mirrors [CLAUDE.md](../../CLAUDE.md) "Where to find things". Do not remove a folder without deprecating the row first.

---

## Canonical folders

| Path | Owner task | Purpose | Populated by |
|------|-----------|---------|--------------|
| `.claude/agents/` | *(pre-existing)* | Sub-agent definitions (`backend-engineer`, `frontend-engineer`, `infra-engineer`, `prompt-engineer`, `reviewer`). | Pre-existing (curated by hand). |
| `.claude/skills/` | *(pre-existing)* | Reusable Claude Code skills (`vertex-call`, `agent-prompt-edit`, `rubric-yaml`, `calibration-run`) plus installed Spec Kit skills. | Pre-existing + Spec Kit scaffolding (T00). |
| `.github/workflows/` | T10 | GitHub Actions CI/CD pipelines (lint, test, deploy, rollback, migration gate). | T10 (CI pipeline), T06a (deploy/rollback), T05a (feature-flag sync). Currently empty (`.gitkeep`). |
| `.specify/` | T00 | Spec Kit metadata — templates, scripts, extensions, constitution, per-feature state. | T00 (Spec Kit init). Do not edit `.specify/memory/constitution.md` outside of a constitution-edit PR. |
| `adr/` | *(pre-existing)* | Architectural Decision Records (numbered `001..NNN`). Read-only except when adding or superseding a decision. | Pre-existing (21 ADRs authored pre-T00). |
| `alembic/` | T05 | Database migrations. `alembic.ini` at repo root; numbered migration files under `alembic/versions/`. | T05 (baseline) and any later task that ships schema changes. Currently empty (`.gitkeep`). |
| `app/backend/` | T02 | FastAPI service — `main.py`, routers, services, DB models, LLM adapter. Python 3.12 only. | T02 (skeleton), T04 (Vertex client), T05 (models), T17+ (agents wiring). T01 adds an empty `__init__.py` as a package marker so `mypy` has a target; no runtime code yet. |
| `app/frontend/` | T03 | Next.js App Router + TypeScript + Tailwind + shadcn/ui frontend. pnpm workspace. | T01 (tooling config + lockfile + a `tooling.d.ts` marker so `tsc --noEmit` has an input on empty target — deletable by T03), T03 (Next.js scaffold + admin shell). |
| `configs/` | T08 / T16 | Source-of-truth YAML for rubrics, position templates, prompt versions, feature-flag defaults (ADR-021 Configs as Code). | T08 (rubric import), T05a (feature flags), T16 (configs-as-code sync). Currently empty (`.gitkeep`). |
| `docs/design/` | *(pre-existing)* | Design system — principles, tokens, components, per-screen specs. Read by `frontend-engineer` on every UI PR. | Pre-existing. |
| `docs/engineering/` | *(pre-existing + this task)* | Agent-readable operational references: conventions, playbooks, multi-agent workflow, this directory map. | Pre-existing docs; this file (`directory-map.md`) added by T01. |
| `docs/kickoff/` | *(pre-existing)* | One-time launch artefacts (dev briefings, kickoff decks). | Pre-existing; no ongoing edits. |
| `docs/specs/` | *(pre-existing)* | Canonical product specs (`.docx`) for humans/stakeholders. | Pre-existing; updated when product scope changes. |
| `evals/` | T04+ / calibration | Evaluation datasets and harnesses for the Assessor/Interviewer (calibration, regression, prompt tests). | Later tiers (calibration-run skill, prompt-engineer flows). Currently empty (`.gitkeep`). |
| `infra/` | *(pre-existing)* | Infrastructure entry points — `bootstrap.sh` for one-time GCP bootstrap. | Pre-existing. |
| `infra/scripts/` | T01a | One-shot operational scripts (smoke tests, ad-hoc infra probes). Bash-first, no language runtime required beyond `gcloud` + `curl`. | T01a (`vertex-smoke.sh`, the FR-006 smoke runner). Future ad-hoc operational scripts append here without further directory-map edits. |
| `infra/terraform/` | T06 | Managed GCP infrastructure: Cloud Run services, Cloud SQL, Secret Manager, Identity Platform, budget alerts, runtime IAM. | T002 (`002-terraform-backend-bootstrap`) seeded the Terraform root module: `provider.tf`, `versions.tf`, `backend.tf` (hardcoded GCS bucket), `variables.tf`, `terraform.tfvars`, `.gitignore`, `.terraform.lock.hcl` (provider `hashicorp/google ~> 6.0`). T01a layered on top: extra variables (`project_number`, `billing_account`, `ops_email`) + placeholder values; `billing.tf` (notification channel + 2 budgets); minimal `iam.tf` (runtime SA `techscreen-backend@` + `roles/aiplatform.user` + Owner `serviceAccountTokenCreator` binding only — see `specs/003-vertex-quota-region/research.md` §R6). T06 extends `iam.tf` additively (Cloud SQL/Secret Manager/logging/monitoring bindings) and adds `sql.tf`, `cloud_run.tf`, `artifact_registry.tf`, `secrets.tf`, `monitoring.tf`, `network.tf`. T07 adds Identity Platform; T06a's deploy/rollback workflows reference Terraform outputs. |
| `prompts/` | *(pre-existing)* | Versioned agent system prompts: `interviewer/`, `assessor/`, `planner/`, `shared/`. Edits flow through the `agent-prompt-edit` skill. | Pre-existing structure; new versions added by `prompt-engineer`. |
| `specs/` | *(per-feature)* | Spec Kit feature folders (`spec.md`, `plan.md`, `tasks.md`, `checklists/`, optionally `research.md`/`data-model.md`/`contracts/`/`quickstart.md`). | Created per feature by `/speckit-specify`. T01 itself lives at `specs/001-t01-monorepo-baseline/`. |

## Repo-root canonical files (non-folders)

For completeness — these files are at the repo root and are expected by the tree in CLAUDE.md:

| Path | Owner task | Purpose |
|------|-----------|---------|
| `CLAUDE.md` | *(pre-existing)* | Entry point for every Claude Code session. |
| `README.md` | *(pre-existing + this task)* | Public-facing summary. T01 adds a `## Developer setup` section. |
| `.pre-commit-config.yaml` | *(pre-existing)* | Guardrail hooks (constitution §5/§6/§15). T01 does not edit it (FR-009). |
| `.env.example` | *(pre-existing)* | Env keys with empty secret values + non-secret defaults (ADR-022). |
| `.gitignore`, `.dockerignore` | *(pre-existing)* | Ignore rules. |
| `Dockerfile`, `Dockerfile.frontend`, `Dockerfile.vertex-mock` | *(pre-existing)* | Docker build definitions (ADR-010 Docker parity). |
| `docker-compose.yml`, `docker-compose.test.yml` | *(pre-existing)* | Dev + CI Docker stacks. T09 extends with services as they're added. |
| `pyproject.toml`, `uv.lock` | T01 | Python tooling + dep manifest at repo root (consumed by `Dockerfile`). |
| `docs/engineering/vertex-quota.md` | T01a | Canonical Vertex AI quota log (region, granted quotas, verification, smoke-test records, follow-ups). Append-only by convention; format pinned at `specs/003-vertex-quota-region/contracts/vertex-quota-log-format.md`. |

## Rules

1. **Adding a new canonical folder**: add a row to the table above in the same PR that creates the folder. The row's "Owner task" column must reference a T-id from `docs/engineering/implementation-plan.md` (or an ad-hoc task if the folder was not in the original plan).
2. **Removing a canonical folder**: remove the row in the same PR that removes the folder. If the folder was referenced by CLAUDE.md, update CLAUDE.md too.
3. **Empty folders**: every empty canonical folder carries a `.gitkeep` so git tracks it. Remove the `.gitkeep` when the folder gains real content.
4. **No drift**: if this map and CLAUDE.md "Where to find things" disagree, CLAUDE.md wins and this map is patched to match (CLAUDE.md is the sub-agent entry point).
