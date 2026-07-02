# Feature Specification: Cloud runtime foundation — Cloud Run + Cloud SQL + Secret Manager + Artifact Registry (T06)

**Feature Branch**: `018-t06-cloud-runtime`
**Created**: 2026-07-02
**Status**: Draft
**Input**: User description: T06 — Cloud runtime foundation per `docs/engineering/implementation-plan.md` Tier 1 / W1–W2. Terraform provisions Cloud Run (backend + frontend), Cloud SQL Postgres 17 + pgvector, Secret Manager shells for every secret key in `.env.example`, Artifact Registry, runtime IAM for the backend/frontend service accounts, and fills the `<TODO-T06>` placeholders in `.github/workflows/sync-feature-flags.yml` so the T05a flag-sync workflow goes live. WIF only — no JSON keys (§5–6, ADR-013). Two environments — `dev` and `prod` — in the single GCP project; still no staging/QA/UAT gate in the release path.

## Clarifications

### Session 2026-07-02

- Q: `implementation-plan.md` T06 says "Two workspaces: dev, prod" while ADR-009 / constitution §8 / `cloud-setup.md` say production is the only long-lived environment. Which topology does T06 build? → A: **Dev + Prod** (owner's call, per the implementation-plan reading). Consequence accepted by the owner: this supersedes ADR-009 and amends constitution §8, so T06 MUST ship a new ADR (next free number, "dev + prod topology") and the §8 amendment in the same PR (constitution edits are ADR-gated), plus reconcile `cloud-setup.md`. The release-path philosophy is unchanged: no staging gate; prod releases still go out via Cloud Run revisions at 0 % traffic (ADR-012); `dev` is a long-lived development/integration environment, not a pre-release approval step.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are: the operator (Ihor) who runs the one-shot `terraform apply` and later fills secret values; every later task that deploys code (T06a `/deploy`, T11 Tier-1 smoke) or authenticates users (T07); the T05a flag-sync workflow that has been shipping inert since PR #9 and is waiting for this task's live binding; and the backend itself, whose runtime identity gains exactly the permissions it needs — nothing more. T06 delivers **infrastructure shell, identity, and data plane** for **two environments (`dev` and `prod`)** in the single GCP project — application containers arrive with T06a, SSO with T07.

### User Story 1 — Operator provisions the whole cloud runtime in one reviewed Terraform change (Priority: P1)

The operator checks out this feature branch, runs the documented pre-flight (already captured in `docs/engineering/cloud-setup.md` § Operator pre-flight), then `terraform plan` → PR review → `terraform apply` — once per environment (`dev`, then `prod`). After apply: in each environment both Cloud Run services exist and answer HTTP on their `*.run.app` URLs (placeholder container until T06a), each environment's Cloud SQL instance is up with the `techscreen` and `techscreen_shadow` databases, the shared Artifact Registry repository exists, and a repeat `terraform plan` in each environment shows an empty diff.

**Why this priority**: P1 — this is the task. Every acceptance criterion in the implementation plan (T06) maps here, and T06a/T07/T11/T16 are all blocked on it.

**Independent Test**: From the merged tree, `terraform -chdir=infra/terraform plan` shows no pending changes; `gcloud run services describe techscreen-backend --region europe-west1` returns the service; `curl` on both service URLs returns HTTP 200.

**Acceptance Scenarios**:

1. **Given** the bootstrap state (state bucket, WIF pool, budgets, backend SA) already in Terraform state, **When** the operator applies this change for each environment, **Then** each apply completes without manual console steps and a follow-up `terraform plan` reports zero resource changes in both environments.
2. **Given** the applied infrastructure, **When** anyone runs `gcloud run services describe` for the backend and frontend services of **each** environment in `europe-west1`, **Then** all four return a service with min 0 / max 5 instances, 1 vCPU / 1 GiB, and a dedicated runtime service account each.
3. **Given** the applied infrastructure, **When** the operator connects to **each** environment's Cloud SQL instance and runs `SELECT extname FROM pg_extension WHERE extname = 'vector';`, **Then** exactly one row returns in both.
4. **Given** the applied infrastructure, **When** required APIs are listed, **Then** `run`, `sqladmin`, `secretmanager`, `artifactregistry` (and error-reporting) appear as enabled — enabled by Terraform, not by hand.

---

### User Story 2 — Secrets exist as empty shells; values never touch Git (Priority: P1)

Every **secret** key from `.env.example` (`DATABASE_URL`, `MAGIC_LINK_SIGNING_KEY`, `SESSION_COOKIE_SECRET`, `SENDGRID_API_KEY`, `CALIBRATION_DATASET_KEY`) exists in Secret Manager after apply — one secret per key **per environment**, created empty, filled manually by the operator afterwards per the documented process (distinct values per environment; dev never reuses prod key material). The backend runtime identity can read exactly the secrets it consumes, granted per-secret, not project-wide. No JSON service-account key exists anywhere in the repo or the cloud project.

**Why this priority**: P1 — constitution §5–6 are the invariants most catastrophic to violate, and this story is the mechanism that makes "no secret ever lands in source" workable for prod.

**Independent Test**: `gcloud secrets list` shows all five names; `gcloud secrets get-iam-policy <name>` shows the backend SA as accessor on backend-consumed secrets only; `git grep -l keyfile.json` and gitleaks return nothing.

**Acceptance Scenarios**:

1. **Given** the applied infrastructure, **When** the operator runs `gcloud secrets list`, **Then** every secret key from `.env.example` appears **for each environment** (values empty until filled manually).
2. **Given** the secret shells, **When** the operator fills values via `gcloud secrets versions add` following the runbook, **Then** no value appears in Git history, PR text, Terraform state output, or logs.
3. **Given** the IAM bindings, **When** a reviewer inspects them, **Then** `techscreen-backend@` holds `secretAccessor` on named secrets only (no project-level grant), and the frontend SA holds none.

---

### User Story 3 — The T05a flag-sync workflow goes live (Priority: P2)

`.github/workflows/sync-feature-flags.yml` has shipped inert since T05a, guarded by `<TODO-T06>` placeholders. This task fills them: a dedicated CI identity is created for the sync job, bound to the existing `github-actions` WIF pool, granted a path to the Cloud SQL instances, and the placeholders are replaced with real values. Because flags are Configs-as-Code defaults (§16), the sync applies to **both** environments' databases. The first post-merge run on `main` performs a real upsert of `configs/feature-flags.yaml` into each environment's `feature_flag` table.

**Why this priority**: P2 — §16 Configs-as-Code has been waiting on this binding; it is the first end-to-end proof that GitHub Actions can mutate cloud state via WIF with no stored secrets. T16 (rubric sync) extends this same workflow later.

**Independent Test**: Trigger `workflow_dispatch` on `main` after apply; the Guard step reports `skip=false`, the job completes green, and `SELECT name, enabled FROM feature_flag` on **each** environment's DB returns the rows from `configs/feature-flags.yaml` with `updated_by='configs-as-code'`.

**Acceptance Scenarios**:

1. **Given** filled placeholders and applied IAM, **When** the workflow runs on `main`, **Then** the Guard step emits `skip=false` and the upsert step succeeds against the cloud instance.
2. **Given** a flag row present in DB but absent from YAML, **When** the workflow runs, **Then** the orphan is surfaced as a warning annotation and **not** deleted (T05a FR-009 preserved).

---

### User Story 4 — Cloud database is migration-ready and §3-safe from day one (Priority: P2)

Each environment's cloud database has the same role split the local stacks have: an application role that cannot `UPDATE`/`DELETE` audit tables, and a migrator role that owns DDL. The operator applies the existing Alembic chain (0001–0005) to both instances via the documented connection path, so the schema — including the §3 append-only triggers and pgvector — is live before any application container arrives.

**Why this priority**: P2 — nothing else in T06 depends on the schema being applied, but User Story 3's upsert needs the `feature_flag` table, and T11's invariant smoke (§3 trigger fires on a direct SQL attempt) needs the triggers present in the cloud DB.

**Independent Test**: `alembic upgrade head` against the cloud instance exits 0; a subsequent `UPDATE turn_trace ...` attempt as the application role raises the append-only trigger error.

**Acceptance Scenarios**:

1. **Given** the provisioned instance, **When** the operator runs the documented migration procedure, **Then** `alembic upgrade head` completes and all 12 tables + triggers exist.
2. **Given** the migrated cloud DB, **When** an `UPDATE` or `DELETE` is attempted on any of the six §3 tables as the application role, **Then** the trigger raises and the statement fails.
3. **Given** the migrated cloud DB, **When** the sync workflow (User Story 3) runs, **Then** it finds the `feature_flag` table and upserts successfully.

---

### Edge Cases

- **Postgres 17 or pgvector unavailable in `europe-west1` at provisioning time**: per ADR-001 amendment 2026-04-19, verify availability during implementation; fall back to Postgres 16 **only if blocked**, and record the fallback as an ADR-001 addendum in the same PR. Do not silently change region (ADR-015).
- **API enablement propagation**: freshly enabled services (`run`, `sqladmin`, …) can take minutes to propagate; the Terraform graph must order resources after their `google_project_service` (with `disable_on_destroy = false` so a later destroy never turns off shared APIs).
- **Apply from the wrong checkout**: shared GCS state means applying from `main` while this branch holds new HCL would plan a destroy of T01a resources. The existing warning in `cloud-setup.md` § "How to apply a change" covers this; the PR body repeats it.
- **Secret values not yet filled when a container first starts**: acceptable during T06 — the placeholder container reads no secrets. The runbook orders "fill secrets" before T06a's first real deploy.
- **DB passwords**: role passwords must not land in Git, PR text, or Terraform state in plaintext-recoverable form beyond what the state's access controls already protect; the plan phase decides the exact mechanism (out-of-band `gcloud sql users set-password` vs. Terraform-generated) and documents it.
- **Cost regression**: the new line items across both environments (2 × Cloud SQL `db-f1-micro` + PITR ≈ $18/mo, Cloud Run idle ≈ $2–4/mo) stay within the existing PLN 200 project budget; no budget resource changes in this task — but the new topology ADR MUST record the doubled baseline so the §12 interpretation stays honest.
- **`terraform destroy` safety**: both SQL instances carry deletion protection so a bad day cannot silently drop a database.
- **Cross-environment bleed**: dev identities must not be able to read prod secrets or reach the prod DB — per-secret and per-instance grants are scoped to the matching environment's SAs only.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST enable all newly required Google APIs (`run.googleapis.com`, `sqladmin.googleapis.com`, `secretmanager.googleapis.com`, `artifactregistry.googleapis.com`, `clouderrorreporting.googleapis.com`) via Terraform `google_project_service` resources with `disable_on_destroy = false`, additive to the bootstrap-enabled set.
- **FR-002**: System MUST provision an Artifact Registry Docker repository named `techscreen` in `europe-west1` to hold images for both services.
- **FR-003**: System MUST provision one Cloud SQL Postgres instance **per environment** (`dev`, `prod`; prod named `techscreen-pg`, dev name decided in plan) — target: Postgres 17; `db-f1-micro`, 10 GB SSD, daily backups with 7-day retention, PITR enabled, deletion protection on — each with databases `techscreen` and `techscreen_shadow`, in `europe-west1`, public IP with no authorised networks (access via Cloud SQL Auth Proxy / connectors only).
- **FR-004**: System MUST ensure, **per environment**, the database principals the project already assumes exist: an application role (used by the backend at runtime; subject to the §3 `REVOKE`s applied by migration 0001) and a migrator role (owns DDL) — created by the operator out-of-band, since the Cloud SQL API refuses passwordless creation (R6 amendment) — plus a Terraform-managed IAM-authenticated database user for the CI flag-sync identity. Passwords/credentials MUST NOT appear in Git, PR text, or Terraform state.
- **FR-005**: System MUST create a Secret Manager secret (empty shell, no version) for every secret key in `.env.example` — `DATABASE_URL`, `MAGIC_LINK_SIGNING_KEY`, `SESSION_COOKIE_SECRET`, `SENDGRID_API_KEY`, `CALIBRATION_DATASET_KEY` — **per environment** (naming scheme decided in plan), with values filled manually post-apply per the documented process (never in Git, never in Terraform; distinct values per environment).
- **FR-006**: System MUST provision a backend Cloud Run service **per environment** (prod named `techscreen-backend`; min 0 / max 5 instances, 1 vCPU / 1 GiB) running as a per-environment backend service account (prod reuses the existing `techscreen-backend@`), extended with `roles/cloudsql.client`, per-secret `roles/secretmanager.secretAccessor` (on that environment's backend-consumed secrets only), `roles/logging.logWriter`, and `roles/monitoring.metricWriter` (prod's SA already holds `roles/aiplatform.user` from T01a; dev's SA gets the same). Services start on a placeholder container image; Terraform MUST ignore subsequent image changes so T06a's deploy mechanism owns image rollout.
- **FR-007**: System MUST provision a frontend Cloud Run service **per environment** (prod named `techscreen-frontend`; same sizing) running as a new minimal per-environment frontend service account holding only `roles/logging.logWriter` and `roles/monitoring.metricWriter` — no SQL, no Secret Manager.
- **FR-008**: System MUST create a dedicated CI identity for the flag-sync job, bind it to the existing `github-actions` WIF pool (repository-pinned), grant it the minimum needed to reach **both** environments' Cloud SQL instances and write their `feature_flag` tables, and replace every `<TODO-T06>` placeholder in `.github/workflows/sync-feature-flags.yml` with real values so the Guard step evaluates `skip=false` and the upsert runs against both environments.
- **FR-009**: System MUST document and execute the initial schema application: the operator runs the existing Alembic chain (0001–0005) against **each** environment's instance via a documented connection procedure, and verifies the §3 append-only trigger fires on both cloud DBs.
- **FR-010**: System MUST update `docs/engineering/cloud-setup.md` to match post-T06 reality (dev + prod topology, resource inventory, Terraform layout section reconciled with the actual `infra/terraform/` layout, secret-fill runbook confirmed) and keep `.env.example` guidance accurate.
- **FR-011**: System MUST keep every existing guardrail green: `pre-commit run --all-files` (incl. gitleaks, terraform_validate, actionlint, shellcheck), CI backend/frontend/smoke jobs, and the repo-wide absence of any `keyfile.json` / service-account key material.
- **FR-012**: System MUST manage every new cloud resource in Terraform. The only permitted manual steps are the ones the runbook names explicitly: filling secret versions, setting DB role passwords (if the plan chooses the out-of-band mechanism), and running the initial migration.
- **FR-013**: System MUST ship the governance artifacts the topology decision requires, in the same PR: a new ADR ("Dev + prod topology", next free ADR number) that supersedes ADR-009 with the owner's 2026-07-02 decision and its cost/drift trade-offs; a constitution §8 amendment (via the constitution edit flow) replacing "production is the only long-lived environment" with the two-environment model while preserving the no-staging-gate release philosophy (0 %-traffic revisions, ADR-012); an `adr/README.md` index update; and the matching `docs/engineering/cloud-setup.md` rewrite (FR-010). ADR-009 gets `Status: Superseded by ADR-0XX`.

### Key Entities

- **Cloud Run services** (`techscreen-backend`, `techscreen-frontend`): the future prod runtime; shells with placeholder containers until T06a deploys real images at 0 % traffic.
- **Cloud SQL instance** (`techscreen-pg`) with databases `techscreen`, `techscreen_shadow` and the role split (app / migrator / CI-sync).
- **Secret shells**: five Secret Manager secrets mirroring `.env.example`'s secret keys; per-secret accessor grants.
- **Artifact Registry repository** (`techscreen`): image home for both services.
- **Runtime identities**: `techscreen-backend@` (extended), `techscreen-frontend@` (new, minimal), flag-sync CI identity (new, WIF-bound).
- **Live flag-sync binding**: the filled placeholders in `sync-feature-flags.yml` — the first working GitHub-Actions-to-cloud write path.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the documented apply, a repeat `terraform plan` reports **zero** pending changes (clean-diff acceptance from the implementation plan).
- **SC-002**: `gcloud run services describe` returns **all four** services (backend + frontend × dev + prod) in `europe-west1`, and an unauthenticated HTTP GET on each service URL returns **200** within 10 s (placeholder body until T06a).
- **SC-003**: `gcloud secrets list` shows **all five** secret names from `.env.example` **per environment** (ten shells); IAM policy on each backend-consumed secret names that environment's backend SA as accessor; **zero** project-level secret grants.
- **SC-004**: On **each** environment's cloud DB: `SELECT extname FROM pg_extension WHERE extname='vector'` returns **1 row**; an `UPDATE` attempt on a §3 table as the application role **fails with the trigger error**; `alembic current` reports head `0005`.
- **SC-005**: One `workflow_dispatch` run of `sync-feature-flags.yml` on `main` completes green with `skip=false`, and **each** environment's `feature_flag` table contains every YAML entry with `updated_by='configs-as-code'`.
- **SC-006**: `git grep -iE "keyfile|service.?account.*\.json"` over the tree and a gitleaks scan return **zero** secret-material hits; the cloud project has **zero** user-managed SA keys (`gcloud iam service-accounts keys list` shows only Google-managed).
- **SC-007**: The incremental monthly cost of the new resources stays within ~**$22–25** (two environments: 2 × Cloud SQL `db-f1-micro`+PITR ≈ $18, Cloud Run idle ≈ $2–4, registry/secrets < $2) — still under the PLN 200 project budget; both existing budget alerts remain untouched by this change.
- **SC-008**: The governance trail is complete: the new topology ADR is merged with `adr/README.md` indexed, ADR-009 is marked Superseded, constitution §8 reflects the two-environment model, and `git grep -n "only prod\|prod-only"` across active docs returns no stale claims.

## Assumptions

- **Topology is dev + prod** per the owner's 2026-07-02 decision (see Clarifications). Both environments live in the single GCP project `tech-screen-493720`, single region, one Terraform codebase with per-environment instantiation (mechanism — workspaces vs. tfvars — decided in plan). The governance artifacts this requires (new ADR superseding ADR-009, constitution §8 amendment) ship in this PR (FR-013). The release path keeps its no-staging-gate shape: prod deploys still verify via 0 %-traffic revisions (ADR-012); `dev` is for development/integration, not a mandatory pre-release approval step.
- The one-shot bootstrap (state bucket, `terraform` SA, `github-actions` WIF pool, budgets, `techscreen-backend@` SA) is done and in state — verified 2026-07-02 (`terraform state list` shows the six T01a-era resources).
- The operator applies from this branch's checkout, with the ADC/billing pre-flight from `cloud-setup.md` already satisfied on this machine.
- Application containers are **out of scope**: services start on a placeholder image; the first real image build/push/deploy belongs to T06a (`/deploy` at 0 % traffic). "Cloud Logging + Error Reporting wired" at T06 means: APIs enabled, runtime SAs hold `logging.logWriter`/`monitoring.metricWriter`, and structured-JSON stdout (already the app's log format) is the transport — no extra log infrastructure is provisioned.
- Monitoring dashboards and alert policies beyond the existing T01a budget alerts are **T38**, not T06.
- The `<project>-techscreen-assets` bucket in the cloud-setup inventory has no consumer before Tier 6; it is deferred to the task that first needs it (kept out of T06 to avoid speculative infrastructure).
- Sequential single-agent execution (repo default); `infra-engineer` profile work, one PR.

## Out of scope

- `/deploy`, `/promote`, `/rollback` automation and the first real image rollout — **T06a**.
- Identity Platform SSO, role claims, `docs/contracts/id-token-claims.json` — **T07**.
- The rubric half of Configs-as-Code sync (second job in the same workflow) — **T16**.
- Monitoring dashboards, alert policies, Slack routing — **T38**.
- Custom domain, VPC Connector / private IP, VPC Service Controls, WAF, CMEK — explicitly "not set up" per `cloud-setup.md`; each needs its own ADR when the pilot graduates.
- Any change to migration content, `configs/feature-flags.yaml` semantics, or application code (beyond none being expected).

## Plan-phase research items (handle in `plan.md` / `research.md`)

- **PG17 + pgvector availability check** in `europe-west1` on `db-f1-micro` (shared-core) — and whether the `cloudsql.enable_pgvector` database flag from the implementation plan text is still a real/required flag on current Cloud SQL Postgres, or whether `CREATE EXTENSION vector` (already in migration 0001) suffices.
- **DB credential mechanism**: Terraform `random_password` (lands in state — evaluate acceptability given state-bucket ACLs) vs. out-of-band `gcloud sql users set-password` by the operator (nothing in state; one more manual step). Recommendation expected in `research.md`.
- **IAM DB auth for the flag-sync identity**: exact Cloud SQL IAM-user name format for an SA when the proxy runs `--auto-iam-authn` (the workflow currently says `DATABASE_USER: techscreen_migrator` — reconcile: the sync should not run as the migrator).
- **Placeholder image choice** for the Cloud Run shells (e.g., Google-provided hello image) + the Terraform `lifecycle ignore_changes` shape that hands image ownership to T06a.
- **Per-environment instantiation mechanism**: Terraform **workspaces** (implementation-plan wording) vs. per-env tfvars/directories — pick one; existing T01a resources (budgets, backend SA) live in the current default-workspace state, so the migration path for state layout must be explicit and non-destructive. Keep the GCS state bucket; decide prefixes.
- **Environment naming convention**: prod keeps the documented names (`techscreen-backend`, `techscreen-pg`, secret names as listed); dev resources need a suffix/prefix scheme (`-dev`) applied consistently across services, SAs, SQL instances, and secrets. Cloud Run names are unique per project+region, so collisions are structural, not stylistic.
- **Sync-workflow fan-out shape**: matrix job over `dev`/`prod` vs. sequential steps; failure isolation (one env failing must not mask the other — mirrors T16's "failure of one does not block the other" rule).
- **Cloud Run ingress + auth posture at T06**: public URL with placeholder is harmless; decide whether to restrict ingress until T06a deploys real images.
- **Ordering/dependency graph**: `google_project_service` → SQL instance → databases/users → secrets → IAM → Cloud Run, with API-propagation timing handled.
