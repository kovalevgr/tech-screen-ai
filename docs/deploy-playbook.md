# Deploy Playbook

How TechScreen ships code to production. The only long-lived environment is `prod`; there is no staging. Safety comes from Docker parity, traffic splitting, and explicit human approval at the migration checkpoint.

Related: [ADR-009](../adr/009-prod-only-topology.md), [ADR-010](../adr/010-docker-first-parity.md), [ADR-012](../adr/012-cloud-run-traffic-splitting.md), [constitution §8, §10, §19](../.specify/memory/constitution.md).

---

## Mental model

Every deploy is a new Cloud Run revision at **0% traffic**. A human shifts traffic from the old revision to the new one in stages: 0 → 10 → 50 → 100. Rollback is a single command that shifts all traffic back to the previous revision; the problematic revision is kept but receives no requests.

```
   main (merged PR)
        │
        ▼
  /deploy
        │
        ├─► build image
        ├─► push to Artifact Registry
        ├─► alembic dry-run SQL  ──► human approves ──► alembic upgrade head
        ├─► cloud run deploy --no-traffic (revision R+1 at 0%)
        └─► smoke tests at R+1
              │
              ▼
  /promote 10  ─► 10% of live traffic on R+1
  (observe 10 minutes, watch dashboards)
              │
              ▼
  /promote 50  ─► 50% of live traffic on R+1
              │
              ▼
  /promote 100 ─► 100%; R becomes the previous revision
```

Rollback at any step: `/rollback` → 100% to the previous healthy revision.

---

## Prerequisites

Before `/deploy` will do anything:

1. The PR is merged to `main`.
2. CI on `main` is green (lint, unit, integration, contract, E2E, reviewer agent).
3. The operator has permission to shift Cloud Run traffic (recruiter SSO group `techscreen-deployers`).
4. Calibration report, if present, has been read by the operator. Calibration regressions are warning-only but the operator owns the call.

---

## `/deploy` — build, migrate, deploy at 0%

The `/deploy` command runs the following steps in order. Each step logs to the operator's terminal and to the `deploys` audit table. A failure stops the pipeline and leaves production untouched.

### Step 1 — Preflight

- Confirm the operator is on `main` at the expected SHA.
- Confirm no uncommitted changes.
- Confirm Vertex, Cloud SQL, Secret Manager are reachable (fail fast if a dependency is down).

### Step 2 — Image build

- Build `backend` and `frontend` images using the committed `Dockerfile`s.
- Tag: `europe-west1-docker.pkg.dev/<project>/techscreen/<service>:<short-sha>`.
- Push to Artifact Registry.

### Step 3 — Migration dry-run

- Generate the SQL that `alembic upgrade head` would run against the current prod database.
- Print it to the terminal with diff highlighting.
- **Prompt the operator for explicit approval** before applying. This is the constitution §10 checkpoint.
- If the migration includes destructive DDL without an ADR link in the commit body, the command refuses (anti-patterns.md).

### Step 4 — Migration apply

- Run `alembic upgrade head` against the prod database.
- Capture the new revision in `schema_migrations`.
- On failure: the pipeline halts. The operator must either fix forward or manually roll back the migration.

### Step 5 — Cloud Run revision at 0%

- `gcloud run deploy techscreen-backend --image ... --no-traffic --revision-suffix=<short-sha>`.
- Same for `techscreen-frontend`.
- New revisions are live but receive no user traffic.

### Step 6 — Smoke tests

- A minimal suite (see `docs/testing-strategy.md` §7) runs against the new revision's direct URL.
- Health check, one synthetic session, Secret Manager read, feature flag read.
- Budget: < 60 seconds.
- **Failure blocks `/promote`.** The operator may investigate via logs and either fix-forward (new deploy) or abandon (revision stays at 0%).

At the end of `/deploy` the operator is told:

> Revision `techscreen-backend-00042-abc` is live at 0% traffic. Smoke passed. Ready for `/promote 10`.

---

## `/promote <percent>` — shift traffic gradually

`/promote 10`, `/promote 50`, `/promote 100` each shift the percentage of live traffic to the latest deployed revision.

### After `/promote 10`

Observe for **at least 10 minutes** before going higher:

- Error rate in Cloud Monitoring (target: no deviation from previous 24h baseline).
- p95 latency (target: within 20% of baseline).
- LLM cost per session (target: within 20% of baseline).
- Feature-flag-gated code paths, if any new flag was introduced.

### After `/promote 50`

Same checks. Because the candidate population is small, 50% may still be only a handful of live sessions — the operator should confirm at least one or two completed sessions before moving on.

### After `/promote 100`

- The previous revision is now at 0% and becomes the rollback target.
- The operator runs `/deploy cleanup` to prune revisions older than two deploys back (keeps the last two for rollback; older ones are deleted).
- A line is appended to `deploys` table marking the deploy complete.

---

## `/rollback` — one-command recovery

`/rollback` shifts 100% of traffic to the previous healthy revision. It:

1. Reads the last entry in `deploys` where traffic_percent = 100 and status = success before the current one.
2. Runs `gcloud run services update-traffic techscreen-<service> --to-revisions=<prev>=100`.
3. Logs the rollback to `deploys` with a link to the incident channel.
4. Completes in under a minute from invocation.

**Rollback does NOT reverse migrations.** Forward-only migration policy (constitution §10) means the schema is additive; a new revision must keep working against a newer schema. If the only fix requires a schema reversal, treat it as a new forward migration and deploy normally.

---

## What rollback cannot do

- Undo data written during the bad window (e.g., `turn_trace` rows with bad model output). These stay in the audit log; they are flagged via an `assessment_correction` pass once the bug is identified.
- Undo a feature flag being flipped to `true`. Flag state is in the DB and should be flipped back via the flag admin route or a direct migration.
- Undo a secret rotation. If the deploy included a Secret Manager secret update, the new secret stays; the old revision will use the new secret value.

---

## Migration approval — the human checkpoint

Per constitution §10, no migration applies without explicit operator approval of the dry-run SQL. This is the single place where automation is not allowed to proceed without a human.

### What the operator checks

- Does the DDL match the changes in the PR?
- Is any statement destructive (`DROP`, `TRUNCATE`, type narrowing, `NOT NULL` on an existing populated column with no default)?
- If destructive: is there a linked ADR explaining why and what the rollback plan is?
- Does the migration use forward-compatible patterns (add column → dual-write → backfill → remove reads → drop in a later PR)?
- Is the expected runtime acceptable for the dataset size?

### When the operator rejects

- `Ctrl-C` or answer `no` to the prompt.
- The pipeline stops. No Cloud Run revision is created.
- The operator opens an issue and assigns the migration author.

---

## Feature flag promotion

Feature flags default to `false` on creation (ADR-011 / constitution §9). A typical launch path:

1. Deploy code behind flag `false`. Verified via staging-free dark test in prod (the code runs for flag-on users only, default none).
2. Enable for the `techscreen-internal` audience (N-iX employees) via the flag admin route or a seed migration.
3. Monitor for 24 hours.
4. Enable for a small candidate percentage (e.g., 10% via flag variant).
5. Enable for all candidates.

Flag flips are audited in `audit_log` with the operator identity.

---

## Deploy cadence

- **Working hours, weekdays:** preferred window for all deploys.
- **Off-hours:** permitted for hotfixes only; on-call notified in advance.
- **Fridays after 4pm local time:** avoid unless it is a live incident fix.
- **No deploys during a live session.** The deploy command refuses if any `interview_session` is in an active state (not `COMPLETED`, `HALTED`, or `CANCELLED`). A 2-minute drain window is enforced.

---

## Post-deploy checklist

For five minutes after `/promote 100`, the operator:

- Watches the error dashboard tab.
- Watches the LLM cost dashboard tab (a regression here is a 10x bill risk).
- Watches `turn_trace` for a spike in `error_code` rows.
- Confirms at least one end-to-end session completed on the new revision (candidate side + assessor + reviewer view).
- Posts a short note to `#techscreen-deploys` Slack (or email to a small internal list at MVP): revision, change summary, observed state.

---

## When things go wrong mid-promote

| Symptom                                              | Action                                                                       |
| ---------------------------------------------------- | ---------------------------------------------------------------------------- |
| Error rate spikes at 10%                             | `/rollback` immediately. Do not investigate first — the spike is the signal. |
| p95 latency up, error rate flat                      | Hold at current %, investigate. Rollback if unresolved in 10 minutes.        |
| LLM cost per session doubled                         | Hold at 10%, check for a prompt regression. Rollback if confirmed.           |
| Smoke passed but a specific feature broken           | `/rollback`. File issue. Do not try to hotfix under traffic.                 |
| Candidate session stuck in `SESSION_PAUSED_UPSTREAM` | Check Vertex status dashboard. If Vertex is fine, rollback.                  |

The rule: **if in doubt, rollback.** Rollback is a minute; a bad hour under traffic is data loss and candidate-trust loss.

---

## Auditability

Every deploy and every traffic shift creates a row in `deploys`:

- `id`, `revision_id`, `image_sha`, `git_sha`.
- `operator_email` (from Workspace SSO).
- `traffic_percent` at each step.
- `migration_applied` (bool), `migration_sql_hash`.
- `smoke_passed` (bool).
- `rolled_back_at`, `rolled_back_by` (nullable).
- `created_at`.

Queries we run from this table:

- "All deploys in the last 7 days" — weekly review.
- "All rollbacks ever" — incident catalogue.
- "Deploys with failed smoke" — reliability trend.

---

## Ownership

- **Deployer role** (N-iX group `techscreen-deployers`): can run `/deploy`, `/promote`, `/rollback`.
- **Migration reviewer**: on the PR that introduces a migration, a second maintainer approves or the `reviewer` sub-agent blocks.
- **Post-incident writer**: whoever runs `/rollback` owns the incident note within 24 hours.

---

## Document versioning

- v1.0 — 2026-04-18.
- Update this file when: traffic-shift percentages change, a new deploy gate is introduced, the migration-approval mechanism changes, or tooling shifts off Cloud Run.
