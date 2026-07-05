#!/usr/bin/env bash
# Sleep/wake the TechScreen Cloud SQL instances (cost-idle mode).
#
# Owner decision 2026-07-05: while the project has no real traffic, both
# instances stay STOPPED (~$4-5/mo storage-only) and are woken on demand
# for migrations, flag-sync merges, /deploy smokes, or any DB-touching work.
# Terraform deliberately ignores settings.activation_policy (see the module's
# lifecycle block) so this toggle never shows up as drift.
#
# Usage:
#   scripts/cloud-sql-power.sh sleep [prod|dev|all]   # default: all
#   scripts/cloud-sql-power.sh wake  [prod|dev|all]
#   scripts/cloud-sql-power.sh status
#
# Wake takes ~60-90 s; the script waits until the instance is RUNNABLE.
# Remember: while asleep, the sync-feature-flags workflow and anything else
# that dials the DB will fail — wake first, then re-dispatch.

set -euo pipefail

PROJECT="tech-screen-493720"
ACTION="${1:-status}"
TARGET="${2:-all}"

instances() {
  case "$TARGET" in
    prod) echo "techscreen-pg" ;;
    dev)  echo "techscreen-pg-dev" ;;
    all)  echo "techscreen-pg techscreen-pg-dev" ;;
    *)    echo "unknown target '$TARGET' (want prod|dev|all)" >&2; exit 2 ;;
  esac
}

case "$ACTION" in
  status)
    gcloud sql instances list --project "$PROJECT" \
      --format='table(name,state,settings.activationPolicy)'
    ;;
  sleep|wake)
    policy="NEVER"
    [ "$ACTION" = "wake" ] && policy="ALWAYS"
    for inst in $(instances); do
      echo ">> $ACTION $inst (activation-policy=$policy)"
      gcloud sql instances patch "$inst" --project "$PROJECT" \
        --activation-policy="$policy" --quiet
    done
    if [ "$ACTION" = "wake" ]; then
      for inst in $(instances); do
        for _ in $(seq 1 30); do
          state=$(gcloud sql instances describe "$inst" --project "$PROJECT" \
            --format='value(state)')
          [ "$state" = "RUNNABLE" ] && { echo ">> $inst is RUNNABLE"; break; }
          sleep 5
        done
      done
    fi
    "$0" status
    ;;
  *)
    echo "usage: $0 {sleep|wake|status} [prod|dev|all]" >&2
    exit 2
    ;;
esac
