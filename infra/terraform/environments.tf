# =============================================================================
# TechScreen — environment instantiation (T06, ADR-023)
# -----------------------------------------------------------------------------
# Exactly two long-lived environments, both from the same module: structural
# drift between dev and prod is impossible by construction (constitution §8
# v1.1). Prod keeps canonical resource names (empty suffixes); dev appends
# "-dev" / "_DEV".
#
# Prod's backend SA + two bindings predate this module (T01a). Before the
# first plan of this configuration, run the three `terraform state mv`
# commands in specs/018-t06-cloud-runtime/quickstart.md §2.
# =============================================================================

module "env_prod" {
  source = "./modules/environment"

  env                = "prod"
  llm_backend        = "vertex" # FR-007: prod refuses mock at boot
  wire_runtime       = false    # prod sleeps (cost-idle) — flip together with waking it
  name_suffix        = ""
  secret_suffix      = ""
  project_id         = var.project_id
  region             = var.region
  flag_sync_sa_email = google_service_account.flag_sync.email
  operator_email     = var.ops_email

  depends_on = [google_project_service.required]
}

module "env_dev" {
  source = "./modules/environment"

  env                = "dev"
  llm_backend        = "mock"              # dev-legal (settings guard), zero Vertex spend
  wire_runtime       = true                # dev instance is awake for the active work phase
  auth_mode          = "identity_platform" # T07 live on dev since 2026-07-06 (prod stays dark)
  name_suffix        = "-dev"
  secret_suffix      = "_DEV"
  project_id         = var.project_id
  region             = var.region
  flag_sync_sa_email = google_service_account.flag_sync.email
  operator_email     = var.ops_email

  depends_on = [google_project_service.required]
}
