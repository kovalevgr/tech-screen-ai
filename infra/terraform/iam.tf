# =============================================================================
# TechScreen — IAM seed (T01a)
# -----------------------------------------------------------------------------
# Minimum runtime-SA slice required for the FR-006 smoke test (Phase 6 of T01a).
# Strictly three resources, scoped per Clarifications 2026-04-24 Q4 + the spec
# Assumption that "the runtime SA has roles/aiplatform.user either by T01a time
# or by T06 time": T01a chose "T01a time" so the smoke can run from a developer
# laptop without waiting on T06's Cloud Run bring-up.
#
# T06 EXTENDS this file (does not rewrite). T06 will append additional
# google_project_iam_member and google_secret_manager_secret_iam_member
# resources for: roles/cloudsql.client, roles/secretmanager.secretAccessor on
# named secrets, roles/logging.logWriter, roles/monitoring.metricWriter — see
# docs/engineering/cloud-setup.md §IAM model and specs/003-vertex-quota-region/
# research.md §R6.
#
# Constitution §6: NO JSON service-account keys. The SA is consumed via
# Workload Identity Federation (Cloud Run runtime, T06+) and short-lived ADC
# impersonation (smoke test from operator laptop, this PR). The
# `gcloud iam service-accounts keys create` command is forbidden by the
# constitution and by the pre-commit `forbid-sa-keys` hook.
# =============================================================================

resource "google_service_account" "techscreen_backend" {
  account_id   = "techscreen-backend"
  display_name = "TechScreen backend runtime"
  description  = "Runtime identity for the Cloud Run backend (seeded by T01a; T06 extends with additional role bindings — see docs/engineering/cloud-setup.md §IAM model)."
}

resource "google_project_iam_member" "techscreen_backend_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.techscreen_backend.email}"
}

# Lets the human Owner principal (the operator who runs `terraform apply` and
# the smoke script) impersonate the runtime SA via:
#   gcloud auth print-access-token \
#     --impersonate-service-account=techscreen-backend@${PROJECT_ID}.iam.gserviceaccount.com
# This is the FR-006 smoke-test path (no JSON key, short-lived token).
#
# Single-person dependency: the binding targets `user:ikovalov@n-ix.com`
# specifically. To let another operator run the smoke, either rotate this
# value (HCL edit + apply) OR — the documented follow-up — switch to a group
# principal once N-iX IT provisions one (e.g. `group:techscreen-owners@n-ix.com`).
# See B1 in the analyze report tracked in `specs/003-vertex-quota-region/` and
# Follow-ups in `docs/engineering/vertex-quota.md`.
resource "google_service_account_iam_member" "techscreen_backend_tokens_for_owner" {
  service_account_id = google_service_account.techscreen_backend.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:ikovalov@n-ix.com"
}
