# ADR-009: Production-only topology, no staging

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

The industry-default environment model is `dev → staging → prod`. Staging exists to catch integration issues before they reach users. But staging has well-known pathologies:

- It drifts from production (different data volumes, different configs, stale seed data).
- It doubles infrastructure cost.
- It gives a false sense of safety — "it worked in staging" becomes the incident post-mortem line.

TechScreen is an internal tool with a small user set (10–20 recruiters, 20–50 candidates per week at pilot). We have resources either to build a high-fidelity staging environment or to build strong compensating controls — not both.

## Decision

**There is one long-lived environment: production.** One GCP project, `<PROJECT_ID>`, hosts everything. No staging, no QA, no UAT.

Compensating controls:

- **Docker parity** (ADR-010) keeps dev containers identical to prod images.
- **Cloud Run traffic splitting** (ADR-012) lets a new revision receive 0% traffic until smoke tests pass, then ramp 10% → 50% → 100%.
- **Feature flags** (ADR-011) allow merging code ahead of enablement.
- **Append-only audit** (ADR-019) makes any production anomaly reconstructible.

## Consequences

**Positive.**

- ~40% infrastructure cost saving vs. a prod+staging setup.
- No staging drift debt.
- Incentive alignment: engineers must ship code that is genuinely safe, not "safe in staging".

**Negative.**

- No pre-prod environment for recruiter training or sales demos. Mitigated by isolated demo sessions tagged `is_demo: true` in the same DB — they never affect analytics or decisions.
- A subtle production-only bug has no catch-before-users step.

**Mitigation.**

- Smoke test suite runs against every new Cloud Run revision at 0% traffic before any user sees it.
- Dark launches (constitution §9) for anything touching critical paths.
