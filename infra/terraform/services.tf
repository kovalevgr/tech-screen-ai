# =============================================================================
# TechScreen — required Google APIs (T06)
# -----------------------------------------------------------------------------
# APIs the cloud runtime needs beyond the bootstrap set (see infra/bootstrap.sh
# for storage/iam/sts/aiplatform/billingbudgets/monitoring). These five were
# enabled live on 2026-07-02 during T06 research (specs/018 research.md R9);
# this file adopts them into Terraform so a project rebuild is one apply.
#
# disable_on_destroy = false: a future `terraform destroy` of this stack must
# never switch off shared project APIs — other resources and operator tooling
# may rely on them.
# =============================================================================

locals {
  required_apis = [
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "clouderrorreporting.googleapis.com",
  ]
}

resource "google_project_service" "required" {
  for_each = toset(local.required_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
