#!/usr/bin/env bash
# ============================================================================
# TechScreen — GCP bootstrap
# ----------------------------------------------------------------------------
# Runs the minimum one-time setup that Terraform itself cannot do:
#   1. Enables the APIs required for Terraform to run.
#   2. Creates the GCS bucket that holds Terraform remote state.
#   3. Creates the `terraform` service account and grants it Owner.
#   4. Creates the Workload Identity Federation pool + provider so that
#      GitHub Actions can impersonate the Terraform SA without JSON keys.
#
# Prerequisites:
#   - gcloud installed and you are logged in with an account that has
#     Owner on the target project (`gcloud auth login`).
#   - gsutil available (comes with gcloud).
#   - The GCP project already exists (create it in Console if not).
#
# Idempotency: safe to re-run. Every step checks existence first.
#
# Usage:
#   PROJECT_ID=techscreen-prod GH_REPO=your-org/techscreen ./bootstrap.sh
# ============================================================================

set -euo pipefail

# -------- Config (override via env) -----------------------------------------
PROJECT_ID="${PROJECT_ID:?PROJECT_ID env var is required, e.g. techscreen-prod}"
REGION="${REGION:-europe-west1}"
TF_STATE_BUCKET="${TF_STATE_BUCKET:-${PROJECT_ID}-tf-state}"
TF_SA_NAME="${TF_SA_NAME:-terraform}"
TF_SA_EMAIL="${TF_SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# Workload Identity Federation for GitHub
GH_POOL_NAME="${GH_POOL_NAME:-github-actions}"
GH_PROVIDER_NAME="${GH_PROVIDER_NAME:-github}"
GH_REPO="${GH_REPO:?GH_REPO env var is required, e.g. your-org/techscreen}"

# -------- Preflight ---------------------------------------------------------
command -v gcloud >/dev/null || { echo "ERROR: gcloud not installed"; exit 1; }
command -v gsutil >/dev/null || { echo "ERROR: gsutil not installed"; exit 1; }

echo "==> Active project: ${PROJECT_ID}"
gcloud config set project "${PROJECT_ID}" >/dev/null

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
echo "    project number: ${PROJECT_NUMBER}"

# -------- 1. Enable bootstrap APIs ------------------------------------------
# These cover both:
#   (a) the absolute minimum Terraform itself needs to run (resourcemanager,
#       iam, iamcredentials, serviceusage, storage, sts)
#   (b) APIs that any subsequent terraform apply will require, so Ihor does not
#       hit "API not enabled" mid-apply on a fresh project. Enabling here is
#       idempotent and free.
#
# T01a-required additions (specs/003-vertex-quota-region/):
#   - aiplatform.googleapis.com    Vertex AI (smoke test + every later LLM call;
#                                  spec Assumption explicitly relies on this)
#   - billingbudgets.googleapis.com  google_billing_budget resources (Phase 5)
#   - monitoring.googleapis.com    google_monitoring_notification_channel +
#                                  later observability work (T38+)
#
# T06+ will append more APIs (run, sqladmin, secretmanager, artifactregistry,
# identitytoolkit) when those resources actually land. Each addition is
# documented in the same spirit: name the resource that needs it.
echo "==> Enabling bootstrap APIs"
gcloud services enable \
  cloudresourcemanager.googleapis.com \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  serviceusage.googleapis.com \
  storage.googleapis.com \
  sts.googleapis.com \
  aiplatform.googleapis.com \
  billingbudgets.googleapis.com \
  monitoring.googleapis.com

# -------- 2. GCS bucket for Terraform state ---------------------------------
if gsutil ls -b "gs://${TF_STATE_BUCKET}" >/dev/null 2>&1; then
  echo "==> TF state bucket gs://${TF_STATE_BUCKET} already exists"
else
  echo "==> Creating TF state bucket gs://${TF_STATE_BUCKET}"
  gsutil mb -l "${REGION}" -b on "gs://${TF_STATE_BUCKET}"
fi

echo "==> Enabling versioning + lifecycle on state bucket"
gsutil versioning set on "gs://${TF_STATE_BUCKET}" >/dev/null

LIFECYCLE=$(mktemp)
cat > "${LIFECYCLE}" <<'JSON'
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {"numNewerVersions": 30, "isLive": false}
      }
    ]
  }
}
JSON
gsutil lifecycle set "${LIFECYCLE}" "gs://${TF_STATE_BUCKET}" >/dev/null
rm -f "${LIFECYCLE}"

# -------- 3. Terraform service account --------------------------------------
if gcloud iam service-accounts describe "${TF_SA_EMAIL}" >/dev/null 2>&1; then
  echo "==> Terraform SA ${TF_SA_EMAIL} already exists"
else
  echo "==> Creating Terraform SA ${TF_SA_EMAIL}"
  gcloud iam service-accounts create "${TF_SA_NAME}" \
    --display-name="Terraform automation"
fi

echo "==> Granting roles/owner to Terraform SA (MVP; narrow down later)"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${TF_SA_EMAIL}" \
  --role="roles/owner" \
  --condition=None >/dev/null

# -------- 4. Workload Identity Federation -----------------------------------
echo "==> Setting up Workload Identity Federation for GitHub (${GH_REPO})"

if gcloud iam workload-identity-pools describe "${GH_POOL_NAME}" \
     --location="global" >/dev/null 2>&1; then
  echo "    WIF pool already exists"
else
  gcloud iam workload-identity-pools create "${GH_POOL_NAME}" \
    --location="global" \
    --display-name="GitHub Actions Pool"
fi

if gcloud iam workload-identity-pools providers describe "${GH_PROVIDER_NAME}" \
     --workload-identity-pool="${GH_POOL_NAME}" \
     --location="global" >/dev/null 2>&1; then
  echo "    WIF OIDC provider already exists"
else
  gcloud iam workload-identity-pools providers create-oidc "${GH_PROVIDER_NAME}" \
    --workload-identity-pool="${GH_POOL_NAME}" \
    --location="global" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition="assertion.repository == '${GH_REPO}'"
fi

POOL_FULL="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${GH_POOL_NAME}"

echo "==> Binding GitHub repo ${GH_REPO} -> impersonate ${TF_SA_EMAIL}"
gcloud iam service-accounts add-iam-policy-binding "${TF_SA_EMAIL}" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/${POOL_FULL}/attribute.repository/${GH_REPO}" \
  >/dev/null

# -------- 5. Summary --------------------------------------------------------
cat <<EOF

=================================================================
Bootstrap complete.

Project:           ${PROJECT_ID} (${PROJECT_NUMBER})
Region:            ${REGION}
TF state bucket:   gs://${TF_STATE_BUCKET}
Terraform SA:      ${TF_SA_EMAIL}
WIF pool:          ${POOL_FULL}
WIF provider:      ${POOL_FULL}/providers/${GH_PROVIDER_NAME}

-----------------------------------------------------------------
Next steps
-----------------------------------------------------------------

1. Add to infra/terraform/backend.tf:

   terraform {
     backend "gcs" {
       bucket = "${TF_STATE_BUCKET}"
       prefix = "terraform/state"
     }
   }

2. Local 'terraform apply' (your user account has Owner):

   gcloud auth application-default login
   cd infra/terraform
   terraform init
   terraform plan

3. GitHub Actions snippet (no JSON keys):

   permissions:
     id-token: write
     contents: read

   - uses: google-github-actions/auth@v2
     with:
       workload_identity_provider: ${POOL_FULL}/providers/${GH_PROVIDER_NAME}
       service_account: ${TF_SA_EMAIL}

=================================================================
EOF
