project_id = "tech-screen-493720"
region     = "europe-west1"

# -----------------------------------------------------------------------------
# T01a additions (specs/003-vertex-quota-region/).
#
# IMPORTANT: Before running `terraform apply` for the first time after the
# T01a PR merges, replace every "<FILL-IN ...>" placeholder below with the
# real value. Apply will fail with "variables not set" until done.
#
# None of these are secrets per ADR-022 (project numbers, billing account IDs,
# email addresses are organizational identifiers, not credentials). The T01
# gitleaks + detect-secrets hooks scan this file on every commit.
# -----------------------------------------------------------------------------

# Numeric project number, as quoted in docs/engineering/cloud-setup.md (463244185014).
# Required by google_billing_budget.budget_filter.projects.
project_number = "463244185014"

# N-iX billing account ID, format "XXXXXX-XXXXXX-XXXXXX".
# Obtain from GCP Console → Billing → Account management → Billing account ID.
billing_account = "01FD59-751466-B7F7A5"

# Budget-alert recipient.
# MVP: Ihor's personal N-iX mailbox (Clarifications 2026-04-24 Q1).
# Swap to a shared group alias here once N-iX IT provisions one — see
# Follow-ups in docs/engineering/vertex-quota.md.
ops_email = "ikovalov@n-ix.com"
