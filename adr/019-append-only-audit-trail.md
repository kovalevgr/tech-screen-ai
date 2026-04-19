# ADR-019: Append-only audit trail

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

Hiring decisions may be challenged months after the fact:

- A candidate appeals a rejection.
- A manager asks why a specific competency was scored low.
- Compliance or legal requests a full record of what the system and reviewers did.

If we edit or delete any row related to a decision, we lose the audit trail. A reviewer correction that overwrites the original Assessor score destroys our ability to answer "what did the model originally say, and what did the human change?"

## Decision

The following tables are **append-only** — rows are never `UPDATE`-ed or `DELETE`-ed by application code:

- `turn_trace` — every LLM call with inputs, outputs, latency, cost.
- `assessment` — the Assessor's original output per turn.
- `assessment_correction` — reviewer overrides. An override is a **new row** referencing the `assessment` it corrects, not a mutation of the assessment itself.
- `turn_annotation` — reviewer quality marks per turn.
- `session_decision` — the final hiring decision artefact, including inputs and justification.
- `audit_log` — actor, action, subject, timestamp for every state change across the system.

Effective scores are computed as "latest correction wins", not by updating the original.

## Consequences

**Positive.**

- Constitution §3 enforced.
- Full reconstructability: any historical decision can be explained step-by-step.
- Calibration metrics (Assessor vs reviewer agreement) are always computable because both sides of the comparison are preserved.
- Audit of reviewers themselves (how often they override, toward which direction) becomes possible — useful for reviewer training.

**Negative.**

- Storage grows monotonically. For MVP scale this is negligible; at scale we partition old rows or archive to cold storage.
- Queries for "effective" values require window functions or materialised views rather than a simple select.

**Mitigation.**

- DB-level `REVOKE UPDATE, DELETE` on the application role for these tables. The database enforces the invariant, not just code discipline.
- `vw_effective_assessment` materialised view exposes the "latest correction wins" view as a simple query interface.
