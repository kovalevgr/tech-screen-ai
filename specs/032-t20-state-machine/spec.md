# Feature spec — T20 Interview Orchestrator State Machine

**Status**: Draft
**Branch**: `032-t20-state-machine`
**Contract**: [`docs/contracts/state-machine.md`](../../docs/contracts/state-machine.md) (v1.1 — normative; this spec does not restate it)
**Authored by**: main-loop orchestrator (CLAUDE.md §Sub-agent model policy rev. 2 — spec kit is a brain artifact)

## What / why

The deterministic Python core that runs an interview session: phases INTRO → TECH → QA → CLOSE, per-turn move selection for the Interviewer, async scheduling of the Assessor, the owner's 2/1/0 turn-adjudication table, session-state persistence and resumability. This is the piece the constitution's §2 exists for: every routing decision in TechScreen happens here, in reviewable Python, never in a prompt.

## Functional requirements

- **FR-032-1** Pure transition core: `transition(state, event, config)` with no I/O, no clock, no randomness; timestamps arrive on events (contract §1, §3).
- **FR-032-2** Full phase machine per contract §2 with terminal `COMPLETED` / `ABORTED(reason)`.
- **FR-032-3** Owner's adjudication table (contract §5): ANSWERED/CLARIFY/NONE computed only from typed AssessorOutput fields vs plan `target_level` and `configs/orchestrator.yaml` thresholds. `level==0` (evidence-backed None) and empty-assessments ("not assessable") both reach NONE but persist as distinct coverage markers.
- **FR-032-4** Async-assessor policy `proceed_planned` (contract §6.1): pending assessment never blocks the next interviewer move; late results update coverage in any non-terminal phase (§6.8).
- **FR-032-5** Failure policies per contract §6.2–6.3; drift accounting per §6.4; tick priority per §6.7.
- **FR-032-6** Plan input contract per §7 with `PlanInvalid` validation at session start; the shape is the producer contract for T24/T25.
- **FR-032-7** `configs/orchestrator.yaml` (§8) with a load-time-validated frozen loader mirroring `models_config.py`; thresholds changeable by config PR only.
- **FR-032-8** Persistence: `interview_session.session_state JSONB NULL` via forward-only migration; write-after-every-transition command; versioned state schema; resume via `Reconnected` with idempotent re-issue (uuid5 ids, §6.9).
- **FR-032-9** Every numbered transition edge (contract §10, 1–21) covered by ≥1 named test fixture; adjudication matrix covered as {ANSWERED, CLARIFY, NONE} × {assessment present, pending, failed}.
- **FR-032-10** Static purity guards as tests: no `datetime.now`/`time.time`/`random.` in the core module; no branching on candidate free text; no `.should_*`-style LLM-output flow control.

## Clarifications (decisions already made — do not reopen)

1. **Provenance**: a first implementation round was rolled back on the owner's process decision (2026-08-03, model-tiering rev. 2). Its accepted design refinements are contract v1.1 §Amendments; its rejected readings: two-round-trip competency advances (rejected — one call with contract move vocabulary), separate no-op ScheduleNothing command (rejected — omission).
2. **Advance-move vocabulary**: competency/seed advances use the Interviewer contract's own moves — `acknowledge_and_transition` (ANSWERED path) or `close_competency` (NONE path) — with the next seed carried in `move_context`. Bare `ask_seed` only for the very first seed after INTRO.
3. **TimerTick priority**: candidate-timeout beats budget transitions on the same tick (contract §6.7).
4. **Persistence ordering** (persist before wrapper calls) is the SHELL's obligation — recorded here as a requirement on T22, unenforceable from a pure core by design.
5. **No feature flag in T20**: the orchestrator has no user-facing surface; the §9 dark-launch flag ships with the exposure point (T22/T29). Recorded rationale, not an omission.
6. **§3 scope**: `interview_session.session_state` is mutable working state, not one of the six append-only audit tables; in-place update is correct. The transition audit trail is T21's (`turn_trace` + transition records).
7. **Rubric-snapshot cross-check** of plan `node_id`s is deferred to the session-start service (T22) — the machine validates shape, not referential integrity against the snapshot.

## Success criteria

- **SC-1** All 21 contract edges have passing named tests (`test_edge_NN_*`); adjudication matrix complete incl. boundary `confidence == confidence_min` (passes) and probe-budget exhaustion.
- **SC-2** Determinism: repeated `transition` calls with equal inputs yield equal outputs; `SessionState` JSON round-trips losslessly.
- **SC-3** Migration `upgrade → downgrade → upgrade` verified against real Postgres.
- **SC-4** Gates green: pytest, ruff check, ruff format --check, mypy --strict, no-provider-sdk-imports (and no new provider-SDK surface at all).
- **SC-5** Diff is additive except the one migration + `InterviewSession` column mapping; no changes under `app/backend/agents/**`, `app/backend/llm/**`, `prompts/**`.

## Handoff notes

- **T21**: consume `TransitionResult` for durable transition audit; wire cost-ceiling → `ABORTED(cost_ceiling)` hook; `RecordDecision` commands map to `session_decision` rows.
- **T22**: imperative shell (command executor), persist-before-call ordering, `enable_live_orchestrator` flag default false, rubric-snapshot cross-check at session start, scripted opening/closing delivery.
- **T24/T25**: plan producer must satisfy contract §7 exactly.
