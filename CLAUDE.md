# CLAUDE.md

This file is the entry point for [Claude Code](https://docs.claude.com/en/docs/claude-code) working in the TechScreen repository. Every Claude Code session loads this file automatically. Read it in full on first entry; consult the linked documents when a specific decision is in scope.

---

## What this project is

TechScreen is an internal AI-powered technical interview system for N-iX. It conducts structured technical interviews with candidates, produces reviewer-auditable assessments, and improves via reviewer corrections. See [`README.md`](./README.md) for a public-facing summary and [`docs/specs/mvp-scope.docx`](./docs/specs/mvp-scope.docx) for MVP scope.

---

## The floor: read these before non-trivial work

1. [`.specify/memory/constitution.md`](./.specify/memory/constitution.md) — **20 non-negotiable invariants.** If a change would violate any of these, stop and flag it.
2. [`adr/`](./adr/) — 21 architectural decisions with context and consequences. Start at [`adr/README.md`](./adr/README.md) for the index.
3. [`docs/specs/architecture.docx`](./docs/specs/architecture.docx) — system architecture diagram and data flow.
4. [`docs/specs/data-model.docx`](./docs/specs/data-model.docx) — full schema with invariants.
5. [`docs/specs/agents.docx`](./docs/specs/agents.docx) — Interviewer / Assessor / Planner contracts.

Everything else in `docs/` is domain reference — consult when relevant. Layout:

- [`docs/specs/`](./docs/specs/) — canonical product specs (.docx) for humans/stakeholders.
- [`docs/engineering/`](./docs/engineering/) — operational references (.md) Claude Code agents consult during work (conventions, playbooks, glossary, implementation plan, multi-agent workflow).
- [`docs/design/`](./docs/design/) — design system (principles, tokens, components, per-screen specs).
- [`docs/kickoff/`](./docs/kickoff/) — one-time launch artefacts (dev briefing, kickoff decks).

---

## Core invariants — most commonly violated by accident

These are the shortcuts Claude Code is most likely to take that we explicitly forbid. They are all stated in full in the constitution; listed here so they stay top of mind.

- **No LLM-driven flow control.** The orchestrator is a Python state machine. LLMs produce content, not routing decisions. (§2, ADR-005)
- **No `UPDATE` / `DELETE` on audit tables.** Corrections are new rows. (§3, ADR-019)
- **Rubric edits never touch existing sessions.** Sessions hold a frozen `rubric_snapshot`. (§4, ADR-018)
- **No secret ever lands in source, logs, Docker images, or LLM context.** `.env` locally, Secret Manager in prod, no JSON service-account keys anywhere. (§5–6, ADR-013)
- **No staging environment.** Test via Docker, release via Cloud Run traffic splitting at 0%. (§8, ADR-009/012)
- **Dark-launch by default.** Risky features ship behind a feature flag that starts `false`. (§9, ADR-011)
- **Forward-only, zero-downtime migrations.** Destructive DDL needs its own ADR. (§10)
- **Hybrid language in prompts.** English instructions + Ukrainian candidate-facing output. (§11, ADR-008)
- **Hard caps on LLM calls.** 30s timeout, 4096 max output tokens, per-session cost tracked. (§12)
- **Calibration never blocks merge.** Warning-only in CI. (§13)
- **Contract-first before parallel layer work.** OpenAPI or JSON schema committed before backend/frontend fan out. (§14, ADR-014)
- **Configs as code.** Rubrics, prompts, flag defaults live in Git. Admin UI edits are promoted via PR. (§16, ADR-021)

---

## How work happens here (Spec Kit)

TechScreen uses [GitHub Spec Kit](https://github.com/github/spec-kit) `0.7.4` for all non-trivial feature work. Spec Kit integrates with Claude Code as **skills** under `.claude/skills/speckit-*` — **not as slash commands**. Invoke them by name through the skill picker.

The workflow:

```
speckit-specify    → spec.md (what / why)
speckit-clarify    → iterate on an ambiguous spec (optional)
speckit-plan       → plan.md with agent / parallel / depends_on fields
speckit-tasks      → ordered tasks.md
speckit-analyze    → cross-check spec ↔ plan ↔ tasks (optional)
speckit-checklist  → pre-merge / pre-implement checklist (optional)
speckit-implement  → execute tasks; respects `parallel: true` only when set
```

`speckit-constitution` and `speckit-taskstoissues` are also available for the rare cases (constitution edit — always ADR-gated; export `tasks.md` to GitHub issues). Five `speckit-git-*` helpers are installed but `auto_commit: false` in `.specify/extensions/git/git-config.yml` — **we commit manually** so CODEOWNERS, message style, and pre-commit hooks stay in our control. Do not flip `auto_commit` on without a PR that explains why.

Specifications live under `.specify/specs/<slug>/` (`spec.md`, `plan.md`, `tasks.md`, `checklist.md`) and ship as part of the feature PR. Trivial changes (typos, dependency bumps, formatting) skip the flow entirely.

> Older docs (e.g., `docs/engineering/implementation-plan.md`, the cheat sheet below) sometimes say "run `/specify`" or "run `/plan`" — read those as "invoke the corresponding `speckit-*` skill".

**`plan.md` must:**

- Label each task with `agent:` (`backend-engineer`, `frontend-engineer`, `infra-engineer`, `prompt-engineer`, or no agent for main orchestrator).
- Mark parallelisable task groups with `parallel: true`.
- Reference a committed contract (OpenAPI spec or JSON schema) for any cross-layer parallel group. No contract → no parallel fan-out.
- If the change affects screens, reference `docs/design/screens/<NN-xxx>/spec.md`.
- If the change affects prompts, reference `prompts/<agent>/<version>/`.
- If the change affects the rubric, reference the `rubric_tree_version` bump.

---

## Multi-agent: explicit, not automatic

We have five Claude Code sub-agents defined under [`.claude/agents/`](./.claude/agents/):

| Agent               | Role                                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------------- |
| `backend-engineer`  | FastAPI, SQLAlchemy, Alembic, Vertex adapter.                                                            |
| `frontend-engineer` | Next.js, shadcn/ui, Tailwind, design system.                                                             |
| `infra-engineer`    | Terraform, Docker, GitHub Actions, Cloud Run.                                                            |
| `prompt-engineer`   | Agent prompts, rubric YAML, calibration.                                                                 |
| `reviewer`          | Read-only. Validates constitution adherence, secrets scan, test coverage, migration safety before merge. |

Full workflow and maturity phases are documented in [`docs/engineering/multi-agent-workflow.md`](./docs/engineering/multi-agent-workflow.md).

**Default behaviour at MVP:** sequential single-agent. Sub-agent fan-out happens only when either the user explicitly requests it in the prompt, or the orchestrator proposes it in `/plan` and the user approves. Automatic parallelisation is disabled.

---

## Skills

Reusable Claude Code skills live in [`.claude/skills/`](./.claude/skills/). Current skills:

- [`vertex-call`](./.claude/skills/vertex-call/SKILL.md) — wrapper for Vertex AI calls with retry, timeout, cost tracking.
- [`agent-prompt-edit`](./.claude/skills/agent-prompt-edit/SKILL.md) — versioned edit flow for agent system prompts, with calibration prompt.
- [`rubric-yaml`](./.claude/skills/rubric-yaml/SKILL.md) — rubric tree YAML validation, diffs, snapshot generation.
- [`calibration-run`](./.claude/skills/calibration-run/SKILL.md) — run calibration against labelled dataset, produce agreement metrics.

Invoke a skill by name. Do not duplicate skill logic in ad-hoc scripts.

---

## Where to find things

```
.
├── .specify/memory/constitution.md  Project invariants.
├── adr/                             Architectural decisions (001..021).
├── docs/
│   ├── specs/                       Canonical .docx specs (architecture, data-model, agents, methodology, mvp-scope, roadmap).
│   ├── engineering/                 Agent-readable operational references (.md): conventions, playbooks, glossary, implementation plan, multi-agent workflow, vertex-integration, testing strategy, anti-patterns.
│   ├── design/                      Design system — principles, tokens, components, per-screen specs.
│   └── kickoff/                     One-time launch artefacts (dev briefings).
├── app/
│   ├── backend/                     FastAPI service.
│   └── frontend/                    Next.js service.
├── alembic/                         DB migrations.
├── configs/                         Rubrics, templates, flag defaults (source of truth; see ADR-021).
├── prompts/                         Agent system prompts per version.
├── infra/
│   ├── bootstrap.sh                 One-time GCP bootstrap.
│   └── terraform/                   All managed infra.
├── .claude/
│   ├── agents/                      Sub-agent definitions.
│   └── skills/                      Reusable skills.
├── docker-compose.yml               Dev stack.
├── docker-compose.test.yml          Test stack.
└── .github/workflows/               CI/CD.
```

---

## Cheat sheet

- **Make a change.** Write a spec (`/specify`), then a plan, then tasks, then implement.
- **Edit a prompt.** Use the `agent-prompt-edit` skill. Prompt changes trigger the calibration job (warning-only).
- **Edit the rubric.** Use the `rubric-yaml` skill. Rubric edits create a new `rubric_tree_version`, never modify existing nodes in place.
- **Add a feature flag.** New row in `configs/feature-flags.yaml` + migration that seeds the DB row with `enabled=false`.
- **Deploy.** Run `/deploy` when the PR is merged and green. Then `/promote 10`, `/promote 50`, `/promote 100`.
- **Roll back.** Run `/rollback`. Single Cloud Run traffic shift, completes in under a minute.
- **Secret needed.** Add a key to `.env.example` with an empty value (secrets always empty; non-secret defaults OK per ADR-022). Add a `google_secret_manager_secret` to Terraform. Fill the value in Secret Manager manually — never commit the value.
- **Database schema change.** Alembic migration + ADR if destructive + append-only invariants (§3) respected.
- **Touch a screen.** Reference `docs/design/screens/<NN-xxx>/spec.md` from the plan. If the spec doesn't exist yet, write it first.

---

## What to do when something is unclear

1. Check the constitution (one of the 20 principles probably applies).
2. Check the ADRs (scan titles first via [`adr/README.md`](./adr/README.md)).
3. Check the relevant `docs/engineering/*.md` reference.
4. Ask the user. Do not guess on decisions that would affect invariants or architecture.

When in doubt, surface the question rather than assume. A five-minute clarification is cheaper than a two-hour course correction.

---

## Document versioning

- **This file:** v1.1 — 2026-04-19. (v1.1: Spec Kit section rewritten — skills, not slash commands; auto_commit-off note added.)
- Update this file when: a new invariant is added, a new sub-agent or skill is introduced, the repository layout materially changes, or a new core workflow is adopted.
- Keep it under ~250 lines. If it grows beyond that, move details into linked docs.
