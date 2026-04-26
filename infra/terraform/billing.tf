# =============================================================================
# TechScreen — Billing alerts (T01a)
# -----------------------------------------------------------------------------
# Two budgets + one notification channel. Per Clarifications 2026-04-24 Q5:
#   - Project-wide budget at $50/mo  → constitution §12 hard cap, all services
#   - Vertex-only  budget at $20/mo  → early-warning that isolates LLM-side
#                                      spikes from general infra drift
# Both target a single Cloud Monitoring email channel routed to Ihor's
# personal N-iX mailbox (Q1). Swap to a group alias by editing
# terraform.tfvars `ops_email` and re-applying — no resource
# replacement needed.
#
# Provider: `hashicorp/google ~> 6.0` (pinned by PR #2's versions.tf).
# `google_billing_budget` is GA in 5.x and 6.x; attribute names below were
# validated against provider 6.50.0 (current lock-file pin). If you bump the
# provider major, verify `disable_default_iam_recipients` and
# `enable_project_level_recipients` still resolve on `all_updates_rule`.
# =============================================================================

resource "google_monitoring_notification_channel" "ops_email" {
  display_name = "TechScreen budget alerts (MVP recipient)"
  type         = "email"
  labels = {
    email_address = var.ops_email
  }
  enabled = true

  description = "MVP recipient for TechScreen budget alerts. Per Clarifications 2026-04-24 Q1, this is Ihor's personal N-iX mailbox. Swap for a shared group alias via terraform.tfvars when N-iX IT provisions one — see Follow-ups in docs/engineering/vertex-quota.md."
}

resource "google_billing_budget" "project_wide" {
  billing_account = var.billing_account
  display_name    = "techscreen / project-wide PLN 200 (≈ $50)"

  budget_filter {
    projects = ["projects/${var.project_number}"]
    # No `services` filter — covers all GCP services in the project.
    # This is the constitution §12 hard cap for total monthly spend.
    # Currency note: billing account 01FD59-751466-B7F7A5 is denominated in PLN
    # (Polish złoty), so budgets MUST be PLN. 200 PLN ≈ $50 USD at ~4 PLN/USD —
    # the constitution §12 cap interpreted as "approximately $50". See
    # specs/003-vertex-quota-region/spec.md Clarifications 2026-04-26 Q (currency).
  }

  amount {
    specified_amount {
      currency_code = "PLN"
      units         = "200"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  all_updates_rule {
    # All four attributes set explicitly. Provider would otherwise default
    # `enable_project_level_recipients` to false and `schema_version` to "1.0";
    # making the defaults visible avoids plan/HCL drift confusion for future
    # readers (per L7 in PR #3 review).
    monitoring_notification_channels = [google_monitoring_notification_channel.ops_email.id]
    disable_default_iam_recipients   = true
    enable_project_level_recipients  = false
    schema_version                   = "1.0"
  }
}

resource "google_billing_budget" "vertex_only" {
  billing_account = var.billing_account
  display_name    = "techscreen / vertex-only PLN 80 (≈ $20)"

  budget_filter {
    projects = ["projects/${var.project_number}"]
    services = ["services/aiplatform.googleapis.com"]
  }

  amount {
    specified_amount {
      # PLN-denominated per billing account currency; 80 PLN ≈ $20 USD.
      # See Clarifications 2026-04-26 Q (currency) in spec.md.
      currency_code = "PLN"
      units         = "80"
    }
  }

  threshold_rules {
    threshold_percent = 0.5
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 0.9
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }

  all_updates_rule {
    # All four attributes set explicitly. Provider would otherwise default
    # `enable_project_level_recipients` to false and `schema_version` to "1.0";
    # making the defaults visible avoids plan/HCL drift confusion for future
    # readers (per L7 in PR #3 review).
    monitoring_notification_channels = [google_monitoring_notification_channel.ops_email.id]
    disable_default_iam_recipients   = true
    enable_project_level_recipients  = false
    schema_version                   = "1.0"
  }
}
