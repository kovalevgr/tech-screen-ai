# =============================================================================
# TechScreen — project-global IAM (T01a seed, T06 reshape, T06a deployer)
# -----------------------------------------------------------------------------
# T01a seeded the prod backend runtime SA here (three resources). T06 moved
# those into the environment module (module.env_prod — see ADR-023 and
# specs/018-t06-cloud-runtime/quickstart.md §2 for the non-destructive
# `terraform state mv` commands; the operator-impersonation rationale from
# T01a lives on in the module's backend_tokens_for_operator resource).
#
# What lives at root is identity that exists ONCE for the whole project:
# the CI flag-sync service account (T06) and the CI deploy-pipeline service
# account (T06a), each with a Workload Identity Federation binding to the
# bootstrap-created `github-actions` OIDC pool.
#
# Constitution §6: NO JSON service-account keys — CI authenticates via WIF
# (short-lived, per-run, repository-pinned); humans via ADC impersonation.
# =============================================================================

# CI identity for .github/workflows/sync-feature-flags.yml (T05a workflow,
# bound live by T06). Reaches Cloud SQL through the Auth Proxy with
# --auto-iam-authn; its in-database privileges are limited to the
# feature_flag table (scripts/cloud-db-grants.sql).
resource "google_service_account" "flag_sync" {
  account_id   = "techscreen-flag-sync"
  display_name = "TechScreen configs-as-code sync (CI)"
  description  = "GitHub Actions identity for syncing configs/*.yaml into Cloud SQL (both environments). WIF-only; DB access limited to the feature_flag table via SQL grants."
}

resource "google_project_iam_member" "flag_sync_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.flag_sync.email}"
}

# Required (in addition to cloudsql.client) for IAM database authentication.
resource "google_project_iam_member" "flag_sync_cloudsql_instance_user" {
  project = var.project_id
  role    = "roles/cloudsql.instanceUser"
  member  = "serviceAccount:${google_service_account.flag_sync.email}"
}

# Lets GitHub Actions runs from THIS repository (and only this repository —
# the pool provider's attribute condition pins `kovalevgr/tech-screen-ai`)
# impersonate the flag-sync SA. Pool + provider were created by
# infra/bootstrap.sh; resource name verified live 2026-07-02.
resource "google_service_account_iam_member" "flag_sync_wif" {
  service_account_id = google_service_account.flag_sync.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/github-actions/attribute.repository/kovalevgr/tech-screen-ai"
}

# -----------------------------------------------------------------------------
# T06a — deploy pipeline identity (/deploy, /promote, /rollback)
# -----------------------------------------------------------------------------
# GitHub Actions identity for .github/workflows/{deploy,promote,rollback}.yml.
# Role set is deliberately minimal — full justification in
# specs/020-t06a-deploy-commands/research.md D4:
#
#   - run.developer, NOT run.admin: can deploy revisions and shift traffic
#     (traffic is a Service field, covered by run.services.update) but lacks
#     run.services.setIamPolicy — the public-access surface (run.invoker
#     bindings) stays Terraform-owned.
#   - iam.serviceAccountUser is granted ON the four runtime SAs only
#     (SA-level bindings below), never project-level: the deployer must not
#     be able to actAs the roles/owner terraform SA or the flag-sync SA.
#   - artifactregistry.writer on the single `techscreen` repository, not the
#     project.
#   - cloudsql.viewer: read-only instance metadata for the deploy gate's
#     cost-idle check. Chosen over cloudsql.client on purpose — viewer has no
#     instances.connect and no instances.update, so the deploy identity can
#     neither reach data nor wake/sleep instances (that is the operator's
#     scripts/cloud-sql-power.sh).
#
# What the deployer explicitly cannot do: read secrets, connect to any
# database, modify IAM, create keys, apply Terraform.

resource "google_service_account" "deployer" {
  account_id   = "techscreen-deployer"
  display_name = "TechScreen deploy pipeline (CI)"
  description  = "GitHub Actions identity for /deploy, /promote, /rollback (T06a). WIF-only; builds/pushes images, deploys Cloud Run revisions at 0% traffic, shifts traffic. Least-privilege role set documented in specs/020-t06a-deploy-commands/data-model.md."
}

# Same repository-pinned principalSet as the flag-sync binding above; the
# pool provider's attribute condition additionally pins the repository.
resource "google_service_account_iam_member" "deployer_wif" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/projects/${var.project_number}/locations/global/workloadIdentityPools/github-actions/attribute.repository/kovalevgr/tech-screen-ai"
}

resource "google_project_iam_member" "deployer_run_developer" {
  project = var.project_id
  role    = "roles/run.developer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "deployer_cloudsql_viewer" {
  project = var.project_id
  role    = "roles/cloudsql.viewer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_artifact_registry_repository_iam_member" "deployer_ar_writer" {
  location   = google_artifact_registry_repository.techscreen.location
  repository = google_artifact_registry_repository.techscreen.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.deployer.email}"
}

# actAs on the runtime SAs — deploying a revision that runs as SA X requires
# serviceAccountUser on X. SA-level only (see header note).
resource "google_service_account_iam_member" "deployer_actas_backend_prod" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${module.env_prod.backend_sa_email}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_actas_frontend_prod" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${module.env_prod.frontend_sa_email}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_actas_backend_dev" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${module.env_dev.backend_sa_email}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_service_account_iam_member" "deployer_actas_frontend_dev" {
  service_account_id = "projects/${var.project_id}/serviceAccounts/${module.env_dev.frontend_sa_email}"
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
