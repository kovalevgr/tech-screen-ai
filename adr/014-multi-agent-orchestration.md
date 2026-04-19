# ADR-014: Multi-agent orchestration is explicit, not automatic

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

Claude Code supports sub-agents — specialised agents defined in `.claude/agents/*.md` that the main Claude can dispatch tasks to via the `Task` tool. Combined with git worktrees, this makes it possible to run backend, frontend, and infra work in parallel.

The tempting design is an orchestrator that "figures out" when to fan out. Two problems with that:

1. We do not yet have calibration data for an orchestrator's parallelisation heuristics. Wrong fan-out wastes tokens and creates merge conflicts.
2. A sub-agent that modifies a file another sub-agent is also modifying produces silent bugs that are hard to trace.

## Decision

**Multi-agent fan-out is explicit, declared in the plan, and approved before `/implement` runs.**

Process:

1. `/specify` and `/plan` are produced by the orchestrator Claude.
2. `/plan` must label each task with an `agent:` field (e.g. `backend-engineer`, `frontend-engineer`, `prompt-engineer`, `reviewer`).
3. Tasks that can run in parallel are explicitly marked `parallel: true` and grouped. The plan states *why* they are safe to run in parallel (typically: disjoint file sets + a committed contract — see constitution §14).
4. The human approves the plan before `/implement`.
5. `/implement` refuses to fan out tasks not marked `parallel: true`.

Sub-agents defined for MVP:

- `backend-engineer` — FastAPI, Postgres, Alembic.
- `frontend-engineer` — Next.js, shadcn, Tailwind.
- `infra-engineer` — Terraform, Docker, CI.
- `prompt-engineer` — Vertex agents, prompts, rubric.
- `reviewer` — read-only, constitution / security / tests.

## Consequences

**Positive.**
- Predictable, debuggable parallelism.
- Cost of fan-out is visible at plan time, not a surprise mid-`implement`.
- Sub-agent definitions let each one carry a focused system prompt — better quality per domain.

**Negative.**
- More ceremony than fully-automatic orchestration. A one-layer feature could skip all this and just run sequentially.

**Mitigation.**
- For one-layer changes, the plan is trivially small (one agent, no `parallel: true`) and this ADR imposes no measurable overhead.
- Maturity phases (MVP → post-MVP → mature) are documented in `docs/multi-agent-workflow.md`. We can loosen explicitness once we have data.
