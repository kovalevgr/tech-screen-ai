#!/usr/bin/env bash
# T09 — Docker stack smoke check.
#
# Brings up the documented dev stack (--profile db --profile web), polls the
# backend /health endpoint and the frontend root until both return 200 within
# a generous budget, then tears the stack down on EXIT regardless of pass/fail.
# Used today by operators as a "did I break Docker?" check; T10 wires it into
# CI; T11 invokes it as part of the Tier-1 gate.
#
# Exit codes:
#   0 — both services reached 200 within the budget.
#   1 — at least one service failed to reach 200 (precise message on stderr).
#
# Usage:
#   bash scripts/smoke-docker-stack.sh        # default (run + tear down)
#   bash scripts/smoke-docker-stack.sh keep   # leave the stack up after success
#
# Requires: docker compose v2, curl. No Python. Runs on the HOST, not inside
# any container.

set -euo pipefail

readonly STACK_LABEL="techscreen-dev-smoke"
readonly BACKEND_URL="http://localhost:8000/health"
readonly FRONTEND_URL="http://localhost:3000/"
readonly POLL_MAX_ATTEMPTS=30      # 30 × (curl 2s + sleep 1s) ≈ 90 s ceiling
readonly POLL_CURL_TIMEOUT=2
readonly POLL_SLEEP_SECONDS=1

KEEP_RUNNING=0
if [[ "${1:-}" == "keep" ]]; then
  KEEP_RUNNING=1
fi

COMPOSE_CMD=(docker compose --profile db --profile web)

teardown() {
  local rc=$?
  if [[ ${KEEP_RUNNING} -eq 1 && ${rc} -eq 0 ]]; then
    echo "[$STACK_LABEL] keeping stack running (per 'keep' arg)"
  else
    echo "[$STACK_LABEL] tearing down…"
    "${COMPOSE_CMD[@]}" down --remove-orphans >/dev/null 2>&1 || true
  fi
  exit ${rc}
}
trap teardown EXIT

bring_up() {
  echo "[$STACK_LABEL] bringing up backend + frontend + postgres (this may build the images)…"
  "${COMPOSE_CMD[@]}" up -d --build
}

poll() {
  local name=$1
  local url=$2
  local i
  for ((i = 1; i <= POLL_MAX_ATTEMPTS; i++)); do
    local code
    code=$(curl --silent --output /dev/null --max-time "${POLL_CURL_TIMEOUT}" \
                --write-out '%{http_code}' "${url}" || true)
    if [[ "${code}" == "200" ]]; then
      echo "[$STACK_LABEL] ${name} OK (HTTP 200 at ${url}, attempt ${i})"
      return 0
    fi
    sleep "${POLL_SLEEP_SECONDS}"
  done
  echo "[$STACK_LABEL] ERROR: ${name} did not return 200 at ${url} after ${POLL_MAX_ATTEMPTS} attempts" >&2
  return 1
}

main() {
  bring_up
  poll backend  "${BACKEND_URL}"
  poll frontend "${FRONTEND_URL}"
  echo "[$STACK_LABEL] smoke PASSED"
}

main "$@"
