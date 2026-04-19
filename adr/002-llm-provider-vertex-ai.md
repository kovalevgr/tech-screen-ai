# ADR-002: LLM provider — Google Vertex AI Model Garden

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

TechScreen depends on high-quality LLMs for dialogue (Interviewer), structured evaluation (Assessor), and offline planning (Pre-Interview Planner). We considered three sourcing options:

1. **Direct provider APIs** — Anthropic, OpenAI, Google AI Studio.
2. **Vertex AI Model Garden** — Gemini models first-party, Anthropic Claude via partnership, unified IAM and billing.
3. **Self-hosted open models** — Llama/Mistral on GKE with GPU nodes.

N-iX has already approved Vertex AI for other products, meaning procurement, DPA, billing, and IAM integration are solved. Self-hosting open models is off the table for MVP budget and ops reasons. Direct provider APIs would require separate procurement and billing integration per vendor.

## Decision

**All production LLM traffic goes through Vertex AI.** The application never calls Anthropic, OpenAI, or Google AI Studio endpoints directly.

Model selection across providers is available via Model Garden (Gemini first-party, Claude via Anthropic-on-Vertex). Specific model choice is covered in ADR-003.

## Consequences

**Positive.**
- Single billing stream, single IAM surface, single audit log.
- Workload Identity Federation (ADR-013) works uniformly — no vendor-specific credential format.
- A/B tests across providers (Gemini vs Claude on the same prompt) are API-compatible with minor schema adaptors.
- Data residency aligns with our Cloud Run region (see ADR-015).

**Negative.**
- Model availability on Vertex lags provider-native by days to weeks. A new Gemini or Claude version may be accessible on its native API before appearing in Model Garden.
- We inherit Vertex quota limits, which are per-project and per-model and must be raised in advance of load tests.

**Mitigation.**
- Vertex adapter is isolated in a single module (`app/backend/llm/vertex.py`). If we ever need to call a native API, the change is contained.
- Quota increases are requested as part of deploy checklist before any meaningful load.
