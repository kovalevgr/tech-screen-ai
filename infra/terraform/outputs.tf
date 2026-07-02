# =============================================================================
# TechScreen — root outputs (T06)
# -----------------------------------------------------------------------------
# Consumed by operators (quickstart acceptance sweep) and future tasks
# (T06a /deploy targets, T07 SSO wiring, sync-feature-flags.yml values).
# =============================================================================

output "prod_backend_url" {
  description = "Prod backend Cloud Run URL."
  value       = module.env_prod.backend_service_url
}

output "prod_frontend_url" {
  description = "Prod frontend Cloud Run URL."
  value       = module.env_prod.frontend_service_url
}

output "dev_backend_url" {
  description = "Dev backend Cloud Run URL."
  value       = module.env_dev.backend_service_url
}

output "dev_frontend_url" {
  description = "Dev frontend Cloud Run URL."
  value       = module.env_dev.frontend_service_url
}

output "prod_sql_connection_name" {
  description = "Prod Cloud SQL connection name (project:region:instance)."
  value       = module.env_prod.sql_connection_name
}

output "dev_sql_connection_name" {
  description = "Dev Cloud SQL connection name (project:region:instance)."
  value       = module.env_dev.sql_connection_name
}

output "flag_sync_sa_email" {
  description = "CI flag-sync service-account email (WIF-bound; used by sync-feature-flags.yml)."
  value       = google_service_account.flag_sync.email
}
