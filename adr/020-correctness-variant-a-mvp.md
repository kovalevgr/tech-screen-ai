# ADR-020: Correctness evaluation — Variant A for MVP

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

Assessors must flag **factually wrong** answers, not just shallow ones. "The candidate described garbage collection accurately but shallowly" scores differently from "the candidate confidently stated wrong facts about garbage collection."

We considered three mechanisms for correctness:

- **Variant A — Prompt the Assessor itself.** Include `coverage: wrong` as a Assessor output field and add a `FACTUALLY_WRONG` red flag. Rely on the model's own knowledge.
- **Variant B — RAG fact-check.** Retrieve authoritative passages per topic and ask a separate agent to verify factual claims.
- **Variant C — Dual-model cross-check.** Run the same answer through two different models; flag on disagreement.

Variant B needs an authoritative corpus we do not yet have. Variant C doubles cost and produces subtle divergences that are hard to adjudicate. Both have much higher engineering cost than Variant A.

## Decision

**MVP uses Variant A.**

The Assessor prompt explicitly asks for:

- `coverage` enum per competency: `{not_covered, superficial, adequate, deep, wrong}`.
- A `red_flags` list with enum values including `FACTUALLY_WRONG`.
- A `rationale` field supporting any `wrong` flag with the specific false claim.

Reviewers see the Assessor's `wrong` flags and can override via `assessment_correction` (ADR-019). Disagreements become calibration signal.

Variants B and C are on the roadmap (H1/H2) and will be enabled when:

- B: we have an authoritative corpus per competency.
- C: we have a model that reliably disagrees-for-good-reasons (measured on labelled data).

## Consequences

**Positive.**

- Simple. Works day 1. No corpus, no extra models, no extra cost per turn.
- Calibration data from reviewer overrides informs whether we need B/C at all.

**Negative.**

- Model hallucination risk: the Assessor might mark `wrong` things that are actually correct (false positive) or miss `wrong` things it hallucinated as correct (false negative).
- Reviewer load is higher until the model's correctness calibration converges.

**Mitigation.**

- Reviewer UI surfaces `wrong` flags prominently with the model's rationale, making overrides fast.
- Calibration dashboard tracks `FACTUALLY_WRONG` agreement specifically; if accuracy stalls, we escalate to Variant B.
