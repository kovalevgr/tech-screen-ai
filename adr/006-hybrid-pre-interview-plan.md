# ADR-006: Hybrid pre-interview InterviewPlan (Variant C)

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

We considered three strategies for pre-interview preparation:

- **Variant A — fully generative at runtime.** The Interviewer picks each question on the fly from the rubric and position template.
- **Variant B — fully scripted.** A human or tool writes a line-by-line script before the interview, and the Interviewer reads it.
- **Variant C — hybrid scaffold.** A pre-interview agent generates a structured `InterviewPlan` (seed questions per competency, suggested depth-probe branches, opening and closing lines). The recruiter reviews and approves it. At runtime the Interviewer uses the plan as a scaffold and adapts wording and follow-ups.

Variant A produces interviews with inconsistent coverage across candidates — a problem for hiring fairness and for calibration. Variant B is rigid, brittle to clarifying questions, and defeats the purpose of an adaptive agent. Variant C balances coverage guarantees with adaptivity.

## Decision

The **Pre-Interview Planner agent** produces an `InterviewPlan` before the session starts. The plan contains:

- Competencies in scope, ordered.
- Seed questions per competency (2–4 options).
- Depth-probe branches for each seed (what to ask if candidate's first answer is shallow).
- Opening and closing scripts.
- Time budget per competency.

The **recruiter reviews and edits** the plan in the Review UI. On approval, the plan is **frozen** into the `interview_session.interview_plan_snapshot` column (JSONB). At runtime, the Interviewer uses the snapshot as an authoritative scaffold.

## Consequences

**Positive.**
- Every interview has guaranteed competency coverage by construction.
- Recruiter stays in the loop — they see and tune the plan before candidates join.
- The plan is auditable: we can show a candidate or compliance officer exactly what was prepared vs. what happened.
- Calibration becomes easier — different candidates answer overlapping seed questions, so Assessor behaviour is comparable across sessions.

**Negative.**
- Adds a manual review step to every session, which costs recruiter time (~5 min/session).
- The plan can drift from the live rubric between generation and session start — mitigated by §4 of the constitution (immutable snapshots).

**Mitigation.**
- Planner defaults are tuned so that most plans need minimal recruiter editing.
- "Plan freshness" warning fires if the rubric version changed since plan generation.
