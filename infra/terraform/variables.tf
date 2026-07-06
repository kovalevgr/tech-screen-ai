variable "project_id" {
  description = "GCP project ID"
  type        = string
}

variable "region" {
  description = "Default GCP region for regional resources"
  type        = string
  default     = "europe-west1"
}

# -----------------------------------------------------------------------------
# T01a additions (seeded by specs/003-vertex-quota-region/).
# None of these values are secrets per ADR-022: project numbers, billing
# account IDs, and email addresses are organizational identifiers, not
# credentials. They live in terraform.tfvars and are committed to the repo.
# -----------------------------------------------------------------------------

variable "project_number" {
  description = "GCP project number (numeric, e.g. \"463244185014\" per docs/engineering/cloud-setup.md). Required by google_billing_budget.budget_filter.projects, which expects \"projects/<number>\" not \"projects/<id>\"."
  type        = string
}

variable "billing_account" {
  description = "N-iX billing account ID (format \"XXXXXX-XXXXXX-XXXXXX\"). Both google_billing_budget resources attach here. Obtain from GCP Console → Billing → Account management."
  type        = string
}

variable "ops_email" {
  description = "Email recipient for budget-alert notifications. MVP: Ihor's personal N-iX mailbox (per Clarifications 2026-04-24 Q1). Swap to a shared group alias via tfvars + apply once N-iX IT provisions one — see Follow-ups in docs/engineering/vertex-quota.md."
  type        = string
}

# -----------------------------------------------------------------------------
# T07 additions (seeded by specs/021-t07-identity-sso/).
# Both values are public *.run.app URLs of the operator-deployed auth-claims
# blocking function — organizational identifiers, not credentials (ADR-022).
# They default to "" so the first apply (before the function exists) skips
# trigger registration; the operator fills them in terraform.tfvars after
# quickstart §4 and a second apply registers the blocking triggers.
# -----------------------------------------------------------------------------

variable "auth_before_create_uri" {
  description = "HTTPS URI of the deployed auth-claims beforeUserCreated endpoint (gen2 Cloud Function). Empty = trigger not registered yet."
  type        = string
  default     = ""
}

variable "auth_before_sign_in_uri" {
  description = "HTTPS URI of the deployed auth-claims beforeUserSignedIn endpoint (gen2 Cloud Function). Empty = trigger not registered yet."
  type        = string
  default     = ""
}
