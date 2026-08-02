#!/usr/bin/env bash
#
# check-no-provider-sdk-imports.sh
#
# Static guardrail enforcing spec FR-014 / constitution §12 / ADR-002:
# only the canonical Vertex wrapper modules may import a model-provider SDK.
#
# Allowlist:
#   - app/backend/llm/_real_backend.py   (the SDK adapter)
#   - app/backend/llm/_mock_backend.py   (forward-compat; imports nothing today)
#   - app/backend/tests/llm/test_prompt_schema_transport.py
#     (030 offline regression — pins the installed SDK's pre-network
#     schema-transport behaviour, so it must import the SDK directly)
#
# Blocked imports:
#   import|from  vertexai
#   import|from  google.genai
#   import|from  google.cloud.aiplatform
#   import|from  anthropic
#   import|from  openai
#
# A second check (030) forbids the `GenAiAPIError` re-export from being
# consumed outside `_real_backend.py` and its taxonomy test — importing
# the alias would otherwise bypass the SDK-module grep.
#
# Exit 0 on a clean tree, exit 1 with the violation file:line in stderr
# otherwise. The pre-commit hook and the (future) CI step both invoke
# this script unchanged.

set -euo pipefail

PATTERN='^(import|from)[[:space:]]+(vertexai|google\.genai|google\.cloud\.aiplatform|anthropic|openai)([. ]|$)'

ALLOWED_FILES=(
  "app/backend/llm/_real_backend.py"
  "app/backend/llm/_mock_backend.py"
  "app/backend/tests/llm/test_prompt_schema_transport.py"
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

# Second check (030): `_real_backend.py` re-exports the SDK error type as
# `GenAiAPIError` for the taxonomy tests ONLY. Importing that alias from a
# non-allowlisted module would bypass the SDK-module grep above, so any
# other occurrence fails the guardrail.
REEXPORT_PATTERN='GenAiAPIError'

REEXPORT_ALLOWED_FILES=(
  "app/backend/llm/_real_backend.py"
  "app/backend/tests/llm/test_real_backend.py"
)

REEXPORT_HITS=$(rg \
  --no-heading \
  --line-number \
  --glob 'app/backend/**/*.py' \
  "$REEXPORT_PATTERN" \
  . || true)

REEXPORT_VIOLATIONS=""
if [ -n "$REEXPORT_HITS" ]; then
  while IFS= read -r line; do
    candidate_file="${line%%:*}"
    candidate_file="${candidate_file#./}"
    is_allowed=false
    for allowed in "${REEXPORT_ALLOWED_FILES[@]}"; do
      if [ "$candidate_file" = "$allowed" ]; then
        is_allowed=true
        break
      fi
    done
    if [ "$is_allowed" = false ]; then
      REEXPORT_VIOLATIONS="${REEXPORT_VIOLATIONS}${line}"$'\n'
    fi
  done <<< "$REEXPORT_HITS"
fi

if [ -n "$REEXPORT_VIOLATIONS" ]; then
  printf 'ERROR: GenAiAPIError (SDK error re-export) used outside its allowlist.\n' >&2
  printf 'It exists for app/backend/tests/llm/test_real_backend.py ONLY —\n' >&2
  printf 'consume the SDK-free BackendError hierarchy instead:\n' >&2
  printf '%s' "$REEXPORT_VIOLATIONS" >&2
  exit 1
fi

exit 0
