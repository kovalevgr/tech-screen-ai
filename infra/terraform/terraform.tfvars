project_id = "tech-screen-493720"
region     = "europe-west1"

# -----------------------------------------------------------------------------
# T01a additions (specs/003-vertex-quota-region/).
#
# All three values below are organizational identifiers, not credentials,
# per ADR-022 (project numbers, billing account IDs, email addresses).
# Committed to the repo intentionally; the T01 gitleaks + detect-secrets
# hooks scan this file on every commit.
#
# To rotate any value (e.g. swap `ops_email` for a group alias once N-iX IT
# provisions one): edit here, then run the apply procedure documented in
# docs/engineering/cloud-setup.md §"How to apply a change" (which now also
# covers the cloud-billing ADC scope and env-var setup needed for budgets).
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
