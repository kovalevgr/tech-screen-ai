# ADR-011: Feature flags self-hosted in application database

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

Given prod-only topology (ADR-009) and dark-launch-by-default (constitution §9), we need a first-class feature flag system. Options:

1. **Managed SaaS** — LaunchDarkly, Flagsmith (hosted), ConfigCat.
2. **Self-hosted OSS** — Flagsmith self-hosted, Unleash.
3. **Simple DB table + library** — flags stored in our own Postgres, with a small SDK.

A managed SaaS adds another vendor, billing line, and credential to manage for a feature we can implement in ~200 LOC. An OSS self-hosted solution is another service to run. For MVP scale (small handful of flags, small handful of engineers) this is over-engineering.

## Decision

Feature flags are rows in a `feature_flag` table in the application database. The schema:

```
feature_flag (
  key         TEXT PRIMARY KEY,   -- e.g. 'interviewer.streaming_response'
  enabled     BOOLEAN NOT NULL DEFAULT false,
  owner       TEXT NOT NULL,
  description TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

A small `FeatureFlags` service caches flags in-process with a 30-second TTL. Admin UI exposes flip-on / flip-off per flag with audit logging.

`configs/feature-flags.yaml` is the source of truth for **default values**; DB rows override defaults at runtime; changes in the DB are promoted back to the YAML as part of the weekly config review.

## Consequences

**Positive.**

- Zero external dependency for a critical part of our safety story.
- Cost: $0.
- Flag flips are auditable in our own `audit_log` alongside everything else.
- Aligns with configs-as-code (ADR-021).

**Negative.**

- No advanced targeting (percent rollouts per user, segment targeting). We do not need these at MVP — Cloud Run traffic splitting (ADR-012) handles percentage rollouts.
- If the application DB is down, flags are down. This is acceptable because if the DB is down, the system is down anyway.

**Mitigation.**

- The flag library falls back to `configs/feature-flags.yaml` defaults if the DB query fails, never returning "flag unknown" to the caller.
