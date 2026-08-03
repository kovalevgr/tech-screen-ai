# Tasks — 033 T21 + shell

- [x] T001 Commit contracts verbatim (`turn-trace.schema.json`, `dev-session-api.yaml`) + spec kit
- [x] T002 Migration: turn_trace rich columns per row schema; flag seeds (`enforce_session_cost_ceiling`, `enable_live_orchestrator`) enabled=false; `configs/llm-limits.yaml`
- [x] T003 `PostgresTraceSink` — sync write, TraceWriteError on failure, wrapper_outcome/transition/turn_id support
- [x] T004 `PostgresCostLedger` — SUM-over-traces total, ceiling guard behind flag (warn when off)
- [x] T005 Flags registered per repo checker; call sites exist
- [x] T006 Shell service: command executor (persist→issue ordering, background RunAssessor, event feedback, scripted open/close as system transcript entries)
- [x] T007 API routes per contract + gating (flag 404, role when auth on); openapi.yaml regenerated and matching
- [x] T008 session_decision insert on ceiling breach (flag on) + `ABORTED(cost_ceiling)` path
- [x] T009 Tests: §3 still blocks UPDATE/DELETE; trace-per-call incl. failures; ceiling matrix; shell e2e mock session; ordering; gating
- [x] T010 Gates green both DB modes; live migration cycle (clean up containers); do NOT push until told

## Fix rounds

- [x] T011 Owner adjudication of spec note 5 — extend the T04 seam (`TraceRecord.response_text` / `.parsed`, populated by `call_model`); the two fields removed from `TurnTraceContext` (disjoint sources, no precedence rule); `wrapper_outcome` documented as nullable-by-design; row contract amended in-branch
- [x] T012 Reviewer gate (PASS-WITH-FINDINGS, no blockers) — double-ceiling interplay documented as designed (spec note 21 + `docs/engineering/feature-flags.md`); `ck_turn_trace_outcome` drops `trace_write_error`; `TraceRow.interview_session_id` non-optional; assessor-failure → `AssessmentFailed` tests added and assessor rows asserted to carry the transition context; Clarification 2 annotated; handoff note recorded for promoting the Interviewer's private prompt helpers
