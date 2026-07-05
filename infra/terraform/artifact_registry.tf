# =============================================================================
# TechScreen — Artifact Registry (T06)
# -----------------------------------------------------------------------------
# One docker repository shared by both environments (ADR-023); dev/prod
# separation happens at the image-tag level, owned by T06a's /deploy.
# =============================================================================

resource "google_artifact_registry_repository" "techscreen" {
  location      = var.region
  repository_id = "techscreen"
  format        = "DOCKER"
  description   = "Container images for techscreen-backend and techscreen-frontend (both environments; tags carry the env/version)."

  depends_on = [google_project_service.required]
}
