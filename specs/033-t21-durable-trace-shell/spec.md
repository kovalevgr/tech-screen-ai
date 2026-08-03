# Feature spec — T21 Durable TurnTrace + Cost Ceiling, plus the T22 backend shell

**Status**: Draft · **Branch**: `033-t21-durable-trace-shell` · **Authored by**: main loop (policy rev. 2)
**Contracts**: [`docs/contracts/turn-trace.schema.json`](../../docs/contracts/turn-trace.schema.json) (row shape) · [`docs/contracts/dev-session-api.yaml`](../../docs/contracts/dev-session-api.yaml) (shell surface) · state-machine contract §9/§11 (shell obligations)

## What / why

Two tightly-coupled backend deliverables: (1) T21 — every LLM call leaves a durable, append-only `turn_trace` row and a durable per-session cost total with a §12 ceiling behind a dark flag; (2) the imperative shell over the T20 machine, exposed as the dev-only session API — the missing backend half of T22. One stream because they share the persistence layer and the shell is the first real writer of traces.

## Functional requirements

- **FR-033-1** Migration: rich `turn_trace` columns per the committed row schema (the T05 docstring anchor names them); forward-only, additive; §3 trigger/REVOKE untouched and still effective (test proves UPDATE/DELETE still raise).
- **FR-033-2** `PostgresTraceSink` (TraceSink protocol): synchronous write before `call_model` returns; write failure → `TraceWriteError` (§1 trumps an otherwise-OK call — T04 semantics, unchanged). Populates `turn_id`, `wrapper_outcome`, `transition` when the caller provides orchestrator context.
- **FR-033-3** `PostgresCostLedger` (CostLedger protocol): running total = SUM over the session's trace rows (no second table); pre-call guard raises `SessionBudgetExceeded` when flag `enforce_session_cost_ceiling` is enabled AND total ≥ ceiling from `configs/llm-limits.yaml` (new, default 5.00 USD, §16). Flag default **false** (§9): guard logs a structured warning instead of raising.
- **FR-033-4** Flag registration per repo rules: `configs/feature-flags.yaml` entries + seeding migration rows `enabled=false` for `enforce_session_cost_ceiling` AND `enable_live_orchestrator`.
- **FR-033-5** Shell (`app/backend/services/dev_session.py` + `app/backend/api/dev_sessions.py`): implements `docs/contracts/dev-session-api.yaml` exactly. Ordering per spec-032 Clarification 4: persist state after EVERY transition, BEFORE issuing wrapper calls; `RunAssessor` commands run as FastAPI background tasks; `AssessmentCompleted/Failed` events fed back through the same transition+persist path. Command idempotency honored on re-issue.
- **FR-033-6** Gating: routes return 404 when `enable_live_orchestrator` is disabled; role-gated (reviewer/admin) when `AUTH_MODE=identity_platform`. No candidate-facing surface.
- **FR-033-7** `app/backend/openapi.yaml` regenerated; generated paths/schemas for `/api/dev/*` match the committed contract (CI regen test stays green).
- **FR-033-8** Cost-ceiling breach flow: guard raise → shell maps to machine event per state-machine contract §2 (`ABORTED(cost_ceiling)`) → `session_decision` row (`reason=cost_ceiling`) — append-only insert; observed metric name constant `techscreen_session_cost_usd` recorded for T38.

## Clarifications (decided — do not reopen)

1. Cost total derives from `turn_trace` (single source, no drift); in-process memo allowed as cache only.
2. `wrapper_outcome` closes the "trace says ok but wrapper rejected" seam recorded in specs 031/032 — the agent wrappers currently can't report it themselves; the SHELL records `rejected/contract_miss_retried` from the typed exceptions it catches. Direct wrapper self-reporting is a possible later refinement, out of scope.
3. Scripted opening/closing are delivered by the shell (transcript `role=system` entries from the repo prompt files), not via LLM calls.
4. Dev-only transcript lives inside `session_state` (the machine already accumulates what the UI needs via commands' payloads — extend the SHELL-side view assembly, not the machine). The state machine module is NOT modified in this branch; if a genuine gap blocks the shell, STOP and report — do not patch the core.

## Success criteria

- SC-1 Trace row written for every call through the shell (incl. failed calls with non-ok outcomes); UPDATE/DELETE still blocked at DB level.
- SC-2 Ceiling test: mocked cost stream crosses 5.00 → flag off: warning only; flag on: `SessionBudgetExceeded` + `ABORTED(cost_ceiling)` + `session_decision` row (T21 acceptance from the implementation plan).
- SC-3 Full dev-session happy path against the MOCK backend in tests: create → turns → COMPLETED, every turn traced (this is the seed of T23).
- SC-4 Gates green (both DB modes); migration cycle live-verified; openapi regen equality.
- SC-5 No changes to `app/backend/orchestrator/state_machine.py`, `app/backend/agents/**`, `app/backend/llm/**` (sink/ledger are new modules implementing existing protocols), `prompts/**`.
