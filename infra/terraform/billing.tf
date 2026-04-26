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
# Provider note: google_billing_budget went GA in `hashicorp/google` ~5.x;
# attribute names below match provider 5.30+. If you bump the provider,
# verify `disable_default_iam_recipients` is still supported on
# all_updates_rule.
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
  display_name    = "techscreen / project-wide $50"

  budget_filter {
    projects = ["projects/${var.project_number}"]
    # No `services` filter — covers all GCP services in the project.
    # This is the constitution §12 hard cap for total monthly spend.
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "50"
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
    monitoring_notification_channels = [google_monitoring_notification_channel.ops_email.id]
    disable_default_iam_recipients   = true
  }
}

resource "google_billing_budget" "vertex_only" {
  billing_account = var.billing_account
  display_name    = "techscreen / vertex-only $20"

  budget_filter {
    projects = ["projects/${var.project_number}"]
    services = ["services/aiplatform.googleapis.com"]
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = "20"
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
    monitoring_notification_channels = [google_monitoring_notification_channel.ops_email.id]
    disable_default_iam_recipients   = true
  }
}
