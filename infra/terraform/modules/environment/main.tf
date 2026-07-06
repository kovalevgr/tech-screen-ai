# =============================================================================
# TechScreen environment module (T06) — one long-lived environment (ADR-023).
#
# Contents, in dependency order:
#   1. Data plane  — Cloud SQL instance + databases + users
#   2. Identity    — runtime service accounts + IAM (least privilege,
#                    constitution §6: no JSON keys, ever)
#   3. Secrets     — empty Secret Manager shells (constitution §5: values are
#                    filled manually post-apply, never in Git or state)
#   4. Runtime     — Cloud Run v2 services on a placeholder image; image
#                    ownership is handed to T06a's /deploy via ignore_changes
#
# See specs/018-t06-cloud-runtime/data-model.md for the full resource table
# and the identity → access matrix.
# =============================================================================

# -----------------------------------------------------------------------------
# 1. Data plane — Cloud SQL (research R1, R5, R6)
# -----------------------------------------------------------------------------

resource "google_sql_database_instance" "pg" {
  name             = "techscreen-pg${var.name_suffix}"
  database_version = "POSTGRES_17" # verified available in europe-west1 2026-07-02 (R1)
  region           = var.region

  # A bad day must not silently drop an interview database (§1, §3).
  deletion_protection = true

  # Cost-idle mode (owner decision 2026-07-05): the operator sleeps/wakes
  # instances via scripts/cloud-sql-power.sh (activation policy NEVER/ALWAYS)
  # while the project has no real traffic. Same ownership split as the Cloud
  # Run image: Terraform owns the shape, the operator owns the on/off toggle.
  # See docs/engineering/cloud-setup.md § Cost-idle mode.
  lifecycle {
    ignore_changes = [
      settings[0].activation_policy,
    ]
  }

  settings {
    tier      = "db-f1-micro"
    edition   = "ENTERPRISE"
    disk_size = 10
    disk_type = "PD_SSD"

    ip_configuration {
      # Public IP, zero authorised networks: access only via Cloud SQL Auth
      # Proxy / connectors with IAM (docs/engineering/cloud-setup.md §Networking).
      ipv4_enabled = true
    }

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
      transaction_log_retention_days = 7

      backup_retention_settings {
        retained_backups = 7
      }
    }

    # Required for the CI flag-sync identity to authenticate as itself
    # (CLOUD_IAM_SERVICE_ACCOUNT user below) instead of holding a password.
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }

    user_labels = {
      env = var.env
    }
  }
}

resource "google_sql_database" "techscreen" {
  name     = "techscreen"
  instance = google_sql_database_instance.pg.name
}

# Alembic autogenerate target (docs/engineering/cloud-setup.md resource inventory).
resource "google_sql_database" "techscreen_shadow" {
  name     = "techscreen_shadow"
  instance = google_sql_database_instance.pg.name
}

# Built-in roles (techscreen_app, techscreen_migrator) are deliberately NOT
# Terraform resources: the Cloud SQL API refuses to create a Postgres user
# without a password (verified on first apply, 2026-07-02), and a password in
# HCL or state would violate §5 (research R6 amendment). The operator creates
# both users out-of-band — see specs/018-t06-cloud-runtime/quickstart.md §4.

# CI flag-sync identity as an IAM-authenticated DB user (research R5). The
# Postgres username is the SA email minus ".gserviceaccount.com". Table-level
# grants are applied post-migration via scripts/cloud-db-grants.sql.
resource "google_sql_user" "flag_sync" {
  name     = trimsuffix(var.flag_sync_sa_email, ".gserviceaccount.com")
  instance = google_sql_database_instance.pg.name
  type     = "CLOUD_IAM_SERVICE_ACCOUNT"
}

# -----------------------------------------------------------------------------
# 2. Identity — runtime service accounts + IAM
# -----------------------------------------------------------------------------

# Prod note: the prod instance of this SA predates the module (seeded by T01a).
# It is adopted via `terraform state mv` — see specs/018 quickstart.md §2.
resource "google_service_account" "backend" {
  account_id   = "techscreen-backend${var.name_suffix}"
  display_name = "TechScreen backend runtime (${var.env})"
  description  = "Runtime identity for the ${var.env} Cloud Run backend. Seeded by T01a (prod) / created by T06 (dev); role set defined in specs/018-t06-cloud-runtime/data-model.md."
}

resource "google_service_account" "frontend" {
  account_id   = "techscreen-frontend${var.name_suffix}"
  display_name = "TechScreen frontend runtime (${var.env})"
  description  = "Runtime identity for the ${var.env} Cloud Run frontend. Minimal: logs + metrics only — no SQL, no Secret Manager (data-model.md access matrix)."
}

resource "google_project_iam_member" "backend_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "frontend_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_project_iam_member" "frontend_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.frontend.email}"
}

# Short-lived token impersonation for the operator (smoke tests) — the §6
# alternative to JSON keys. Prod binding predates the module (T01a; adopted
# via state mv); dev gets the same shape.
resource "google_service_account_iam_member" "backend_tokens_for_operator" {
  service_account_id = google_service_account.backend.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "user:${var.operator_email}"
}

# -----------------------------------------------------------------------------
# 3. Secrets — empty shells, per-secret access (constitution §5–6)
# -----------------------------------------------------------------------------

locals {
  # Every SECRET key from .env.example (ADR-022: non-secret keys stay env vars).
  secret_names = [
    "DATABASE_URL",
    "MAGIC_LINK_SIGNING_KEY",
    "SESSION_COOKIE_SECRET",
    "SENDGRID_API_KEY",
    "CALIBRATION_DATASET_KEY",
  ]

  # Backend-consumed subset: gets per-secret accessor for the backend SA.
  # CALIBRATION_DATASET_KEY is consumed by calibration tooling, not the
  # backend — no runtime accessor (data-model.md access matrix).
  backend_readable_secrets = [
    "DATABASE_URL",
    "MAGIC_LINK_SIGNING_KEY",
    "SESSION_COOKIE_SECRET",
    "SENDGRID_API_KEY",
  ]
}

resource "google_secret_manager_secret" "env" {
  for_each = toset(local.secret_names)

  secret_id = "${each.value}${var.secret_suffix}"

  labels = {
    env = var.env
  }

  replication {
    auto {}
  }
}

# Per-secret grants only — never project-level (spec FR-006, SC-003).
resource "google_secret_manager_secret_iam_member" "backend_accessor" {
  for_each = toset(local.backend_readable_secrets)

  secret_id = google_secret_manager_secret.env[each.value].id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backend.email}"
}

# -----------------------------------------------------------------------------
# 4. Runtime — Cloud Run v2 shells (research R7)
# -----------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "backend" {
  name     = "techscreen-backend${var.name_suffix}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.backend.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      # Placeholder until T06a's /deploy pushes the real image; Terraform
      # permanently ignores image drift below so deploys never fight state.
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }

  labels = {
    env = var.env
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      # The /deploy workflow names revisions explicitly (sha-run-attempt);
      # Terraform must not null it back — deploys own revision naming (T06a).
      template[0].revision,
      client,
      client_version,
      # API populates an empty service-level scaling block we do not manage
      # (instance counts live in template.scaling) — ignoring kills the
      # perpetual in-place diff that would break the SC-001 clean plan.
      scaling,
    ]
  }
}

resource "google_cloud_run_v2_service" "frontend" {
  name     = "techscreen-frontend${var.name_suffix}"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.frontend.email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "us-docker.pkg.dev/cloudrun/container/hello"

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }
    }
  }

  labels = {
    env = var.env
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
      # The /deploy workflow names revisions explicitly (sha-run-attempt);
      # Terraform must not null it back — deploys own revision naming (T06a).
      template[0].revision,
      client,
      client_version,
      # API populates an empty service-level scaling block we do not manage
      # (instance counts live in template.scaling) — ignoring kills the
      # perpetual in-place diff that would break the SC-001 clean plan.
      scaling,
    ]
  }
}

# Public *.run.app posture per cloud-setup.md §Networking: recruiter surface is
# SSO-gated at the app layer (T07); candidate surface is magic-link gated (T28).
resource "google_cloud_run_v2_service_iam_member" "backend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
