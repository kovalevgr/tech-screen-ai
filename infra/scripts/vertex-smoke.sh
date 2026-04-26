#!/usr/bin/env bash
# ============================================================================
# TechScreen — Vertex AI smoke test (T01a — FR-006)
# ----------------------------------------------------------------------------
# Issues a minimal generateContent call against Gemini 2.5 Flash in the
# project's region, impersonating the runtime SA (techscreen-backend@…) via
# short-lived ADC tokens — no JSON keys (constitution §6).
#
# On success, prints ONE line on stdout in the comma-separated key=value
# format defined by specs/003-vertex-quota-region/contracts/vertex-quota-log-format.md §5,
# which the operator appends verbatim (with date prefix) to the
# "Smoke-test records" section of docs/engineering/vertex-quota.md.
#
# Prerequisites:
#   - gcloud + python3 + curl installed; you are authenticated as a principal
#     with roles/iam.serviceAccountTokenCreator on the runtime SA (granted by
#     iam.tf during T020).
#   - The runtime SA exists with roles/aiplatform.user (also iam.tf, T020).
#   - Vertex AI for gemini-2.5-flash in europe-west1 is reachable. Per
#     Clarifications 2026-04-26, 2.5 GA models use a global TPM quota with
#     defaults ~5 orders of magnitude above PoC need — see
#     docs/engineering/vertex-quota.md §"Quota observed defaults" for the
#     observed values; no quota-raise request is needed for 2.5.
#
# Usage:
#   PROJECT_ID=tech-screen-493720 \
#     bash infra/scripts/vertex-smoke.sh
#
#   # Optional overrides:
#   RUNTIME_SA=techscreen-backend@tech-screen-493720.iam.gserviceaccount.com \
#   REGION=europe-west1 \
#   MODEL=gemini-2.5-flash \
#     bash infra/scripts/vertex-smoke.sh
#
# Exit codes:
#   0 — success (HTTP 200 AND latency < 10000 ms). One stdout line, status=pass.
#   1 — failure (any non-200 OR timeout OR latency >= 10000 ms).
#       One stdout line, status=fail, optional notes=<short-token>.
# ============================================================================

set -euo pipefail

# -------- Config (override via env) -----------------------------------------
PROJECT_ID="${PROJECT_ID:?PROJECT_ID env var is required, e.g. tech-screen-493720}"
REGION="${REGION:-europe-west1}"
MODEL="${MODEL:-gemini-2.5-flash}"
RUNTIME_SA="${RUNTIME_SA:-techscreen-backend@${PROJECT_ID}.iam.gserviceaccount.com}"

# Hard cap matching FR-006 / SC-004 / contract §5.
LATENCY_LIMIT_MS=10000

# -------- Preflight ---------------------------------------------------------
command -v gcloud  >/dev/null || { echo "ERROR: gcloud not installed"  >&2; exit 1; }
command -v curl    >/dev/null || { echo "ERROR: curl not installed"    >&2; exit 1; }
command -v python3 >/dev/null || { echo "ERROR: python3 not installed" >&2; exit 1; }

# Portable wall-clock millisecond timestamp.
# `date +%s%N` is GNU-only — BSD `date` (stock macOS) returns a literal `N`
# instead of nanoseconds and breaks integer arithmetic. python3 is universally
# available on every contributor machine + CI image and yields the same value
# regardless of OS.
now_ms() { python3 -c 'import time; print(int(time.time() * 1000))'; }

# Per-run temp file for the response body, auto-cleaned on EXIT (success OR
# failure). `mktemp -t` avoids the previous /tmp/vertex-smoke.body race when
# two operators ran on the same host.
BODY_FILE="$(mktemp -t vertex-smoke.XXXXXX)"
trap 'rm -f "${BODY_FILE}"' EXIT

# -------- Get short-lived access token via impersonation --------------------
# This is the §6-safe path: no JSON key, token lives ~1h, scoped to the SA.
TOKEN="$(gcloud auth print-access-token --impersonate-service-account="${RUNTIME_SA}")"
if [[ -z "${TOKEN}" ]]; then
  echo "runner=local-adc-impersonation, model=${MODEL}, region=${REGION}, latency_ms=0, status=fail, notes=no-token"
  exit 1
fi

# -------- Build endpoint + payload ------------------------------------------
ENDPOINT="https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT_ID}/locations/${REGION}/publishers/google/models/${MODEL}:generateContent"

# 8-token cap keeps cost <$0.0001 per run.
PAYLOAD='{"contents":[{"role":"user","parts":[{"text":"ok"}]}],"generationConfig":{"maxOutputTokens":8,"temperature":0}}'

# -------- Bracket-measure wall-clock latency around the curl ----------------
T0_MS=$(now_ms)

# `curl --max-time 15` aborts after 15s wall-clock; we still enforce a tighter
# 10000ms post-hoc check below.
HTTP_CODE=$(curl -sS \
  --max-time 15 \
  -o "${BODY_FILE}" \
  -w '%{http_code}' \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -X POST "${ENDPOINT}" \
  -d "${PAYLOAD}" || echo "000")

T1_MS=$(now_ms)
LATENCY_MS=$((T1_MS - T0_MS))

# -------- Decide pass/fail and emit contract-§5 line ------------------------
STATUS="fail"
NOTES=""

if [[ "${HTTP_CODE}" == "200" ]]; then
  if (( LATENCY_MS < LATENCY_LIMIT_MS )); then
    STATUS="pass"
  else
    NOTES="latency-over-${LATENCY_LIMIT_MS}ms"
  fi
elif [[ "${HTTP_CODE}" == "000" ]]; then
  NOTES="timeout-or-network"
else
  # http429, http403, http5xx, etc. NO commas inside the value.
  NOTES="http${HTTP_CODE}"
fi

LINE="runner=local-adc-impersonation, model=${MODEL}, region=${REGION}, latency_ms=${LATENCY_MS}, status=${STATUS}"
[[ -n "${NOTES}" ]] && LINE="${LINE}, notes=${NOTES}"

echo "${LINE}"

[[ "${STATUS}" == "pass" ]] && exit 0 || exit 1
