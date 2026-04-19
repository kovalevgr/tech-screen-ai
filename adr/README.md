# Architecture Decision Records

This directory captures every non-trivial architectural decision taken on TechScreen. We use the [Michael Nygard format](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions): **Context, Decision, Consequences**.

## Rules

- **One decision per file.** If a PR introduces several decisions, write several ADRs.
- **Never delete.** A decision that is reversed is not erased — it is `Superseded by ADR-NNN` and the new ADR links back.
- **English only.**
- **Short.** Aim for one page. If an ADR grows beyond two pages, split it.
- **Immutable once ratified.** Edits after `Status: Accepted` must be amendments at the bottom with a date, not in-place edits.

## Lifecycle

```
Proposed → Accepted → (Deprecated | Superseded by ADR-NNN)
```

## Index

| # | Status | Title |
| --- | --- | --- |
| [001](./001-stack-python-fastapi-nextjs-postgres.md) | Accepted | Stack: Python FastAPI + Next.js + PostgreSQL |
| [002](./002-llm-provider-vertex-ai.md) | Accepted | LLM provider: Google Vertex AI Model Garden |
| [003](./003-model-selection-gemini-flash-pro.md) | Accepted | Model selection: Gemini 2.5 Flash and Pro |
| [004](./004-agent-architecture-2-plus-1.md) | Accepted | Agent architecture: 2 runtime + 1 pre-interview |
| [005](./005-deterministic-orchestrator.md) | Accepted | Deterministic Python state machine orchestrator |
| [006](./006-hybrid-pre-interview-plan.md) | Accepted | Hybrid pre-interview InterviewPlan (Variant C) |
| [007](./007-pgvector-in-same-database.md) | Accepted | pgvector in same PostgreSQL, no separate vector DB |
| [008](./008-hybrid-prompt-language.md) | Accepted | English system prompts, Ukrainian candidate output |
| [009](./009-prod-only-topology.md) | Accepted | Production-only topology, no staging |
| [010](./010-docker-first-parity.md) | Accepted | Docker-first dev / CI / prod parity |
| [011](./011-feature-flags-self-hosted.md) | Accepted | Feature flags self-hosted in application database |
| [012](./012-cloud-run-traffic-splitting.md) | Accepted | Cloud Run traffic splitting as canary mechanism |
| [013](./013-no-plaintext-secrets.md) | Accepted | No plaintext secrets; Secret Manager + WIF |
| [014](./014-multi-agent-orchestration.md) | Accepted | Multi-agent orchestration is explicit, not automatic |
| [015](./015-region-europe-west1.md) | Accepted | Cloud region: europe-west1 (Belgium) |
| [016](./016-auth-split-sso-magic-link.md) | Accepted | Auth split: Workspace SSO internal, magic link candidates |
| [017](./017-spec-driven-github-spec-kit.md) | Accepted | Spec-driven development via GitHub Spec Kit |
| [018](./018-immutable-rubric-snapshots.md) | Accepted | Immutable rubric snapshots per session |
| [019](./019-append-only-audit-trail.md) | Accepted | Append-only audit trail |
| [020](./020-correctness-variant-a-mvp.md) | Accepted | Correctness evaluation: Variant A for MVP |
| [021](./021-configs-as-code.md) | Accepted | Configs as code: rubrics, prompts, flags in Git |
