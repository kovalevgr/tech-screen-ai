# ADR-003: Model selection — Gemini 2.5 Flash and Pro

- **Status:** Accepted
- **Date:** 2026-04-18

## Context

Each of our three agents has different cost/latency/quality constraints.

- **Interviewer** runs dozens of turns per session, must feel conversational, and drives user-perceived latency. Needs low p95 latency (< 3s) and low per-token cost.
- **Assessor** runs once per candidate turn, produces structured JSON, and must be faithful to the rubric. Needs strong instruction-following and JSON-mode reliability; latency can be 3–5s.
- **Pre-Interview Planner** runs once per session before the interview starts. Produces an `InterviewPlan`. Latency is not user-facing (5–15s acceptable). Quality of reasoning over position template and past annotations matters most.

## Decision

- **Interviewer:** Gemini 2.5 **Flash** (low latency, low cost).
- **Assessor:** Gemini 2.5 **Flash** (with strict JSON schema and temperature 0).
- **Pre-Interview Planner:** Gemini 2.5 **Pro** (better reasoning, quality > latency for offline generation).

The A/B comparison with Claude Sonnet 4.6 on Ukrainian interview content is deferred until after the first pilot sessions produce enough labelled turns (see ADR-020 and Roadmap H1).

## Consequences

**Positive.**
- Flash cost on Interviewer + Assessor keeps per-session spend at ~$0.15–0.30 (see constitution §12 budget model).
- Pro on the Planner produces notably better seed question coverage than Flash in pilot tests.
- One model family across three agents simplifies prompt engineering, context window assumptions, and observability.

**Negative.**
- Flash under-performs on nuanced Ukrainian grammar edge cases. Compensation: explicit `UKRAINIAN STYLE ANCHORS` section in prompts (constitution §11).
- Gemini 2.5 Pro has higher TPS cost (~5× Flash) — but it runs once per session, not per turn, so absolute cost remains small.

**Mitigation.**
- Model name is a config value (`configs/models.yaml`), not a hard-coded constant. Swapping a model for a calibration test is a config change, not a code change.
- Per-agent cost tracking (§12) surfaces regressions early.
