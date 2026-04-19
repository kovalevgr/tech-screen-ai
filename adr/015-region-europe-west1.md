# ADR-015: Cloud region — europe-west1 (Belgium)

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

Cloud region choice trades off latency, cost, service availability, and data residency.

Candidates are primarily in Ukraine and the Ukrainian diaspora in Europe. Our LLM traffic (Vertex AI) is the largest latency contributor; network latency to Cloud SQL and Cloud Run is a secondary factor.

Shortlisted regions:

- **europe-west1 (Belgium)** — cheapest European tier; Vertex Gemini available; ~50–70 ms from Kyiv.
- **europe-central2 (Warsaw)** — closest to Kyiv (~20–30 ms); 10–15% more expensive; smaller service catalogue.
- **europe-west3 (Frankfurt)** — good central-European location; similar cost to west1; slightly slower to Ukraine than central2.

## Decision

**europe-west1 (Belgium)** for all TechScreen infrastructure.

- Cheapest tier for Cloud Run, Cloud SQL, Artifact Registry, Secret Manager.
- Vertex AI Gemini 2.5 Flash and Pro are available.
- Network RTT to Kyiv is dominated by transit, not region choice, and is acceptable for text-based interviews.

## Consequences

**Positive.**
- ~10–15% ongoing savings on infra vs. central2.
- Broadest GCP service catalogue — future needs (e.g. Cloud Scheduler, Pub/Sub, Cloud Tasks) are guaranteed available.

**Negative.**
- Text-to-text interview latency includes ~50–70 ms of RTT vs. ~20–30 ms from central2. Imperceptible for text; **potentially material for voice** (Roadmap H2).

**Mitigation.**
- When we reach voice trials, we re-evaluate this ADR. Migrating Cloud SQL and Cloud Run to a new region is a maintenance window of a few hours — not a rewrite.
- Vertex AI endpoints can be called from different regions if voice work ends up hosted elsewhere, keeping regional decisions decoupled per service.
