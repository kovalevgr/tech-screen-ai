# Multi-Agent Workflow

How TechScreen uses Claude Code sub-agents. The short version: **explicit, not automatic.** Sub-agent fan-out happens when the user asks for it or the orchestrator proposes it in `/plan` and the user approves — never silently.

Related: [ADR-014](../adr/014-multi-agent-orchestration-explicit.md), [ADR-017](../adr/017-spec-driven-development.md), [constitution §14, §18](../.specify/memory/constitution.md).

---

## Why we have sub-agents at all

TechScreen spans several layers — backend (Python / FastAPI / SQLAlchemy), frontend (Next.js / Tailwind / shadcn), infra (Terraform / Cloud Run / GCP), and prompts (agent system prompts / rubric YAML). Each layer has its own conventions, tooling, and failure modes. A single generalist session can work each layer, but it switches contexts a lot and is slower on parallel tasks.

Sub-agents give us two things:

1. **Contextual specialisation.** A backend-engineer session does not load the Tailwind token system into context; a frontend-engineer session does not load `alembic.ini`. Each agent is briefed for its layer.
2. **Parallelism when safe.** When a change is wide (say, a new endpoint + a new screen + a Terraform secret), we can fan out, provided a shared contract gates the work.

What sub-agents do **not** give us: magic coordination. The human is still the decision-maker. The orchestrator's job is to propose, wait for approval, and then dispatch.

---

## The agents

All sub-agents are defined in [`.claude/agents/`](../.claude/agents/). Each is a single Markdown file with frontmatter describing the agent's role, allowed tools, and system prompt.

| Agent               | Scope                                                                                         | Allowed to edit                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `backend-engineer`  | FastAPI, SQLAlchemy, Alembic, Pydantic, Vertex adapter, agent module code                     | `app/backend/**`, `alembic/**`, `configs/**` (service-level), tests under `app/backend/tests/**` |
| `frontend-engineer` | Next.js App Router, shadcn/ui, Tailwind, design system, React Query, OpenAPI client           | `app/frontend/**`                                                                                |
| `infra-engineer`    | Terraform, Docker, Cloud Run, GCP IAM, GitHub Actions                                         | `infra/**`, `.github/workflows/**`, `Dockerfile*`, `docker-compose*.yml`                         |
| `prompt-engineer`   | Agent system prompts, rubric YAML, calibration datasets                                       | `prompts/**`, `configs/rubric/**`, `calibration/**`                                              |
| `reviewer`          | Read-only. Validates constitution, secrets scan, test coverage, migration safety before merge | none (comments only)                                                                             |

Each agent loads `CLAUDE.md`, the constitution, and the ADRs on boot. Each agent also reads its layer's specific reference doc (e.g., `coding-conventions.md` for backend/frontend, `vertex-integration.md` for backend touching LLM code, `prompt-engineering-playbook.md` for the prompt-engineer).

The `reviewer` agent is described in full in its own file under `.claude/agents/reviewer.md`. It is the last gate before merge and it is read-only by design.

---

## When to fan out, when not to

### Fan out when

- A change legitimately spans two or more layers and the tasks can run in parallel behind a committed contract (OpenAPI spec, JSON schema, DB schema).
- The spec is written and the plan explicitly marks task groups `parallel: true`.
- The user has approved the fan-out plan.

### Do **not** fan out when

- The change is small. A one-file change does not need two agents to look at it.
- The contract is not committed yet. Contract-first is constitution §14. Without a contract, parallel work diverges.
- The work is exploratory. If the right design is not yet known, parallelism multiplies the wrong direction by N.
- The user has not approved fan-out. Default to single-agent.

The bias is single-agent. Fan-out is a deliberate act.

---

## The decision flow

```
user asks for a change
    │
    ▼
/specify   ─► spec.md        ← describes what and why
    │
    ▼
/plan      ─► plan.md        ← lists tasks, labels agent:, marks parallel: true where safe
    │
    ▼
user reads /plan output
    │
    ├─► approves single-agent execution       ─► /implement runs sequentially
    │
    └─► approves fan-out                      ─► /implement dispatches to sub-agents,
                                                  waits for each, assembles output
```

The user may override the plan before `/implement` in either direction — ask the orchestrator to fan out when it chose not to, or to go sequential when it proposed fan-out.

---

## What a fan-out plan looks like

A `plan.md` that enables fan-out looks like this (excerpt):

```markdown
## Tasks

### Group A (contract) — sequential, main orchestrator

- A1 — Update OpenAPI spec `app/backend/openapi.yaml` to add `POST /sessions/{id}/pause`.
- A2 — Regenerate frontend client.
- A3 — Commit the contract.

### Group B (implementation) — parallel: true

- B1 — agent: backend-engineer — implement route, service, repository changes. Add integration test.
- B2 — agent: frontend-engineer — implement the `PauseButton` component and wire up the new mutation. Add component test.
- B3 — agent: infra-engineer — no-op for this change (omitted).

### Group C (verification) — sequential, main orchestrator

- C1 — Run docker-compose.test.yml end-to-end.
- C2 — Request reviewer agent pass on the combined diff.
```

Group A commits the contract first. Group B fans out. Group C assembles and verifies.

If Group A is missing — if the PR starts with B1 and B2 running without a committed spec — the orchestrator rejects the plan. Contract-first is not negotiable (constitution §14, ADR-014).

---

## Isolation — git worktrees

When sub-agents run in parallel they work in separate git worktrees under a common `.claude/worktrees/` directory. Each worktree is a branch off the shared base commit. The orchestrator:

1. Creates `.claude/worktrees/<agent>-<task-id>` for each parallel task.
2. Dispatches the task to the sub-agent, which runs in that worktree.
3. Waits for all parallel tasks.
4. Merges the worktree branches back into the feature branch (fast-forward where possible, merge commit otherwise).
5. Runs verification (Group C) on the merged result.

If two parallel tasks touch the same file, the merge fails and the orchestrator halts, asks the user to reconcile, and resumes. This is rare if the plan was correctly scoped — overlap is usually a planning mistake.

---

## The `reviewer` sub-agent

Every non-trivial PR ends with a `reviewer` pass. The reviewer:

- Loads the constitution, all ADRs, `CLAUDE.md`, `coding-conventions.md`, and `anti-patterns.md`.
- Reads the PR diff.
- Comments on violations: constitution, missing tests, secret leaks, destructive DDL without an ADR, prompt edits in place, unversioned rubric changes.
- **Cannot write or commit code.** Read-only by design.
- Blocks merge via a "changes requested" comment if it finds a violation.

The reviewer is the cheapest form of automated discipline we have. It is the last stop before merge.

---

## Maturity phases

### Phase 0 — MVP (now)

- Single-agent default.
- Fan-out explicitly requested per task.
- Reviewer sub-agent runs on every PR.
- Worktrees used for fan-out; sequential for everything else.

### Phase 1 — Pilot has shipped, tooling is stable

- The orchestrator may propose fan-out in `/plan` for multi-layer tasks with committed contracts, still requiring user approval.
- Reviewer sub-agent's block list grows (more checks as we learn what breaks).

### Phase 2 — Team is distributed, multiple humans

- Fan-out can be default for known-safe task shapes (add endpoint + add screen + add secret).
- A human still signs off on the merged PR; sub-agents never auto-merge.
- Reviewer sub-agent runs on PR open and on every force-push.

We are currently in Phase 0. Phase transitions require an ADR amendment.

---

## Rules the orchestrator enforces

1. **No fan-out without a committed contract.** The plan must reference `openapi.yaml` or a JSON schema file that exists on the feature branch.
2. **No sub-agent edits outside its layer.** If `backend-engineer` tries to touch `app/frontend/**`, the orchestrator rejects.
3. **No sub-agent touches the constitution, ADRs, or `CLAUDE.md`.** Those are floor documents and are only edited via dedicated PRs authored by a human.
4. **No sub-agent runs `/deploy` or `/promote` or `/rollback`.** Deploy operations are human-only (see `docs/deploy-playbook.md`).
5. **No sub-agent skips the spec.** Every non-trivial task starts at `/specify`. Trivial carve-out is for typos and dependency bumps.

---

## Example — single-agent flow

User says: "add a `CandidateCard` component that shows the candidate's name and status."

1. `/specify` — spec describes the component and where it appears.
2. `/plan` — one agent: frontend-engineer. One task group, sequential.
3. `/implement` — frontend-engineer implements the component, test, and integrates it where the spec says.
4. Reviewer sub-agent pass.
5. Human merges.

No fan-out needed. Single layer, single agent.

---

## Example — fan-out flow

User says: "add a pause / resume feature. Candidates can pause during a session; recruiters can see paused sessions in the dashboard."

1. `/specify` — spec covers the pause semantics, the UI affordances, and the state-machine transitions.
2. `/plan` — three groups:
   - Group A: commit the `POST /sessions/{id}/pause` OpenAPI addition and the new `SessionState.PAUSED` value in `configs/session-states.yaml`.
   - Group B (parallel): backend-engineer implements the route + state transition; frontend-engineer builds the `PauseButton` and dashboard badge; infra-engineer adds a `candidate.pause_enabled` feature flag row.
   - Group C: integration test, reviewer pass, merge.
3. User approves fan-out.
4. `/implement` — orchestrator runs Group A sequentially, then dispatches Group B to three sub-agents in worktrees, waits, merges, runs Group C.
5. Reviewer sub-agent pass.
6. Human merges behind the feature flag (flag defaults `false` per ADR-011).

---

## What breaks if we ignore this

- **Parallel without a contract.** Backend ships a field the frontend never reads; frontend ships a field the backend never sends. Wasted work, angry PRs.
- **Sub-agents editing each other's layers.** A backend-engineer "fixing" a Tailwind class breaks the design system silently. Layer boundaries are conventional; we enforce them in tooling.
- **No reviewer pass.** Constitution violations slip in, and we re-do the work in a later PR with more context lost.
- **Fan-out on small tasks.** Overhead of worktree + dispatch + merge exceeds the time saved. Worse signal-to-noise.

---

## Ownership

- **Sub-agent definitions (`.claude/agents/*.md`)** are owned by the project. Edits require a PR.
- **The orchestrator** is whichever Claude Code session the user starts. There is no persistent orchestrator process — `/plan` and `/implement` drive the flow.
- **The reviewer sub-agent** is the only one that is required on every non-trivial PR. All others are optional / situational.

---

## Document versioning

- v1.0 — 2026-04-18.
- Update this file when: a sub-agent is added or removed, the fan-out decision rules change, worktree isolation changes, or the maturity phase advances.
