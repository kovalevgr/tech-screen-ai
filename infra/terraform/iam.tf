# =============================================================================
# TechScreen — project-global IAM (T01a seed, T06 reshape)
# -----------------------------------------------------------------------------
# T01a seeded the prod backend runtime SA here (three resources). T06 moved
# those into the environment module (module.env_prod — see ADR-023 and
# specs/018-t06-cloud-runtime/quickstart.md §2 for the non-destructive
# `terraform state mv` commands; the operator-impersonation rationale from
# T01a lives on in the module's backend_tokens_for_operator resource).
#
# What remains at root is identity that exists ONCE for the whole project:
# the CI flag-sync service account and its Workload Identity Federation
# binding to the bootstrap-created `github-actions` OIDC pool.
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
