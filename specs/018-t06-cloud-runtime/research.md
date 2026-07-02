# Research — T06 Cloud runtime foundation (dev + prod)

**Date**: 2026-07-02 · **Feature**: [spec.md](./spec.md) · All spec "plan-phase research items" resolved below. Items marked **[verified live]** were checked against project `tech-screen-493720` on 2026-07-02 with the operator's credentials.

## R1. Postgres 17 + pgvector + `db-f1-micro` in `europe-west1` **[verified live]**

- **Decision**: Cloud SQL `POSTGRES_17` on `db-f1-micro`, Enterprise edition, `europe-west1`. pgvector activates via `CREATE EXTENSION IF NOT EXISTS vector` — which migration `0001_baseline` already runs. The only database flag we set is `cloudsql.iam_authentication=on` (needed by R5).
- **Evidence**: `gcloud sql tiers list` shows `db-f1-micro` available in `europe-west1`; `gcloud sql flags list --database-version=POSTGRES_17` succeeds (version enum valid) and lists `cloudsql.iam_authentication`; **no `cloudsql.enable_pgvector` flag exists** — the implementation-plan T06 text citing it is stale (that flag was never the mechanism on Cloud SQL; the extension is allow-listed and created in-database).
- **Fallback**: if `CREATE EXTENSION vector` unexpectedly fails on PG17 at first migration (SC-004 catches it), fall back to `POSTGRES_16` per ADR-001 amendment and record an ADR-001 addendum. Not expected.
- **Alternatives considered**: PG16 outright (rejected — ADR-001 targets 17; 17 verified available).

## R2. Per-environment instantiation mechanism

- **Decision**: **Single root configuration + a reusable `infra/terraform/modules/environment/` module instantiated twice** (`module "env_dev"`, `module "env_prod"`), all in the **existing default-workspace state**. Project-global resources (API enablement, Artifact Registry, flag-sync SA + WIF binding, existing budgets/IAM) stay at root.
- **Rationale**: the six T01a resources already live in the default-workspace state — no state surgery beyond three targeted `terraform state mv` commands (R3); global resources exist once (workspaces would force `count` conditionals or duplicate them); one `terraform plan/apply` covers everything, matching the current operator runbook; Terraform 1.5.2 supports this shape natively.
- **Alternatives considered**: Terraform **workspaces** (implementation-plan wording) — rejected: default workspace already holds mixed global+prod resources, so we'd need a full state migration plus per-workspace conditionals for globals; the plan's "two workspaces" phrase described the *outcome* (two environments), which this design delivers. **Separate env directories with separate states** — rejected as premature for a 2-env single-project MVP; revisit if blast-radius isolation becomes a real need (noted in the new ADR).
- **State-key stability**: backend bucket/prefix untouched.

## R3. Adopting T01a resources into the module shape

- **Decision**: `techscreen-backend@` SA and its two IAM bindings move into `module.env_prod` via documented, non-destructive `terraform state mv` (exact commands in [quickstart.md](./quickstart.md)). Budgets and the notification channel stay at root (project-global).
- **Rationale**: prod must reuse the existing SA (spec FR-006); `state mv` avoids destroy/recreate of an SA that already holds `aiplatform.user`.

## R4. Environment naming convention

- **Decision**: prod keeps every documented name verbatim (`techscreen-backend`, `techscreen-frontend`, `techscreen-pg`, secrets `DATABASE_URL`…); dev appends `-dev` to services/SAs/SQL instance (`techscreen-backend-dev`, `techscreen-pg-dev`) and `_DEV` to secret names (`DATABASE_URL_DEV`). Module input `name_suffix` (`""` for prod, `"-dev"`/`"_DEV"` derived for dev).
- **Rationale**: implementation-plan + cloud-setup acceptance name the prod resources exactly (`gcloud run services describe techscreen-backend`, "gcloud secrets list shows every key from `.env.example`"); Cloud Run/SQL names are unique per project+region so dev must differ structurally.

## R5. Flag-sync CI identity + IAM DB auth **[verified live: WIF pool exists]**

- **Decision**: new SA `techscreen-flag-sync@` bound to the existing pool (`projects/463244185014/locations/global/workloadIdentityPools/github-actions/providers/github`, repository-pinned principalSet). Per-instance `google_sql_user` of type `CLOUD_IAM_SERVICE_ACCOUNT`; its Postgres username is the SA email **minus** `.gserviceaccount.com`: `techscreen-flag-sync@tech-screen-493720.iam`. Instance flag `cloudsql.iam_authentication=on` (R1). SA gets `roles/cloudsql.client` + `roles/cloudsql.instanceUser`. The workflow's `DATABASE_USER` placeholder gets this IAM username — **not** `techscreen_migrator` (the T05a file's example value is corrected; the sync job must not run as the DDL owner).
- **Table grants**: IAM DB users start with no table privileges. Ship `scripts/cloud-db-grants.sql` (GRANT `SELECT, INSERT, UPDATE` ON `feature_flag` + future-proof comment) — applied by the operator right after the initial migrations (quickstart step; FR-009's runbook).
- **Alternatives considered**: password-auth DB user for CI (rejected — a long-lived password secret in GitHub contradicts the WIF-only spirit of §6); running sync as `techscreen_migrator` (rejected — least privilege).

## R6. Database principals + credential mechanism

- **Decision**: per environment, Terraform creates `techscreen_app` and `techscreen_migrator` as `google_sql_user` **without** `password` (login impossible until set). The operator sets passwords out-of-band (`gcloud sql users set-password`) and fills that environment's `DATABASE_URL`/`DATABASE_URL_DEV` secret manually. Nothing credential-shaped enters Git, PR text, or Terraform state.
- **Alternatives considered**: `random_password` + `google_sql_user.password` (rejected — plaintext-recoverable in the GCS state object; §5's "cheapest prevention is absence"); Secret Manager-generated + data source (same state-exposure problem).

## R7. Placeholder image + image-ownership handoff

- **Decision**: both services start on Google's public sample `us-docker.pkg.dev/cloudrun/container/hello` with `lifecycle { ignore_changes = [template[0].containers[0].image] }` on each `google_cloud_run_v2_service`. T06a's `/deploy` owns image rollout thereafter; Terraform never fights it.
- **Ingress**: public (`allUsers` invoker) from day one, matching cloud-setup's "public-facing on `*.run.app`" posture; the placeholder serves no data and the real backend arrives 401-gated until T07.

## R8. Sync-workflow fan-out shape

- **Decision**: `strategy: matrix: env: [dev, prod]` with `fail-fast: false`; per-env `CLOUD_SQL_INSTANCE` and `DATABASE_NAME=techscreen` from matrix includes; single auth step per job using the same flag-sync SA. One env failing does not mask the other (mirrors T16's isolation rule).

## R9. API enablement + ordering **[executed live]**

- **Decision**: `google_project_service` for `run`, `sqladmin`, `secretmanager`, `artifactregistry`, `clouderrorreporting` with `disable_on_destroy = false`; module resources `depends_on` the services they need. The operator enabled these five on 2026-07-02 (research needed `sqladmin` to verify R1), so first apply **adopts** them — propagation-delay risk is retired; the HCL remains the source of truth for a rebuild.

## R10. Governance artifacts (FR-013)

- **Decision**: new **ADR-023 "Dev + prod environments in a single project"** (next free number after ADR-022) — records the owner's 2026-07-02 decision, cost delta (~$11–12 → ~$22–25/mo), drift trade-offs, and that the release path keeps 0 %-traffic revision verification (ADR-012). ADR-009 → `Status: Superseded by ADR-023`. Constitution §8 rewritten to "two long-lived environments, dev and prod, in a single GCP project; no staging/QA/UAT gate in the release path", version bumped to v1.1 with changelog line, per the constitution's own change procedure (ADR + owner acceptance — recorded in spec Clarifications). `adr/README.md` index gains the row. `cloud-setup.md` rewritten (FR-010); implementation-plan T06's "Two workspaces" + `enable_pgvector` sentences get a correcting note pointing at ADR-023/R1 (Appendix C: no renumbering, description-level fix).

## R11. What T06 explicitly does not decide

- Real image builds/pushes, traffic policy, `/deploy` mechanics — T06a. SSO/Identity Platform — T07. Dashboards/alert policies — T38. Rubric sync job — T16. Assets bucket — deferred until a consumer exists.
