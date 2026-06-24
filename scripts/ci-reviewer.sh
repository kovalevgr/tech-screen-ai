#!/usr/bin/env bash
# T10 — reviewer-agent invocation PLACEHOLDER.
#
# The implementation plan calls for the `reviewer` sub-agent to run on every
# PR. The real Claude-in-CI integration needs an Anthropic API key in repo
# secrets + per-PR cost controls (token ceiling, trivial-PR opt-out) — neither
# is in place yet, and adding an uncontrolled key to CI would violate the
# spirit of constitution §12 before the guardrails exist.
#
# So T10 ships this honest placeholder: it makes the job-graph slot visible and
# self-documenting, never blocks merge, and points at the follow-up.
#
# Real integration is tracked as a follow-up task; see
# docs/engineering/ci.md §Reviewer agent.

set -euo pipefail

echo "Reviewer agent invocation DEFERRED — see docs/engineering/ci.md §Reviewer agent"
echo "(no Anthropic API key / cost controls in CI yet; this step never blocks merge)"
exit 0
