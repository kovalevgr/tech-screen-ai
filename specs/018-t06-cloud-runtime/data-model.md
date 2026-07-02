# Data model — T06 Cloud runtime foundation

Infra feature: the "entities" are cloud resources, identities, and their bindings. Application tables are untouched (migrations 0001–0005 applied as-is).

## Environment module interface (`infra/terraform/modules/environment/`)

| Input | prod value | dev value | Notes |
| --- | --- | --- | --- |
| `env` | `"prod"` | `"dev"` | labels + descriptions |
| `name_suffix` | `""` | `"-dev"` | services, SAs, SQL instance |
| `secret_suffix` | `""` | `"_DEV"` | Secret Manager names |
| `project_id` / `region` | `tech-screen-493720` / `europe-west1` | same | from root vars |
| `flag_sync_sa_email` | root-created SA email | same | becomes `CLOUD_IAM_SERVICE_ACCOUNT` SQL user |
| `backend_sa_create` | `false` (adopts existing via state mv) | `true` | see quickstart § state mv |

Outputs: `backend_service_url`, `frontend_service_url`, `sql_connection_name`, `backend_sa_email`, `frontend_sa_email`.

## Resources per environment (module contents)

| Resource | prod name | dev name | Key attributes |
| --- | --- | --- | --- |
| Cloud SQL instance | `techscreen-pg` | `techscreen-pg-dev` | PG17, `db-f1-micro`, 10 GB SSD, daily backups (7d), PITR on, deletion protection on, flag `cloudsql.iam_authentication=on`, public IP / no authorised networks |
| SQL databases | `techscreen`, `techscreen_shadow` | same | per instance |
| SQL users (built-in) | `techscreen_app`, `techscreen_migrator` | same | created **without password** (R6); operator sets out-of-band |
| SQL user (IAM SA) | `techscreen-flag-sync@tech-screen-493720.iam` | same | type `CLOUD_IAM_SERVICE_ACCOUNT` |
| Cloud Run v2 backend | `techscreen-backend` | `techscreen-backend-dev` | min 0 / max 5, 1 vCPU / 1 GiB, placeholder hello image + `ignore_changes[image]`, public invoker |
| Cloud Run v2 frontend | `techscreen-frontend` | `techscreen-frontend-dev` | same sizing/posture |
| Backend runtime SA | `techscreen-backend@` (existing) | `techscreen-backend-dev@` | roles below |
| Frontend runtime SA | `techscreen-frontend@` | `techscreen-frontend-dev@` | `logging.logWriter`, `monitoring.metricWriter` only |
| Secrets (empty shells) | `DATABASE_URL`, `MAGIC_LINK_SIGNING_KEY`, `SESSION_COOKIE_SECRET`, `SENDGRID_API_KEY`, `CALIBRATION_DATASET_KEY` | same + `_DEV` | replication automatic; zero versions at apply |

Backend SA roles (per env, granted in module): `roles/cloudsql.client` (project-level), `roles/secretmanager.secretAccessor` **per backend-consumed secret of its own environment** (`DATABASE_URL*`, `MAGIC_LINK_SIGNING_KEY*`, `SESSION_COOKIE_SECRET*`, `SENDGRID_API_KEY*` — not `CALIBRATION_DATASET_KEY*`, whose consumer is the calibration tooling), `roles/logging.logWriter`, `roles/monitoring.metricWriter`, `roles/aiplatform.user` (prod already has it from T01a; dev granted new).

## Project-global resources (root)

| Resource | Name / value |
| --- | --- |
| `google_project_service` × 5 | `run`, `sqladmin`, `secretmanager`, `artifactregistry`, `clouderrorreporting` — `disable_on_destroy=false` (adopt: enabled live 2026-07-02, research R9) |
| Artifact Registry repo | `techscreen` (docker, `europe-west1`) — shared by both envs; per-env separation happens at image-tag level (T06a) |
| Flag-sync SA | `techscreen-flag-sync@` + `roles/cloudsql.client`, `roles/cloudsql.instanceUser` |
| WIF binding | `roles/iam.workloadIdentityUser` on flag-sync SA for `principalSet://…/attribute.repository/<owner>/<repo>` (existing pool `github-actions`, provider `github`) |
| Existing (untouched) | budgets ×2, ops email channel, terraform SA, state bucket |

## Identity → access matrix (cross-environment bleed check, spec edge case)

| Identity | prod DB | dev DB | prod secrets | dev secrets |
| --- | --- | --- | --- | --- |
| `techscreen-backend@` | client | — | accessor (named) | — |
| `techscreen-backend-dev@` | — | client | — | accessor (named) |
| `techscreen-flag-sync@` | `feature_flag` table only (SQL grants) | same | — | — |
| `techscreen-frontend*@` | — | — | — | — |

*(`roles/cloudsql.client` is project-level by GCP design; DB-level isolation for the app roles is enforced by per-instance users + passwords, and the §3 REVOKEs inside each DB.)*

## Post-migration SQL grants (`scripts/cloud-db-grants.sql`)

```sql
GRANT SELECT, INSERT, UPDATE ON TABLE feature_flag
  TO "techscreen-flag-sync@tech-screen-493720.iam";
```

Applied per environment by the operator after `alembic upgrade head` (quickstart step 7). `feature_flag` is deliberately mutable (T05a) — this grant does not touch the six §3 append-only tables.

## Workflow contract (`sync-feature-flags.yml` after T06)

| Placeholder | Value |
| --- | --- |
| `WIF_PROVIDER` | `projects/463244185014/locations/global/workloadIdentityPools/github-actions/providers/github` |
| `WIF_SERVICE_ACCOUNT` | `techscreen-flag-sync@tech-screen-493720.iam.gserviceaccount.com` |
| `GCP_PROJECT` | `tech-screen-493720` |
| `CLOUD_SQL_INSTANCE` | matrix: `tech-screen-493720:europe-west1:techscreen-pg` / `…:techscreen-pg-dev` |
| `DATABASE_USER` | `techscreen-flag-sync@tech-screen-493720.iam` (corrected from the stale `techscreen_migrator` example) |

Matrix `env: [dev, prod]`, `fail-fast: false`; Guard step logic unchanged (evaluates to `skip=false` once values are non-empty).

## State transitions

1. **Pre-apply**: default-workspace state = 6 T01a resources.
2. **State surgery** (before first plan of this HCL): 3 × `terraform state mv` of the backend-SA trio into `module.env_prod` addresses.
3. **Apply**: +~45 resources (two module instances + globals).
4. **Steady state**: repeat `terraform plan` = zero diff (SC-001); image drift excluded via `ignore_changes`.
