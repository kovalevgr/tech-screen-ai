# TechScreen docs

This directory has four buckets. Each has a clear audience and update cadence.

| Bucket                           | Audience                                 | Format    | Update cadence                                  |
| -------------------------------- | ---------------------------------------- | --------- | ----------------------------------------------- |
| [`specs/`](./specs/)             | Humans, stakeholders, reviewers          | .docx     | Stable; changes via ADR                         |
| [`engineering/`](./engineering/) | Claude Code agents + engineers           | .md       | Living — updated as operational practice shifts |
| [`design/`](./design/)           | `frontend-engineer`, designers, reviewer | .md + PNG | Living — bumped with screen or token changes    |
| [`kickoff/`](./kickoff/)         | Humans — one-time launch audiences       | .docx     | Point-in-time; archived after launch            |

---

## [`specs/`](./specs/) — canonical product specs

The floor for product understanding. Stakeholder-facing .docx files. If a sub-agent is about to change something load-bearing and the spec disagrees, the spec wins — or the spec updates in the same PR.

- [`architecture.docx`](./specs/architecture.docx) — system architecture, data flow, component diagram.
- [`data-model.docx`](./specs/data-model.docx) — database schema, invariants, ER diagram.
- [`agents.docx`](./specs/agents.docx) — Interviewer / Assessor / Planner contracts.
- [`assessment-methodology.docx`](./specs/assessment-methodology.docx) — rubric, scoring, correctness approach, calibration loop.
- [`mvp-scope.docx`](./specs/mvp-scope.docx) — what ships in MVP and what doesn't.
- [`roadmap.docx`](./specs/roadmap.docx) — horizon-1/2/3 plan and deferred features.

## [`engineering/`](./engineering/) — operational references

Agent-readable markdown that Claude Code agents consult during work. If something describes _how_ the team operates — conventions, playbooks, the rolling plan — it lives here.

- [`implementation-plan.md`](./engineering/implementation-plan.md) — 12-week MVP task breakdown (58 tasks) used by orchestrator during `/specify → /plan → /tasks → /implement`.
- [`multi-agent-workflow.md`](./engineering/multi-agent-workflow.md) — how fan-out is decided and executed (MVP → mature phases).
- [`coding-conventions.md`](./engineering/coding-conventions.md) — Python + TS layering, style, naming, testing.
- [`anti-patterns.md`](./engineering/anti-patterns.md) — what not to do, with reasons.
- [`testing-strategy.md`](./engineering/testing-strategy.md) — test layers + calibration.
- [`deploy-playbook.md`](./engineering/deploy-playbook.md) — `/deploy`, `/promote`, `/rollback` flow.
- [`cloud-setup.md`](./engineering/cloud-setup.md) — GCP topology, IAM, secrets mapping.
- [`vertex-integration.md`](./engineering/vertex-integration.md) — how we call Vertex.
- [`prompt-engineering-playbook.md`](./engineering/prompt-engineering-playbook.md) — how to write and change agent prompts.
- [`glossary.md`](./engineering/glossary.md) — domain terms.

## [`design/`](./design/) — design system

Principles, tokens, components, and per-screen specs. Owned by `frontend-engineer` and reviewed by `reviewer` for visual discipline.

See [`design/README.md`](./design/README.md) for structure.

## [`kickoff/`](./kickoff/) — one-time launch artefacts

Point-in-time deliverables: dev briefings, launch decks, retrospectives. They are not updated after the event they document.

- [`dev-briefing-2026-04-19.docx`](./kickoff/dev-briefing-2026-04-19.docx) — developer kickoff briefing.

---

## When to add a doc

| Asking…                                                                           | Put it in                                                                           |
| --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| "What's the architecture of X?" "What tables exist?" "What's the rubric?"         | `specs/`                                                                            |
| "How do I write a migration?" "What's the naming convention?" "How do we deploy?" | `engineering/`                                                                      |
| "What does this screen look like?" "What's the spacing scale?"                    | `design/`                                                                           |
| "What did we say at the kickoff on DATE?"                                         | `kickoff/`                                                                          |
| Architectural _decision_ with alternatives considered                             | [`adr/`](../adr/) (not docs/)                                                       |
| Project invariant that can never be violated                                      | [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) (not docs/) |
