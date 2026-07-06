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

variable "llm_backend" {
  description = "LLM_BACKEND for the backend service: \"vertex\" (prod-required, FR-007 boot guard) or \"mock\" (dev-legal, free)."
  type        = string

  validation {
    condition     = contains(["mock", "vertex"], var.llm_backend)
    error_message = "LLM_BACKEND is \"mock\" or \"vertex\"."
  }
}

variable "auth_mode" {
  description = "AUTH_MODE for the backend service (T07 §9 seam): \"disabled\" (dark, default) or \"identity_platform\". Managed here so gcloud-side flips never fight Terraform."
  type        = string
  default     = "disabled"

  validation {
    condition     = contains(["disabled", "identity_platform"], var.auth_mode)
    error_message = "AUTH_MODE is \"disabled\" or \"identity_platform\"."
  }
}

variable "auth_allowed_domain" {
  description = "Workspace hosted domain admitted by the backend verifier (AUTH_ALLOWED_DOMAIN)."
  type        = string
  default     = "n-ix.com"
}

variable "wire_runtime" {
  description = "Wire env vars + DATABASE_URL secret + Cloud SQL connector into the backend template. Keep FALSE while the environment's SQL instance sleeps (cost-idle): the connector volume needs a RUNNABLE instance for new revisions to become ready. Flip together with waking the instance."
  type        = bool
  default     = false
}
