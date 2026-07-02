# =============================================================================
# TechScreen environment module — inputs (T06)
# -----------------------------------------------------------------------------
# One instantiation per long-lived environment (ADR-023: exactly two — dev and
# prod — in the single project). Prod uses empty suffixes so every resource
# keeps its canonical documented name; dev appends "-dev" / "_DEV".
# =============================================================================

variable "env" {
  description = "Environment name: \"dev\" or \"prod\". Used in labels and descriptions."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.env)
    error_message = "ADR-023 allows exactly two long-lived environments: dev and prod."
  }
}

variable "name_suffix" {
  description = "Suffix for resource names (services, SAs, SQL instance): \"\" for prod, \"-dev\" for dev."
  type        = string
}

variable "secret_suffix" {
  description = "Suffix for Secret Manager secret names: \"\" for prod, \"_DEV\" for dev."
  type        = string
}

variable "project_id" {
  description = "GCP project ID (single project hosts both environments — ADR-023)."
  type        = string
}

variable "region" {
  description = "Region for regional resources (europe-west1 — ADR-015)."
  type        = string
}

variable "flag_sync_sa_email" {
  description = "Email of the CI flag-sync service account (created at root); becomes a CLOUD_IAM_SERVICE_ACCOUNT SQL user on this environment's instance."
  type        = string
}

variable "operator_email" {
  description = "Human operator allowed to mint short-lived tokens for the backend SA (smoke tests; no JSON keys per constitution §6)."
  type        = string
}
