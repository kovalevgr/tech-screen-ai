#!/usr/bin/env bash
# Visual-discipline guardrail (T03 / FR-007 + FR-008).
#
# Two ripgrep searches over app/frontend/src/:
#   1. Raw hex outside the canonical token files.
#   2. Tailwind dark-mode variants (light theme only at MVP).
#
# Exits 1 with a one-line summary + file:line list on first violation.
# Exits 0 silently on a clean tree.
#
# This script is invoked by:
#   - the `visual-discipline` pre-commit hook (.pre-commit-config.yaml)
#   - `pnpm lint:visual-discipline`
#   - reviewer sub-agent on every frontend PR
#
# The two excluded paths (tokens.ts, globals.css) are the only places a hex
# string is allowed to exist. Every other component / module / stylesheet
# resolves colour through the token roles via Tailwind utilities or CSS vars.

set -u

# Resolve the script's repo-root anchor (this file lives at
# app/frontend/scripts/, so the repo root is two levels up from $0's dir).
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
SRC_DIR="${REPO_ROOT}/app/frontend/src"

if ! command -v rg >/dev/null 2>&1; then
  echo "visual-discipline: ripgrep (rg) not found on PATH" >&2
  exit 2
fi

violations=0

# (a) Raw hex outside the canonical token files.
hex_pattern='#(?:[0-9A-Fa-f]{3,4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b'
hex_hits="$(rg -n \
  --type-add 'frontsrc:*.{ts,tsx,js,jsx,css,scss}' \
  --type frontsrc \
  -e "${hex_pattern}" \
  -g '!**/design/tokens.ts' \
  -g '!**/app/globals.css' \
  "${SRC_DIR}" || true)"
if [ -n "${hex_hits}" ]; then
  echo "visual-discipline: raw hex outside the token file"
  echo "${hex_hits}" | sed 's/^/  /'
  violations=1
fi

# (b) Tailwind dark-mode variant anywhere in the frontend tree.
# Pattern matches "<word-boundary>dark:<lowercase-letter>" so substrings like
# "darken" or "darkblue" are not flagged. The hyphen between dark and the
# colon is built into the regex by the colon itself.
dark_pattern='\bdark:[a-z]'
dark_hits="$(rg -n \
  --type-add 'frontsrc:*.{ts,tsx,js,jsx,css,scss}' \
  --type frontsrc \
  -e "${dark_pattern}" \
  "${SRC_DIR}" || true)"
if [ -n "${dark_hits}" ]; then
  echo "visual-discipline: Tailwind dark-mode variant (light theme only at MVP)"
  echo "${dark_hits}" | sed 's/^/  /'
  violations=1
fi

if [ "${violations}" -ne 0 ]; then
  echo "visual-discipline: see above. Use a token role instead." >&2
  exit 1
fi

exit 0
