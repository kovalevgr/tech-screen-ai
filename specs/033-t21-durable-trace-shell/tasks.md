# Tasks — 033 T21 + shell

- [ ] T001 Commit contracts verbatim (`turn-trace.schema.json`, `dev-session-api.yaml`) + spec kit
- [ ] T002 Migration: turn_trace rich columns per row schema; flag seeds (`enforce_session_cost_ceiling`, `enable_live_orchestrator`) enabled=false; `configs/llm-limits.yaml`
- [ ] T003 `PostgresTraceSink` — sync write, TraceWriteError on failure, wrapper_outcome/transition/turn_id support
- [ ] T004 `PostgresCostLedger` — SUM-over-traces total, ceiling guard behind flag (warn when off)
- [ ] T005 Flags registered per repo checker; call sites exist
- [ ] T006 Shell service: command executor (persist→issue ordering, background RunAssessor, event feedback, scripted open/close as system transcript entries)
- [ ] T007 API routes per contract + gating (flag 404, role when auth on); openapi.yaml regenerated and matching
- [ ] T008 session_decision insert on ceiling breach (flag on) + `ABORTED(cost_ceiling)` path
- [ ] T009 Tests: §3 still blocks UPDATE/DELETE; trace-per-call incl. failures; ceiling matrix; shell e2e mock session; ordering; gating
- [ ] T010 Gates green both DB modes; live migration cycle (clean up containers); do NOT push until told
