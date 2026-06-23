#!/usr/bin/env bash
# T10 — detect destructive DDL in changed Alembic migrations (constitution §10).
#
# Scans the changed alembic/versions/*.py files for the §10-forbidden patterns:
#   - DROP COLUMN      (column removal — data loss)
#   - DROP TABLE       (table removal — catastrophic data loss)
#   - ALTER COLUMN ... TYPE   (type narrowing — truncation/cast risk)
#
# Our migrations express DDL as raw op.execute("...") strings, so matching
# inside string literals is intended — that is exactly where destructive DDL
# lives (research §4).
#
# Behaviour:
#   - Changed files are taken from the args, or derived via
#     `git diff --name-only "${BASE_REF:-origin/main}"...HEAD -- 'alembic/versions/*.py'`.
#   - Writes `needs_adr=true|false` to $GITHUB_OUTPUT (when set) and echoes a
#     human-readable summary to stdout.
#   - ALWAYS exits 0 — the `needs-adr` label is the signal, not the exit code
#     (the CI label step reads the needs_adr output).
#
# Local usage: bash scripts/ci-detect-destructive-ddl.sh path/to/migration.py
#         or:  BASE_REF=origin/main bash scripts/ci-detect-destructive-ddl.sh

set -euo pipefail

readonly DROP_COLUMN='DROP[[:space:]]+COLUMN'
readonly DROP_TABLE='DROP[[:space:]]+TABLE'
readonly ALTER_TYPE='ALTER[[:space:]]+COLUMN[[:space:]]+[A-Za-z_][A-Za-z0-9_]*[[:space:]]+TYPE'
readonly PATTERN="${DROP_COLUMN}|${DROP_TABLE}|${ALTER_TYPE}"

emit_output() {
  # Write a key=value pair to $GITHUB_OUTPUT when running under Actions.
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "$1" >> "${GITHUB_OUTPUT}"
  fi
}

# Resolve the list of changed migration files.
declare -a files=()
if [[ "$#" -gt 0 ]]; then
  files=("$@")
else
  base_ref="${BASE_REF:-origin/main}"
  # `git diff` may legitimately produce no matches; tolerate that under set -e.
  mapfile -t files < <(git diff --name-only "${base_ref}...HEAD" -- 'alembic/versions/*.py' 2>/dev/null || true)
fi

if [[ "${#files[@]}" -eq 0 ]]; then
  echo "ci-detect-destructive-ddl: no changed migration files to scan"
  emit_output "needs_adr=false"
  exit 0
fi

found=0
for f in "${files[@]}"; do
  [[ -f "$f" ]] || continue
  if grep -nEi "${PATTERN}" "$f" >/dev/null 2>&1; then
    found=1
    echo "::warning file=${f}::destructive DDL detected — this migration needs a linked ADR (constitution §10)"
    grep -nEi "${PATTERN}" "$f" | sed "s|^|  ${f}:|"
  fi
done

if [[ "${found}" -eq 1 ]]; then
  echo "ci-detect-destructive-ddl: destructive DDL FOUND — needs_adr=true"
  emit_output "needs_adr=true"
else
  echo "ci-detect-destructive-ddl: no destructive DDL — needs_adr=false"
  emit_output "needs_adr=false"
fi

exit 0
