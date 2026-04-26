#!/usr/bin/env bash
#
# check-no-provider-sdk-imports.sh
#
# Static guardrail enforcing spec FR-014 / constitution §12 / ADR-002:
# only the canonical Vertex wrapper modules may import a model-provider SDK.
#
# Allowlist (the two underscore-prefixed leaves of `app/backend/llm/`):
#   - app/backend/llm/_real_backend.py
#   - app/backend/llm/_mock_backend.py
#
# Blocked imports:
#   import|from  vertexai
#   import|from  google.genai
#   import|from  google.cloud.aiplatform
#   import|from  anthropic
#   import|from  openai
#
# Exit 0 on a clean tree, exit 1 with the violation file:line in stderr
# otherwise. The pre-commit hook and the (future) CI step both invoke
# this script unchanged.

set -euo pipefail

PATTERN='^(import|from)[[:space:]]+(vertexai|google\.genai|google\.cloud\.aiplatform|anthropic|openai)([. ]|$)'

ALLOWED_FILES=(
  "app/backend/llm/_real_backend.py"
  "app/backend/llm/_mock_backend.py"
)

# ripgrep over backend Python only. -g excludes frontend; --no-heading +
# --line-number gives `path:line:content` per match.
HITS=$(rg \
  --no-heading \
  --line-number \
  --glob 'app/backend/**/*.py' \
  "$PATTERN" \
  . || true)

if [ -z "$HITS" ]; then
  exit 0
fi

VIOLATIONS=""
while IFS= read -r line; do
  # Strip leading `./` if rg emitted it.
  candidate_file="${line%%:*}"
  candidate_file="${candidate_file#./}"
  is_allowed=false
  for allowed in "${ALLOWED_FILES[@]}"; do
    if [ "$candidate_file" = "$allowed" ]; then
      is_allowed=true
      break
    fi
  done
  if [ "$is_allowed" = false ]; then
    VIOLATIONS="${VIOLATIONS}${line}"$'\n'
  fi
done <<< "$HITS"

if [ -n "$VIOLATIONS" ]; then
  printf 'ERROR: model-provider SDK imported outside the canonical wrapper:\n' >&2
  printf '%s' "$VIOLATIONS" >&2
  exit 1
fi

exit 0
