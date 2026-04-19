# ADR-012: Cloud Run traffic splitting as canary mechanism

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

With no staging (ADR-009), we need a way to expose a new revision to real traffic in a controlled way. Options:

1. **Blue/green** — deploy to a parallel service and flip DNS. Heavyweight for Cloud Run.
2. **Canary via service mesh** — Istio / Cloud Service Mesh. Over-engineering for two services.
3. **Cloud Run native traffic splitting** — a built-in feature that splits traffic across revisions by percentage.

## Decision

Deploys produce a new Cloud Run revision. The revision initially receives **0% of traffic** (`--no-traffic`). Once smoke tests against the preview URL pass, traffic is ramped:

- `/promote 10` — shift to 10% on the new revision.
- `/promote 50` — shift to 50%.
- `/promote 100` — full cutover.
- `/rollback` — instantly shift 100% back to the previous stable revision.

Ramp decisions are human-initiated (no automated graduation at MVP). The slash commands are implemented via a `deploy-techscreen` Claude Code skill.

## Consequences

**Positive.**

- Native GCP feature, no extra infrastructure.
- Rollback is a single `gcloud run services update-traffic` call, typically completes in 30–60 seconds (constitution §19).
- Previous revisions remain deployed for one week, giving time to investigate before auto-cleanup.
- Same mechanism works for backend and frontend independently.

**Negative.**

- Cloud Run traffic splitting is at the **service** level, not per-request-attribute. We cannot route "Ukrainian users" vs "other users" to different revisions.
- Sessions initiated on an old revision do not follow traffic shifts mid-session — they complete on their original revision. This is generally desirable but requires care on schema changes.

**Mitigation.**

- Per-session "stickiness" is explicit in our model: the session's `app_revision` column records which revision served it. Schema/contract changes must be backwards compatible within a rollback window.
- Cleanup policy: revisions older than 7 days with 0% traffic are automatically deleted by a scheduled job.
