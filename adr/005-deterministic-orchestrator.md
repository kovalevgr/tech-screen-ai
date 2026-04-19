# ADR-005: Deterministic Python state machine orchestrator

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

A common pattern in agent systems is to let the LLM decide "what happens next" — route between tools, pick the next agent, or decide the session is over. This is sometimes called an "agentic loop" or "autonomous agent".

For TechScreen this pattern has three problems:

1. **Non-reproducibility.** If the same session were replayed, the LLM might choose a different next step, breaking calibration and audit.
2. **Debuggability.** When a session behaves unexpectedly, the root cause is a natural-language reasoning chain, not a deterministic rule.
3. **Cost blow-ups.** A model that decides to take one more turn produces unbounded sessions.

## Decision

Interview flow is controlled by a **deterministic Python state machine**. States include `AWAITING_CANDIDATE`, `ASSESSING_TURN`, `SELECTING_NEXT_QUESTION`, `CLOSING`. Transitions are triggered by typed events (timer expiry, candidate submit, Assessor verdict) — never by free-text model output.

LLMs produce content and structured assessments inside states the orchestrator selects. The Interviewer does not decide the session is over; the orchestrator does.

## Consequences

**Positive.**
- Sessions are reproducible: given the same seed and same turn trace, flow is identical.
- Bugs in the orchestrator are debuggable as Python stack traces, not as "the model decided X".
- Max turn count, max session duration, and max cost per session are enforced as hard invariants by the state machine.
- Aligns with constitution §2.

**Negative.**
- Less adaptive than an LLM-driven flow. If a candidate's answer suggests a new line of questioning, the orchestrator cannot "improvise" a new state on the fly.

**Mitigation.**
- Adaptivity comes from the `InterviewPlan` scaffold (ADR-006): the plan contains multiple question paths, and the orchestrator picks among them based on Assessor output. This is structured adaptivity, not free-form branching.
- If we genuinely need a new state, it is added in code under an ADR, not improvised at runtime.
