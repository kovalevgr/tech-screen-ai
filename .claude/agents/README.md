# Claude Code sub-agents

Sub-agents for TechScreen development. Each is a single Markdown file with YAML frontmatter (name, description, tool allow-list) followed by the agent's system prompt.

Full workflow and rationale are in [`docs/multi-agent-workflow.md`](../../docs/multi-agent-workflow.md) and [ADR-014](../../adr/014-multi-agent-orchestration-explicit.md).

---

## The agents

| File                                             | Role                                                                                              |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------- |
| [`backend-engineer.md`](./backend-engineer.md)   | FastAPI, SQLAlchemy, Alembic, Pydantic, Vertex adapter, orchestrator, domain code, backend tests. |
| [`frontend-engineer.md`](./frontend-engineer.md) | Next.js, shadcn/ui, Tailwind, design system, React Query, OpenAPI client.                         |
| [`infra-engineer.md`](./infra-engineer.md)       | Terraform, Docker, Cloud Run, GCP IAM, GitHub Actions.                                            |
| [`prompt-engineer.md`](./prompt-engineer.md)     | Agent system prompts, rubric YAML, calibration dataset and runs.                                  |
| [`reviewer.md`](./reviewer.md)                   | Read-only gate: constitution adherence, secrets scan, test coverage, migration safety.            |

## Hard rules (enforced by the orchestrator)

1. **No sub-agent edits outside its layer.** See each agent's allow-list.
2. **No sub-agent touches the constitution, ADRs, or `CLAUDE.md`.** Floor documents are human-edited.
3. **No sub-agent runs `/deploy`, `/promote`, or `/rollback`.** Deploy ops are human-only.
4. **Every sub-agent reads the floor on boot.** `CLAUDE.md` + constitution + relevant ADRs + its layer's reference docs.
5. **The reviewer never writes code.** Comments only.

## Default behaviour

Single-agent, sequential. Fan-out happens only when the user asks or the orchestrator proposes it in `/plan` and the user approves (constitution §18). See `docs/multi-agent-workflow.md` for decision flow and worktree isolation.
