output "backend_service_url" {
  description = "HTTPS URL of the backend Cloud Run service."
  value       = google_cloud_run_v2_service.backend.uri
}

output "frontend_service_url" {
  description = "HTTPS URL of the frontend Cloud Run service."
  value       = google_cloud_run_v2_service.frontend.uri
}

output "sql_connection_name" {
  description = "Cloud SQL connection name (project:region:instance) — used by the Auth Proxy and the flag-sync workflow."
  value       = google_sql_database_instance.pg.connection_name
}

output "backend_sa_email" {
  description = "Backend runtime service-account email."
  value       = google_service_account.backend.email
}

output "frontend_sa_email" {
  description = "Frontend runtime service-account email."
  value       = google_service_account.frontend.email
}
