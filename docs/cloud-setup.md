# Cloud Setup

How TechScreen uses Google Cloud. Single project, single region, prod-only, Terraform-managed after a one-shot manual bootstrap. Everything here is written so a new engineer can reconstruct the topology end-to-end.

Related: [ADR-009](../adr/009-prod-only-topology.md), [ADR-012](../adr/012-cloud-run-traffic-splitting.md), [ADR-013](../adr/013-secret-management.md), [ADR-015](../adr/015-region-europe-west1.md), [constitution §5, §6, §8](../.specify/memory/constitution.md).

---

## Project layout

- **GCP project:** one, owned by N-iX. Project number `463244185014`. Human-readable project ID confirmed via Cloud Console ("Project info" card). Billing attached to the N-iX billing account for TechScreen.
- **Region:** `europe-west1` (Belgium). All regional resources live there. See ADR-015.
- **Environments:** only `prod`. No staging. Local dev runs against Docker Compose with the `vertex-mock` service; tests run in the same Compose stack in CI.

---

## Resource inventory

| Resource | Purpose | Size / tier |
| --- | --- | --- |
| Cloud Run service `techscreen-backend` | FastAPI API | min 0, max 5 instances, 1 vCPU / 1 GiB |
| Cloud Run service `techscreen-frontend` | Next.js SSR | min 0, max 5 instances, 1 vCPU / 1 GiB |
| Cloud SQL Postgres 15 instance `techscreen-pg` | App DB + pgvector | `db-f1-micro`, 10 GB SSD, PITR on |
| Cloud SQL database `techscreen` | Application schema | |
| Cloud SQL database `techscreen_shadow` | Alembic autogenerate target | |
| Secret Manager | All secrets (DB URL, magic-link signing key, etc.) | |
| Artifact Registry `techscreen` | Docker images for both services | `europe-west1` |
| Cloud Storage bucket `<project>-tfstate` | Terraform remote state | versioned, 30-day lifecycle |
| Cloud Storage bucket `<project>-techscreen-assets` | Generated artefacts, exports | Standard, versioning off |
| Cloud Monitoring workspace | Dashboards, alert policies | |
| Cloud Logging | All services | 30-day retention |
| IAM Workload Identity Pool `github-actions` | CI auth via OIDC | |

Vertex AI is accessed as a managed API (no dedicated resource is provisioned).

---

## Rough monthly cost

For the MVP pilot volume (≤ 50 completed sessions / month):

| Line item | Approx USD/mo |
| --- | --- |
| Cloud Run (both services, mostly idle) | $2 |
| Cloud SQL `db-f1-micro` + 10 GB + PITR | $9 |
| Artifact Registry storage | negligible |
| Cloud Storage (state + assets) | < $1 |
| Secret Manager | < $1 |
| Vertex AI (Gemini 2.5 Flash/Pro) | $4 – $10 |
| Total | **~$20 – $25** |

Monthly budget alert at $50 (constitution §12). Alerts at 50 / 90 / 100 % of budget fire to the ops inbox.

---

## Bootstrap — one-off manual steps

A chicken-and-egg problem: Terraform needs a GCS bucket for state, and service-account auth, both of which we want Terraform to manage. We solve it by creating the absolute minimum by hand.

`infra/bootstrap.sh` handles all of this idempotently. It:

1. Enables required APIs: `cloudresourcemanager`, `iam`, `iamcredentials`, `serviceusage`, `storage`, `sts`.
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

```
infra/terraform/
├── main.tf                provider + backend config (GCS)
├── variables.tf
├── outputs.tf
├── network.tf             VPC connector for Cloud SQL private IP, if used
├── sql.tf                 Cloud SQL instance + dbs + user
├── artifact_registry.tf
├── cloud_run.tf           backend + frontend services + traffic split
├── secrets.tf             Secret Manager secret resources (names only)
├── iam.tf                 SA bindings, WIF pool + provider
├── monitoring.tf          alert policies, dashboards
└── envs/
    └── prod/
        ├── terraform.tfvars
        └── backend.tf     bucket = "<project>-tfstate", prefix = "prod"
```

Only `prod` exists. No `envs/dev/` or `envs/staging/` will be added without an ADR reversing §8.

### How to apply a change

1. Branch from `main`.
2. Edit the HCL.
3. `terraform -chdir=infra/terraform init -upgrade` (once per clone).
4. `terraform -chdir=infra/terraform plan -var-file=envs/prod/terraform.tfvars`.
5. Paste the plan summary into the PR description.
6. On merge, CI runs `terraform apply -auto-approve` against `prod`, authenticated via WIF.

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
- **`techscreen-backend@<project>`:** runtime identity for the backend Cloud Run service.
  - `roles/cloudsql.client`
  - `roles/secretmanager.secretAccessor` on: `DATABASE_URL`, `MAGIC_LINK_SIGNING_KEY`, `SENDGRID_API_KEY`, `SESSION_COOKIE_SECRET`, `VERTEX_SA_IMPERSONATION_TARGET` (if used)
  - `roles/aiplatform.user` for Vertex AI calls
  - `roles/logging.logWriter`, `roles/monitoring.metricWriter`
- **`techscreen-frontend@<project>`:** runtime identity for the frontend Cloud Run service.
  - Minimal: `roles/logging.logWriter`, `roles/monitoring.metricWriter`. Does not talk to SQL or Secret Manager directly.

No JSON keys for any service account. Ever. See ADR-013 and the anti-pattern entry.

### CI (GitHub Actions)

- GitHub runners authenticate to GCP via the `github-actions` Workload Identity Pool.
- Attribute condition pins the pool to a single repository: `attribute.repository == '<owner>/techscreen'`.
- The runner impersonates `terraform@<project>` for infra changes and `techscreen-backend@<project>` (restricted subset) for deploy-time smoke calls if needed.
- No long-lived secrets stored in GitHub. Only the WIF provider resource name and SA email.

---

## Secret Manager inventory

| Secret | Owner | Consumer | Notes |
| --- | --- | --- | --- |
| `DATABASE_URL` | infra | backend | `postgres://` with `techscreen` user |
| `MAGIC_LINK_SIGNING_KEY` | backend | backend | HMAC key for candidate magic links |
| `SESSION_COOKIE_SECRET` | backend | backend | Signs internal SSO session cookies |
| `SENDGRID_API_KEY` | infra | backend | Transactional email |
| `CALIBRATION_DATASET_KEY` | ops | calibration-run | Optional, if the dataset is encrypted at rest |

Adding a secret:

1. Add the key (no value) to `.env.example`.
2. Add a `google_secret_manager_secret` resource in `infra/terraform/secrets.tf`.
3. Deploy via Terraform — this creates an empty secret.
4. Fill the secret value **manually** via Cloud Console or `gcloud secrets versions add`. Never commit the value. Never pass it in a PR description.
5. Grant the consumer SA `roles/secretmanager.secretAccessor` on that specific secret, not at project level.

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

| Alert | Condition | Route |
| --- | --- | --- |
| Error rate high | > 2% of requests for 10 min | ops email |
| LLM latency p95 high | > 10s for 10 min | ops email |
| Cloud SQL connection pool exhaustion | > 80% utilisation for 5 min | ops email |
| Budget 90% | GCP Billing alert | ops email |
| Any rollback executed | log-based alert on deploy audit row | ops email |

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

- Staging environment. ADR-009.
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

- v1.0 — 2026-04-18.
- Update this file when: a resource is added/removed, a secret is added/removed, region changes, IAM model changes, or the bootstrap procedure changes.
