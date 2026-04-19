# ADR-004: Agent architecture — 2 runtime + 1 pre-interview

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

We considered three agent topologies:

1. **One monolithic agent** — a single LLM call per turn handles dialogue, question selection, and scoring.
2. **Many specialised agents** — separate agents for topic routing, question selection, rubric lookup, scoring, summarisation, language style check, etc.
3. **Two runtime agents + one offline planner.**

Monolithic agents produce lower-quality assessments because dialogue fluency and rubric-grounded scoring pull the model in opposite directions. Many specialised agents add latency, cost, and orchestration complexity without measurable quality gains at our MVP scale.

## Decision

TechScreen uses **three distinct agents**:

- **Interviewer** (runtime, per turn) — conducts the dialogue. Selects the next question from the `InterviewPlan`, formulates it in Ukrainian, handles follow-ups.
- **Assessor** (runtime, per candidate turn) — produces structured JSON: per-competency score, correctness flags, communication score, rationale.
- **Pre-Interview Planner** (offline, once per session) — produces an `InterviewPlan` (hybrid scaffold, see ADR-006) from the position template and rubric.

The orchestrator (not an agent, see ADR-005) dispatches to these agents from within a deterministic state machine.

## Consequences

**Positive.**
- Each agent has a focused prompt, measurable behaviour, and independent calibration baseline.
- Failure of the Assessor does not break the Interviewer mid-session — the session continues and the missing assessment is filled in by a retry job.
- Prompt changes to one agent are scoped: Interviewer-only prompt improvements cannot accidentally drift the Assessor.

**Negative.**
- Two LLM calls per candidate turn instead of one — ~2× latency on the critical path. Mitigated by running Assessor in parallel with Interviewer's next question.
- Three system prompts to maintain and calibrate instead of one.

**Mitigation.**
- Interviewer and Assessor calls are issued concurrently from the orchestrator. Candidate waits only on Interviewer.
- Prompt-engineering skill (`.claude/skills/agent-prompt-edit`) enforces version/review on prompt changes per agent.
