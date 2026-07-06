# =============================================================================
# TechScreen — Identity Platform: internal staff SSO (T07, ADR-024)
# -----------------------------------------------------------------------------
# Staff sign in with n-ix.com Google Workspace accounts through Identity
# Platform (GCIP); the backend verifies the resulting ID tokens offline
# against the contract in docs/contracts/id-token-claims.json. The config
# below is PROJECT-GLOBAL: dev and prod share one identity plane (ADR-023
# single project — see specs/021-t07-identity-sso research R8); per-env
# enforcement is each Cloud Run service's AUTH_MODE env var.
#
# Managed here:
#   - API enablement (identitytoolkit + the Cloud Functions build path for
#     the auth-claims blocking function)
#   - google_identity_platform_config: provider posture, authorized domains,
#     blocking-function triggers (tfvars-gated — see variables)
#   - the least-privilege runtime SA for the blocking function
#
# Deliberately NOT managed here (operator runbook,
# specs/021-t07-identity-sso/quickstart.md — research R3):
#   - OAuth consent screen (brand): no honest Terraform surface exists for
#     the general consent screen.
#   - The Google provider (google_identity_platform_default_supported_idp_config):
#     that resource demands client_id/client_secret literals, which land
#     plaintext-recoverable in the GCS state object — rejected for the same
#     reason specs/018 R6 kept DB passwords out of state (constitution §5).
#     Console enablement auto-provisions the OAuth client so no secret ever
#     exists in Git, state, or a shell. NB the resource has no hosted-domain
#     restriction field anyway: n-ix.com gating lives in the blocking
#     function + backend middleware (ADR-024), which fail closed.
#   - The blocking-function deploy itself (gcloud functions deploy): same
#     code-rollout-is-not-Terraform philosophy as T06's ignore_changes[image]
#     handoff. The deployed URIs come back into terraform.tfvars and a second
#     apply registers the triggers.
# =============================================================================

locals {
  identity_apis = [
    "identitytoolkit.googleapis.com", # Identity Platform itself
    "cloudfunctions.googleapis.com",  # auth-claims blocking function (gen2)
    "cloudbuild.googleapis.com",      # gen2 function builds
  ]
}

resource "google_project_service" "identity" {
  for_each = toset(local.identity_apis)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# Creating this resource initializes Identity Platform on the project
# (provider >= 4.49 calls initializeAuth). If the live API still demands the
# one-time console/Marketplace enablement, quickstart §2 names the fallback;
# the resource adopts on re-apply.
resource "google_identity_platform_config" "default" {
  project                    = var.project_id
  autodelete_anonymous_users = false

  # Google is the ONLY sign-in path for staff — enabled via the console
  # (auto-provisioned OAuth client; see the header). Everything Terraform
  # can express is explicitly off.
  sign_in {
    allow_duplicate_emails = false

    email {
      enabled = false
    }
    phone_number {
      enabled = false
    }
    anonymous {
      enabled = false
    }
  }

  # Domains allowed to run the client-side sign-in flow: local dev + the two
  # frontend services. Backend URLs are absent on purpose — the API never
  # hosts a sign-in UI.
  authorized_domains = [
    "localhost",
    trimprefix(module.env_prod.frontend_service_url, "https://"),
    trimprefix(module.env_dev.frontend_service_url, "https://"),
  ]

  # Declared explicitly (false is also the API default) so the block the API
  # returns never shows up as a perpetual in-place diff — same normalization
  # family as the Cloud Run service-level scaling block (specs/018).
  # ADR-024 accepts one shared identity plane; tenants would be its reversal.
  multi_tenant {
    allow_tenants = false
  }

  # Registered only once the operator has deployed the function and pasted
  # its URIs into terraform.tfvars (empty defaults keep the first apply
  # clean). From the apply that registers them on, ALL sign-ins pass the
  # domain gate — Identity Platform fails sign-in when a registered blocking
  # function is unreachable (fail-closed).
  dynamic "blocking_functions" {
    for_each = (var.auth_before_create_uri != "" || var.auth_before_sign_in_uri != "") ? [1] : []

    content {
      dynamic "triggers" {
        for_each = var.auth_before_create_uri != "" ? [var.auth_before_create_uri] : []
        content {
          event_type   = "beforeCreate"
          function_uri = triggers.value
        }
      }

      dynamic "triggers" {
        for_each = var.auth_before_sign_in_uri != "" ? [var.auth_before_sign_in_uri] : []
        content {
          event_type   = "beforeSignIn"
          function_uri = triggers.value
        }
      }

      # No upstream IdP credentials flow to our function — the domain/role
      # decision needs only the event's email + verification flag (§5;
      # specs/021 research R4).
      forward_inbound_credentials {
        id_token      = false
        access_token  = false
        refresh_token = false
      }
    }
  }

  depends_on = [google_project_service.identity]
}

# Runtime identity for the auth-claims blocking function. The function only
# reads its vendored YAML and writes logs — logWriter is the whole grant.
# No keys ever (constitution §6); deploy binds it via --service-account.
resource "google_service_account" "auth_claims_fn" {
  account_id   = "techscreen-auth-claims"
  display_name = "TechScreen auth-claims blocking function"
  description  = "Runtime SA for the Identity Platform blocking function (T07, ADR-024). Deployed per specs/021-t07-identity-sso/quickstart.md §4."
}

resource "google_project_iam_member" "auth_claims_fn_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.auth_claims_fn.email}"
}
