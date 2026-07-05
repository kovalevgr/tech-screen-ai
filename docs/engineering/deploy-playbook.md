# Deploy Playbook

How TechScreen ships code. Two long-lived environments — `dev` and `prod` — exist (ADR-023), but there is no staging gate in the release path. Safety comes from Docker parity, traffic splitting, and explicit human approval at the migration checkpoint.

Since T06a the three verbs are **implemented** as GitHub Actions `workflow_dispatch` workflows, WIF-authenticated as `techscreen-deployer@` (no JSON keys, no stored secrets — constitution §5–6). "Run `/deploy`" means "dispatch the workflow"; the exact invocations are below.

Related: [ADR-023](../../adr/023-dev-prod-environments.md), [ADR-010](../../adr/010-docker-first-parity.md), [ADR-012](../../adr/012-cloud-run-traffic-splitting.md), [constitution §8, §10, §19](../../.specify/memory/constitution.md), [specs/020-t06a-deploy-commands/](../../specs/020-t06a-deploy-commands/) (design + research D1–D12).

---

## Mental model

Every deploy is a new Cloud Run revision at **0% traffic**. A human shifts traffic from the old revision to the new one in stages: 0 → 10 → 50 → 100. Rollback is a single command that shifts all traffic back to the previous revision; the problematic revision is kept but receives no requests.

```
   main (merged PR)
        │
        ▼
  gh workflow run deploy.yml -f env=<env> -f service=both -f git_ref=main
        │
        ├─► gate: prod-ancestry ▪ §10 migration label ▪ Cloud SQL awake?
        ├─► build `runtime` image (linux/amd64) ──► push <sha>-<env> to Artifact Registry
        ├─► cloud run deploy --no-traffic  (revision R+1 at 0%)
        ├─► move `candidate` tag to R+1
        └─► HTTP smoke at R+1's tag URL (≤60s)
              │
              ▼
  gh workflow run promote.yml  -f env=<env> -f service=both -f percent=10
  (observe ≥10 minutes, watch dashboards)
              │
              ▼
  … -f percent=50 … -f percent=100
              │
  rollback at any step:
  gh workflow run rollback.yml -f env=<env> -f service=both
```

Migrations are **not** in this pipeline — see § Migrations below.

---

## Prerequisites

Before `/deploy` will do anything useful:

1. The PR is merged to `main` (for prod this is machine-enforced: the gate rejects refs not reachable from `origin/main`; `dev` accepts any ref — it is the rehearsal environment).
2. CI on the ref is green (lint, backend, frontend, smoke).
3. The dispatcher has **write access to the repository** — that is the MVP's `techscreen-deployers` group; GitHub records who dispatched what, with which inputs.
4. If the ref carries migrations: the PR has the `migration-approved` label (see § Migration approval) **and** the operator has applied the SQL to the target environment's DB.
5. If a deploy step needs the database (see § Cost-idle mode): the target instance is awake.
6. Calibration report, if present, has been read by the operator. Calibration regressions are warning-only but the operator owns the call.

---

## `/deploy` — build, deploy at 0%, smoke

```bash
gh workflow run deploy.yml -f env=dev  -f service=both -f git_ref=main   # dev
gh workflow run deploy.yml -f env=prod -f service=both -f git_ref=main   # prod
# service: backend | frontend | both
```

Steps, in order (all in `.github/workflows/deploy.yml`; failure stops the pipeline and leaves serving traffic untouched):

### Gate job

- **Prod ancestry**: `env=prod` requires the resolved SHA to be an ancestor of `origin/main`.
- **§10 migration gate**: diffs `alembic/versions/**` between the *currently deployed* backend image's git SHA (parsed from its `<sha>-<env>` tag; falls back to `origin/main~1` while the placeholder image is serving) and the target ref. Every migration-touching commit must belong to a PR carrying the `migration-approved` label — otherwise the run fails naming files, commits, and PRs. `/deploy` never applies migrations; the gate checks *approval*.
- **Cost-idle guard**: reads the target instance's `state`/`activationPolicy`. Asleep + a deploy step that needs the DB → hard fail with `run scripts/cloud-sql-power.sh wake <env>`. Asleep + nothing needs it (today's reality: the backend template does not wire `DATABASE_URL` yet) → notice, continue.

### Deploy job (per service)

- Build the committed **`runtime`** Dockerfile target for `linux/amd64` — the same image dev and CI run (ADR-010). Frontend builds receive `NEXT_PUBLIC_API_BASE_URL` (the env's live backend URL) and `NEXT_PUBLIC_APP_ENV` as build args, so frontend images are env-specific.
- Push to `europe-west1-docker.pkg.dev/tech-screen-493720/techscreen/<service>:<full-git-sha>-<env>` — immutable by convention; the tag is how the migration gate later recovers the deployed baseline.
- `gcloud run deploy --no-traffic --port <8000|3000> --revision-suffix <sha>-<run>` — new revision at 0%; **only the image and container port change** (env vars, secrets, scaling, service accounts stay Terraform-owned; backend port 8000, frontend 3000).
- Move the **`candidate`** revision tag to the new revision; its URL (`https://candidate---<service>-<hash>.run.app`) is the smoke surface.
- **Smoke** (≤60 s): backend `GET /health` must return 200 with `"status":"ok"`; frontend `GET /` must return 200. Failure blocks nothing that serves traffic — the revision just stays dark. **Failure blocks `/promote`** by policy: do not promote a revision whose smoke failed.
- **Job summary**: revision name, image tag, candidate URL, smoke verdict — the run page is the deploy record.

> **Known gap until the env-wiring follow-up lands** (specs/020 research D12): the T06 Cloud Run template sets no env vars, and the backend `runtime` image refuses to start as `APP_ENV=prod` + `LLM_BACKEND=mock` — so the first *backend* deploy fails its readiness probe by design-of-the-guard, loudly. Frontend deploys are unaffected. The fix is a small Terraform change to the environment module (`LLM_BACKEND=vertex`, `DATABASE_URL` secret ref, Cloud SQL attachment), tracked as a named follow-up.

---

## `/promote <percent>` — shift traffic gradually

```bash
gh workflow run promote.yml -f env=prod -f service=both -f percent=10
gh workflow run promote.yml -f env=prod -f service=both -f percent=50
gh workflow run promote.yml -f env=prod -f service=both -f percent=100
```

The workflow resolves the service's **latest ready revision by name** and pins it at the requested percent (`update-traffic --to-revisions=<name>=<pct>`); the remainder redistributes across currently-serving revisions. It never leaves a floating `LATEST` allocation — a later deploy can never silently take live traffic. If a newer revision exists but failed (not ready), the summary warns and the ready one is promoted. Promoting `<100%` when only one revision serves traffic fails (deploy first). The summary shows the before/after split.

### After `/promote 10`

Observe for **at least 10 minutes** before going higher:

- Error rate in Cloud Monitoring (target: no deviation from previous 24h baseline).
- p95 latency (target: within 20% of baseline).
- LLM cost per session (target: within 20% of baseline).
- Feature-flag-gated code paths, if any new flag was introduced.

### After `/promote 50`

Same checks. Because the candidate population is small, 50% may still be only a handful of live sessions — confirm at least one or two completed sessions before moving on.

### After `/promote 100`

- The previous revision is now at 0% and becomes the rollback target.
- Revision cleanup is **not implemented yet** (see § Not yet implemented); old revisions accumulate harmlessly at 0%.

---

## `/rollback` — one-command recovery

```bash
gh workflow run rollback.yml -f env=prod -f service=both
# escape hatch when the auto-detection is wrong:
gh workflow run rollback.yml -f env=prod -f service=backend -f revision=<revision-name>
```

The workflow:

1. Identifies the current primary (highest traffic percent) and the **previous serving revision** — the newest *ready* revision older than the primary; failed deploys are skipped automatically. An explicit `revision` input overrides the heuristic (readiness-verified).
2. Runs one `gcloud run services update-traffic --to-revisions=<previous>=100` call, **wall-clock measured**; the summary reports the duration against the ≤60 s working target (ADR-012) and the §19 five-minute ceiling.
3. **Preempts**: rollback shares the `cloud-run-<env>` concurrency group with deploy/promote and cancels whatever is in flight — recovery never queues behind a half-finished deploy.

**Rollback does NOT reverse migrations.** Forward-only migration policy (constitution §10) means the schema is additive; a new revision must keep working against a newer schema. If the only fix requires a schema reversal, treat it as a new forward migration and deploy normally.

---

## What rollback cannot do

- Undo data written during the bad window (e.g., `turn_trace` rows with bad model output). These stay in the audit log; they are flagged via an `assessment_correction` pass once the bug is identified.
- Undo a feature flag being flipped to `true`. Flag state is in the DB and should be flipped back via the flag admin route or a direct migration.
- Undo a secret rotation. If the deploy included a Secret Manager secret update, the new secret stays; the old revision will use the new secret value.

---

## Migrations — operator-run, label-gated

Per constitution §10, no migration applies without explicit human approval of the dry-run SQL. Since T10+T06a the mechanics are:

1. **On the PR**: CI (`ci.yml` migration-sql-render job) renders `alembic upgrade head --sql` and posts it as a PR comment. A human reviews it and applies the **`migration-approved` label**. Destructive DDL auto-gets `needs-adr` and additionally requires a linked ADR.
2. **At deploy time**: the `/deploy` gate refuses any ref whose migration-touching commits lack the label (see above). This is enforcement of *approval*, not application.
3. **Application is manual**: the operator wakes the instance, sets a fresh migrator password (rotate-on-demand — see the password-hygiene note in `specs/018-t06-cloud-runtime/quickstart.md` §4), and runs `alembic upgrade head` through the Cloud SQL Auth Proxy (`specs/018-t06-cloud-runtime/quickstart.md` §6), then discards the password. CI never holds DDL credentials — argued in `specs/020-t06a-deploy-commands/research.md` D2.

Order for a migration-carrying release: label on PR → merge → **apply SQL to the target env** → `/deploy` → smoke → ramp. Additive-only migrations (§10) are what make the old revision safe while the new schema is already live.

### What the reviewer checks before labelling

- Does the DDL match the changes in the PR?
- Is any statement destructive (`DROP`, `TRUNCATE`, type narrowing, `NOT NULL` on an existing populated column with no default)? If destructive: is there a linked ADR with a rollback plan?
- Does the migration use forward-compatible patterns (add column → dual-write → backfill → remove reads → drop in a later PR)?
- Is the expected runtime acceptable for the dataset size?

---

## Cost-idle mode — wake the database first

Both Cloud SQL instances are kept **stopped** (`activationPolicy=NEVER`) between work sessions to keep the ~$18/mo baseline near zero. The lever:

```bash
scripts/cloud-sql-power.sh status dev|prod
scripts/cloud-sql-power.sh wake   dev|prod
scripts/cloud-sql-power.sh sleep  dev|prod
```

**Who needs the DB awake:**

| Consumer | Needs awake DB? |
| --- | --- |
| `/deploy` build + push + traffic steps | never |
| backend revision startup | **yes, once `DATABASE_URL` is wired** into the Cloud Run template (the deploy gate detects this and fails with the wake instruction) |
| frontend anything | never |
| operator-run migrations | always |
| `sync-feature-flags.yml` | always |

Waking is deliberately human-only: the CI deployer identity holds `roles/cloudsql.viewer` (read state, cannot patch). Remember to `sleep` the instance when the session ends.

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
- **No deploys during a live session** — operator judgment at MVP; the automated drain check is not implemented yet (see below).

---

## Post-deploy checklist

For five minutes after `/promote 100`, the operator:

- Watches the error dashboard tab.
- Watches the LLM cost dashboard tab (a regression here is a 10x bill risk).
- Watches `turn_trace` for a spike in `error_code` rows.
- Confirms at least one end-to-end session completed on the new revision (candidate side + assessor + reviewer view) — once sessions exist.
- Posts a short note to `#techscreen-deploys` Slack (or email to a small internal list at MVP): revision, change summary, observed state.

---

## When things go wrong mid-promote

| Symptom                                              | Action                                                                        |
| ---------------------------------------------------- | ----------------------------------------------------------------------------- |
| Error rate spikes at 10%                             | `/rollback` immediately. Do not investigate first — the spike is the signal.  |
| p95 latency up, error rate flat                      | Hold at current %, investigate. Rollback if unresolved in 10 minutes.         |
| LLM cost per session doubled                         | Hold at 10%, check for a prompt regression. Rollback if confirmed.            |
| Smoke passed but a specific feature broken           | `/rollback`. File issue. Do not try to hotfix under traffic.                  |
| Candidate session stuck in `SESSION_PAUSED_UPSTREAM` | Check Vertex status dashboard. If Vertex is fine, rollback.                   |

The rule: **if in doubt, rollback.** Rollback is a minute; a bad hour under traffic is data loss and candidate-trust loss.

---

## Auditability

At MVP the deploy record is **the workflow run history**: GitHub retains who dispatched each run, the inputs (`env`, `service`, `git_ref`/`percent`/`revision`), and the job summary (revision names, image tags, smoke verdicts, traffic splits, measured rollback duration). Cloud Run's revision list is the second ledger — every revision carries its image tag, which embeds the git SHA.

The `deploys` audit table described in earlier versions of this playbook is **deferred** (see below); its query patterns ("all rollbacks ever", "deploys with failed smoke") are served by filtering workflow runs until then.

---

## Not yet implemented (deliberate MVP gaps)

| Item | Status |
| --- | --- |
| `deploys` audit table in Postgres | deferred — lands with the first backend task that owns ops tables |
| ChatOps trigger (`/deploy` typed in a PR comment) | deferred — `gh workflow run` is the invocation; comment-parsing is an injection surface we skip (specs/020 research D1) |
| `/deploy cleanup` (prune revisions older than two deploys) | deferred — 0% revisions are harmless; ADR-012's 7-day cleanup job is future work |
| Live-session drain check before deploy | deferred — no live sessions exist yet; operator judgment until then |
| Migration auto-apply from CI | **rejected**, not deferred — see specs/020 research D2 (§5/§6: CI must not hold DDL credentials) |
| Backend env wiring (`LLM_BACKEND`, `DATABASE_URL`, Cloud SQL attachment) in the Cloud Run template | named follow-up in the environment module — until then the first backend deploy fails readiness (loudly, at 0% traffic) |

---

## Ownership

- **Deployer role**: at MVP, repository write access = permission to dispatch the three workflows; the cloud side is always the least-privilege `techscreen-deployer@` SA regardless of who dispatches. (The `techscreen-deployers` SSO group binding arrives with T07.)
- **Migration reviewer**: on the PR that introduces a migration, a second maintainer reviews the rendered SQL and applies `migration-approved` (or the `reviewer` sub-agent blocks).
- **Post-incident writer**: whoever runs `/rollback` owns the incident note within 24 hours.

---

## Document versioning

- v2.0 — 2026-07-05 — T06a: descriptive → implemented. Exact workflow invocations (`deploy.yml`/`promote.yml`/`rollback.yml`), §10 gate mechanics (label check at deploy time; application operator-run), cost-idle wake rule + `scripts/cloud-sql-power.sh`, pinned-revision traffic semantics, preempting rollback, auditability via run history, honest not-yet-implemented table.
- v1.0 — 2026-04-18.
- Update this file when: traffic-shift percentages change, a new deploy gate is introduced, the migration-approval mechanism changes, or tooling shifts off Cloud Run.
