# Cloud Setup

How TechScreen uses Google Cloud. Single project, single region, **two long-lived environments (`dev` + `prod`)**, Terraform-managed after a one-shot manual bootstrap. Everything here is written so a new engineer can reconstruct the topology end-to-end.

Related: [ADR-023](../../adr/023-dev-prod-environments.md) (supersedes [ADR-009](../../adr/009-prod-only-topology.md)), [ADR-012](../../adr/012-cloud-run-traffic-splitting.md), [ADR-013](../../adr/013-no-plaintext-secrets.md), [ADR-015](../../adr/015-region-europe-west1.md), [constitution §5, §6, §8 (v1.1)](../../.specify/memory/constitution.md).

---

## Project layout

- **GCP project:** one, owned by N-iX. Project number `463244185014`. Human-readable project ID confirmed via Cloud Console ("Project info" card). Billing attached to the N-iX billing account for TechScreen.
- **Region:** `europe-west1` (Belgium). All regional resources live there. See ADR-015.
- **Environments:** `dev` and `prod`, both in this project, both instantiated from the same Terraform module (`infra/terraform/modules/environment/`) — structural drift is impossible by construction (ADR-023). **No staging, and no environment gate in the release path**: prod releases are verified via Cloud Run revisions at 0% traffic (ADR-012), never by "passing dev". Local dev + CI still run against Docker Compose with `LLM_BACKEND=mock`; see `docs/engineering/docker.md`.
- **Naming:** prod keeps canonical names (`techscreen-backend`, `techscreen-pg`, secret `DATABASE_URL`); dev appends `-dev` to resources and `_DEV` to secret names.

---

## Resource inventory

| Resource                                           | Purpose                                            | Size / tier                            |
| -------------------------------------------------- | -------------------------------------------------- | -------------------------------------- |
| Cloud Run `techscreen-backend` / `-dev`            | FastAPI API (per env)                              | min 0, max 5 instances, 1 vCPU / 1 GiB |
| Cloud Run `techscreen-frontend` / `-dev`           | Next.js SSR (per env)                              | min 0, max 5 instances, 1 vCPU / 1 GiB |
| Cloud SQL PG17 `techscreen-pg` / `-dev`            | App DB + pgvector (per env)                        | `db-f1-micro`, 10 GB SSD, PITR on      |
| Cloud SQL databases `techscreen`, `techscreen_shadow` | Application schema + Alembic autogenerate target | per instance                           |
| Secret Manager (10 shells)                         | 5 secret keys × 2 envs (`_DEV` suffix for dev)     |                                        |
| Artifact Registry `techscreen`                     | Docker images, both services, both envs (tag-level separation) | `europe-west1`             |
| Cloud Storage bucket `<project>-tfstate`           | Terraform remote state                             | versioned, 30-day lifecycle            |
| Cloud Monitoring workspace                         | Dashboards, alert policies (T38)                   |                                        |
| Cloud Logging                                      | All services                                       | 30-day retention                       |
| IAM Workload Identity Pool `github-actions`        | CI auth via OIDC (terraform SA + flag-sync SA)     |                                        |

*(The formerly listed `<project>-techscreen-assets` bucket is deferred until a task actually consumes it — see `specs/018-t06-cloud-runtime/` Assumptions.)*

Vertex AI is accessed as a managed API (no dedicated resource is provisioned). Granted per-model rate quotas, region verification, and the smoke-test record live in [`docs/engineering/vertex-quota.md`](./vertex-quota.md), seeded by T01a.

---

## Rough monthly cost

For the MVP pilot volume (≤ 50 completed sessions / month), across **both** environments (ADR-023 doubled the infra baseline):

| Line item                                        | Approx USD/mo  |
| ------------------------------------------------ | -------------- |
| Cloud Run (4 services, mostly idle)              | $2 – $4        |
| Cloud SQL `db-f1-micro` + 10 GB + PITR × 2       | $18            |
| Artifact Registry storage                        | negligible     |
| Cloud Storage (state)                            | < $1           |
| Secret Manager                                   | < $1           |
| Vertex AI (Gemini 2.5 Flash/Pro)                 | $4 – $10       | (full quota state in [`vertex-quota.md`](./vertex-quota.md)) |
| Total                                            | **~$26 – $34** | |

**Two budget alerts** are configured (T01a, declared in `infra/terraform/billing.tf`):

1. **Project-wide budget — PLN 200/mo (≈ $50)** (constitution §12 hard cap, interpreted as "approximately $50" because the billing account is denominated in PLN — see `specs/003-vertex-quota-region/spec.md` Clarifications 2026-04-26 Q on currency), with notifications at 50 / 90 / 100 %.
2. **Vertex-only budget — PLN 80/mo (≈ $20)** scoped to `aiplatform.googleapis.com` (Clarifications 2026-04-24 Q5 — early warning that isolates LLM-side spikes from general infra drift), with notifications at 50 / 90 / 100 %.

Both budgets target a single Cloud Monitoring email channel: **Ihor's personal N-iX mailbox** (the value of `ops_email` in `infra/terraform/terraform.tfvars`). This is the MVP arrangement per Clarifications 2026-04-24 Q1; see Follow-ups in [`vertex-quota.md`](./vertex-quota.md) for the swap-to-group-alias item.

---

## Bootstrap — one-off manual steps

A chicken-and-egg problem: Terraform needs a GCS bucket for state, and service-account auth, both of which we want Terraform to manage. We solve it by creating the absolute minimum by hand.

`infra/bootstrap.sh` handles all of this idempotently. It:

1. Enables required APIs: `cloudresourcemanager`, `iam`, `iamcredentials`, `serviceusage`, `storage`, `sts` (Terraform-itself prerequisites), plus `aiplatform`, `billingbudgets`, `monitoring` (needed by T01a's Vertex smoke test, billing-budget resources, and notification channels — see `specs/003-vertex-quota-region/`).
2. Creates the GCS state bucket `<project>-tfstate` with versioning on and a 30-day delete lifecycle on old versions.
3. Creates the `terraform` service account with `roles/owner` (MVP — to be tightened after the project stabilises).
4. Creates a Workload Identity Pool `github-actions` and an OIDC provider with attribute condition `attribute.repository == '<owner>/<repo>'`.
5. Binds the GitHub repository to impersonate the `terraform` SA.

Run it once, as the project owner, from a laptop with `gcloud` authenticated as that owner:

```bash
PROJECT_ID=<your-project-id> \
GH_REPO=<owner>/<repo> \
./infra/bootstrap.sh
```

After bootstrap, everything else is managed by Terraform.

---

## Terraform layout

Actual layout (post-T06): a flat root (project-global resources + two module instantiations) and one reusable environment module. **One state** (the bootstrap GCS bucket, default workspace) covers everything — there are no per-env state files or workspaces.

```
infra/terraform/
├── backend.tf              GCS state backend (bucket <project>-tf-state)
├── versions.tf             terraform + google provider constraints
├── provider.tf
├── variables.tf            project_id, region, project_number, billing_account, ops_email
├── terraform.tfvars        committed (organizational identifiers only — ADR-022)
├── services.tf             google_project_service × 5 (run, sqladmin, secretmanager, artifactregistry, clouderrorreporting)
├── billing.tf              budget alerts (T01a)
├── iam.tf                  project-global identity: flag-sync SA + WIF binding
├── artifact_registry.tf    shared docker repo `techscreen`
├── environments.tf         module "env_prod" + module "env_dev"
├── outputs.tf              service URLs, SQL connection names
└── modules/environment/    per-env: Cloud SQL + dbs + users, SAs + IAM, secrets, Cloud Run × 2
    ├── main.tf
    ├── variables.tf
    └── outputs.tf
```

Exactly two module instantiations exist (constitution §8 v1.1). No third environment will be added without an ADR superseding ADR-023.

### Operator pre-flight (one-time per laptop)

These steps were tribal knowledge through T01a's debug cycle and are captured here so future operators do not repeat them. Required only the **first** time you run `terraform apply` from a developer machine; once they're done they persist in your `gcloud` config until you clear it.

1. **Authenticate ADC with the right scopes.** Bare `gcloud auth application-default login` defaults to a minimal scope set that does **not** include `cloud-billing` — a `google_billing_budget` apply against this state will fail with `Error 400 INVALID_ARGUMENT` and a misleading "userinfo.email scope?" hint in the debug log. Always pass the full scope list:

   ```bash
   gcloud auth application-default login \
     --scopes=https://www.googleapis.com/auth/userinfo.email,\
   https://www.googleapis.com/auth/cloud-platform,\
   https://www.googleapis.com/auth/cloud-billing
   ```

2. **Set the ADC quota project.** Without this, GCP routes API quota usage to whatever Workspace project your account defaults to (we observed `projects/764086051850`), which makes `billingbudgets.googleapis.com` look "disabled" even though it is enabled on `tech-screen-493720`:

   ```bash
   gcloud auth application-default set-quota-project tech-screen-493720
   ```

3. **`terraform apply` env-vars.** The Terraform `google` provider also needs the user-project override at command time (the ADC quota-project is necessary but not sufficient for billing-account-scoped resources). The two env-vars to prepend on every `terraform plan` / `apply`:

   ```bash
   export GOOGLE_BILLING_PROJECT=tech-screen-493720
   export USER_PROJECT_OVERRIDE=true
   ```

   Or pass inline: `GOOGLE_BILLING_PROJECT=… USER_PROJECT_OVERRIDE=true terraform -chdir=infra/terraform apply …`.

### How to apply a change

⚠️ **Run `terraform apply` ONLY from the branch checkout that contains the HCL you intend to apply.** The Terraform GCS state is shared across all worktrees and checkouts of this repo. If you `terraform apply` from a checkout whose `infra/terraform/*.tf` is *missing* a resource that exists in state, Terraform sees "config has 0, state has 1 → destroy". This happened once during T01a — the recovery was easy but you do not want to re-do it. Concrete rule: if you are reviewing a PR branch, check it out before applying, never apply from `main` while the PR is open.

1. Branch from `main`.
2. Edit the HCL.
3. `terraform -chdir=infra/terraform init -upgrade` (once per clone).
4. `terraform -chdir=infra/terraform plan` — `terraform.tfvars` is auto-loaded from the working dir; backend bucket is hardcoded in `backend.tf` so no `-backend-config=` or `-var-file=` flag is needed.
5. Paste the plan summary into the PR description.
6. The **operator** runs `terraform apply` from the PR-branch checkout (see the warning above). CI auto-apply via WIF is a T06a-era follow-up — not wired yet.

Destructive plans (resource deletions) require a `[destructive]` tag in the PR title and a linked ADR. The CI workflow refuses to auto-apply without it.

---

## IAM model

### Humans

- **Project Owner (Ihor at MVP, later handed off):** full control, used only for bootstrap and break-glass.
- **Developer (to be added):** `roles/run.developer`, `roles/cloudsql.client`, `roles/secretmanager.secretAccessor` on named secrets, `roles/artifactregistry.reader`, `roles/logging.viewer`.
- **Deployer (`techscreen-deployers` group):** additionally `roles/run.admin` for traffic shifts.

Human access is via Workspace SSO (N-iX). No direct IAM user accounts.

### Service accounts

- **`terraform@<project>`:** `roles/owner` at MVP (will be tightened to least-privilege after the IaC shape is stable). Impersonated by CI via WIF; no JSON keys issued.
- **`techscreen-backend@` / `techscreen-backend-dev@`:** runtime identities for the backend Cloud Run services (one per environment).
  - `roles/cloudsql.client`
  - `roles/secretmanager.secretAccessor` on **their own environment's** secrets only: `DATABASE_URL(_DEV)`, `MAGIC_LINK_SIGNING_KEY(_DEV)`, `SENDGRID_API_KEY(_DEV)`, `SESSION_COOKIE_SECRET(_DEV)` — per-secret bindings, never project-level
  - `roles/aiplatform.user` for Vertex AI calls
  - `roles/logging.logWriter`, `roles/monitoring.metricWriter`
- **`techscreen-frontend@` / `techscreen-frontend-dev@`:** runtime identities for the frontend Cloud Run services.
  - Minimal: `roles/logging.logWriter`, `roles/monitoring.metricWriter`. Do not talk to SQL or Secret Manager directly.
- **`techscreen-flag-sync@`:** CI identity for `.github/workflows/sync-feature-flags.yml` (both environments).
  - `roles/cloudsql.client` + `roles/cloudsql.instanceUser`; WIF-bound to this repository
  - In-database privileges limited to the `feature_flag` table (`scripts/cloud-db-grants.sql`)

No JSON keys for any service account. Ever. See ADR-013 and the anti-pattern entry.

### CI (GitHub Actions)

- GitHub runners authenticate to GCP via the `github-actions` Workload Identity Pool.
- Attribute condition pins the pool to a single repository: `attribute.repository == '<owner>/techscreen'`.
- The runner impersonates `terraform@<project>` for infra changes and `techscreen-backend@<project>` (restricted subset) for deploy-time smoke calls if needed.
- No long-lived secrets stored in GitHub. Only the WIF provider resource name and SA email.

---

## Secret Manager inventory

Each key exists **twice**: the canonical name for prod, `<NAME>_DEV` for dev. Values differ per environment — dev never reuses prod key material.

| Secret                    | Owner   | Consumer        | Notes                                         |
| ------------------------- | ------- | --------------- | --------------------------------------------- |
| `DATABASE_URL(_DEV)`      | infra   | backend         | `postgres://` with `techscreen_app` user      |
| `MAGIC_LINK_SIGNING_KEY(_DEV)` | backend | backend    | HMAC key for candidate magic links            |
| `SESSION_COOKIE_SECRET(_DEV)`  | backend | backend    | Signs internal SSO session cookies            |
| `SENDGRID_API_KEY(_DEV)`  | infra   | backend         | Transactional email                           |
| `CALIBRATION_DATASET_KEY(_DEV)` | ops | calibration-run | Optional, if the dataset is encrypted at rest; no backend accessor |

Adding a secret:

1. Add the key to `.env.example` with an empty value (secrets always empty; non-secret defaults are allowed per ADR-022).
2. Add the name to `local.secret_names` in `infra/terraform/modules/environment/main.tf` (and to `local.backend_readable_secrets` if the backend consumes it) — both environments get the shell automatically.
3. Apply via Terraform — this creates empty secrets in both environments.
4. Fill each environment's value **manually** via Cloud Console or `gcloud secrets versions add`. Never commit the value. Never pass it in a PR description. Dev and prod values must differ.
5. Accessor grants are per-secret and generated by the module; never grant at project level.

Rotation: the consumer must fetch the secret at startup or cache with a TTL. A 24-hour TTL is the target for keys used on every request.

---

## Networking

MVP keeps it simple:

- Cloud SQL on public IP with authorised networks = none; access via the Cloud SQL Auth Proxy from Cloud Run using the `roles/cloudsql.client` permission.
- Cloud Run services are public-facing on `*.run.app` for the MVP. Custom domain deferred (see ADR-009 and the deferred features memory).
- No VPC Connector yet. Added only when we need to reach a resource that requires private IP (none at MVP).

---

## Observability

### Logging

- All services log structured JSON to stdout; Cloud Run captures and forwards to Cloud Logging.
- Log fields: `severity`, `session_id` (when applicable), `agent`, `model`, `request_id`, `operator_email` (for deploy-related logs).
- Retention: 30 days. Long-term retention is not needed at MVP; audit is in Postgres.

### Metrics

- Cloud Run publishes request count, latency, instance count automatically.
- Custom metrics written from the backend:
  - `llm.cost.per_session.usd` (gauge)
  - `llm.latency_ms` by agent (distribution)
  - `llm.schema_validation.failures` by agent and model version (counter)
  - `session.state.transitions` by from/to state (counter)

### Alerts

| Alert                                | Condition                           | Route     |
| ------------------------------------ | ----------------------------------- | --------- |
| Error rate high                      | > 2% of requests for 10 min         | ops email |
| LLM latency p95 high                 | > 10s for 10 min                    | ops email |
| Cloud SQL connection pool exhaustion | > 80% utilisation for 5 min         | ops email |
| Budget 90%                           | GCP Billing alert                   | ops email |
| Any rollback executed                | log-based alert on deploy audit row | ops email |

Dashboards live under `Cloud Monitoring → Dashboards → TechScreen`. The Terraform module `monitoring.tf` creates them.

---

## Backups and PITR

- Cloud SQL automated backups: daily, 7-day retention.
- Point-in-time recovery (PITR): enabled. 7-day window.
- Terraform state bucket: versioned, 30-day lifecycle on non-current versions.
- Secret Manager: versioned automatically; old versions kept until explicitly disabled.

Disaster drill: restore `techscreen-pg` from backup to a new instance, update the `DATABASE_URL` secret, redeploy. The drill is performed once per quarter starting after the pilot.

---

## What is explicitly NOT set up

- Staging / QA / UAT environment or any environment gate in the release path. ADR-023 (which added `dev`) keeps this exclusion.
- Separate vector database. ADR-007.
- VPC Service Controls. Overhead vs value is wrong for MVP pilot.
- Cloud Armor / WAF. MVP is internal-only behind SSO for recruiters; candidate traffic is magic-link gated.
- Dedicated KMS CMEK keys for Cloud SQL. Google-managed encryption is acceptable for pilot.
- Custom domain. `*.run.app` is acceptable for pilot.

Each of these becomes a candidate for ADR-reversal when the pilot graduates.

---

## Runbook: "the project needs a new GCP resource"

1. Is it in the resource inventory above? If no: ADR.
2. Add HCL under `infra/terraform/`.
3. If it's a service that runs code, add an SA with least-privilege.
4. If it stores secrets, follow the Secret Manager inventory process.
5. Update this document.
6. Open the PR, paste the `terraform plan` output, merge on approval, auto-apply in CI.

---

## Document versioning

- v2.0 — 2026-07-02 — T06: dev+prod topology (ADR-023), real Terraform layout (flat root + environment module), per-env secrets/IAM, flag-sync identity, cost table doubled, assets bucket deferred.
- v1.0 — 2026-04-18.
- Update this file when: a resource is added/removed, a secret is added/removed, region changes, IAM model changes, or the bootstrap procedure changes.
