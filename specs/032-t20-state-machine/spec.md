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

### Implementation notes (recorded during build, not design changes)

Added by `backend-engineer` while executing plan.md phases 3–5. Each is the simplest reading consistent with contract v1.1; none reopens a decided item.

8. **Command tuples are literal.** The §10 command column is implemented verbatim — including where the table omits `PersistState` (edges 2, 15, 17, 20 and edge 14's "as #13" tuple). §9's blanket "persist after EVERY transition" remains the shell's obligation (Clarification 4), so no durability is lost by following the table exactly. Edges 10–13 inherit `PersistState` from edge 7, inside which they are evaluated.
9. **Edge 14 in QA.** "QA (or CLOSE if already QA)" is implemented as: TECH + session_max → QA with edge 13's single `acknowledge_and_transition`; QA + session_max → CLOSE with edge 16's `EmitScriptedClosing, PersistState` (an `acknowledge_and_transition` into Q&A is meaningless when the destination is CLOSE).
10. **Plan location.** §1 fixes the signature `transition(state, event, config)` and §3 fixes `SessionStarted`'s payload as `now` only, so the raw plan is frozen onto `SessionState.plan_input` at session creation and validated into `SessionState.plan` by edge 1. Both are retained: the raw copy is what makes edge 2 (plan invalid) representable and lets the shell show exactly what was rejected.
11. **Plan minimum + forward compatibility.** `PlanSnapshot` requires ≥ 1 competency (§7 states no minimum; a plan with nothing to assess is a configuration error). Unknown extra keys are tolerated so a richer future Planner payload cannot break a running session.
12. **`ReissuePendingCommand` carries the command.** Edge 21 names it as a command and §9 says the machine "re-emits the pending command", so it is a real `Command` variant wrapping the outstanding `RunInterviewer` / `DeliverUtterance` / `EmitScriptedOpening` / `EmitScriptedClosing`. With nothing outstanding the tuple is just `PersistState`.
13. **`assessment_focus` map.** §4 lists `pending_assessments` as bare turn ids, but `AssessmentFailed` carries no assessor output — so `TechState.assessment_focus` (`turn_id → node_id`) records which coverage cell a late failure belongs to (§6.3 + §6.8). Entries are dropped together with the pending id; §4's field keeps its stated shape.
14. **`level_zero` gap marker.** §4 names three `CoverageCell` markers; NONE reached via §5's level-0 short-circuit gets a fourth `RecordGap` marker value so a reviewer sees *why* the competency closed. The cell itself stays distinct exactly as §5 requires (level 0 recorded vs `gap_not_assessable`).
15. **Boundary operators.** §6.6's candidate timeout is strict (`>` — the operator the contract writes). Session / Q&A / competency budgets count as exhausted on *reaching* the limit (`>=`). §5's `confidence >= confidence_min` and `level >= target_level` are inclusive as written; CLARIFY's time guard is `remaining > min_probe_seconds`, also as written.
16. **Abort reason on edge 19.** `OperatorAbort.reason` is typed as the full §2 abort set and copied onto the state, so §11's `ABORTED(cost_ceiling)` hook is reachable (T21 raises the event). `RecordDecision(operator)` is unchanged; the default reason is `operator_abort`.
17. **Phase-agnostic §6 policies.** Edges 4/5/6 are tabulated for TECH, but §6.2 (failure ladder) and §6.4 (drift) are written phase-agnostically, so they also apply in QA — the only other phase that issues a `RunInterviewer`. INTRO and CLOSE are unaffected (CLOSE exits via edge 17).
18. **Untabulated `(phase, event)` pairs are no-ops** — same state, no commands. The machine never guesses at an edge the contract does not define.
19. **Scripted opening and closing both exist** (`prompts/shared/candidate-facing/opening.md`, `closing.md`). The core references them by path constant (`OPENING_SCRIPT_PATH`, `CLOSING_SCRIPT_PATH`) and never reads the files; delivery is T22/T29's. No candidate-facing prose was authored here.
20. **`confidence_min` is capped at 0.99** by the config loader — the assessor v0003 confidence ceiling. A higher threshold would make ANSWERED unreachable, which must fail at load, not mid-interview.
21. **Migration name** follows plan.md's `000?_add_session_state_column.py` → `alembic/versions/0006_add_session_state_column.py` (revision id `0006_add_session_state_column`).
22. **SC-3 was verified live.** Docker was available in the implementing agent's sandbox, so `upgrade → downgrade → upgrade` ran against a real `pgvector/pgvector:pg17` Postgres and the full suite passed with `DATABASE_URL` set, in addition to the offline `--sql` render in both directions. Counts, re-measured on the fix-round tree: `pytest app/backend/tests` (the gate command) → **448 passed**; a bare `pytest`, which also collects `infra/functions` from the `testpaths` default, → **472 passed** (24 infra tests). The reviewer's 464 and this note's original 440 are those same two scopes measured one commit earlier — the numbers differ by scope, not by outcome.

### Fix-round notes (reviewer gate, contract v1.2)

23. **Stale agent replies (§6.9a).** `_answers_pending_command` now gates both `_on_interviewer_reply` and `_on_interviewer_failed`: an event whose `turn_id` is not the outstanding command's id is a no-op — no delivery, no drift accounting (§6.4), no failure-ladder step (§6.2). Applied uniformly, CLOSE included: edge 17 answers the outstanding closing turn, while its "immediate" `TimerTick` path is unaffected. The race is real — edge 14 preempts an in-flight `depth_probe` — and is reproduced in `app/backend/tests/orchestrator/test_stale_replies.py`.
24. **Purity guards hardened.** The randomness scan now covers attribute form (`uuid.uuid4`, `random.*`, `secrets.*`) as well as bare names; `import uuid` is banned outright in the pure modules (`from uuid import UUID, uuid5` is the sanctioned form, so `uuid.uuid4` is never one attribute access away); the prose-branch guard inspects `match` subjects and `case` guards in addition to `if` / `while` / conditional expressions / comparisons, and its banned attribute set gained `description_en` and `manual_review_reason_en`. Each predicate was exercised against planted violations before landing, so none of them is vacuous.
25. **Shared test helpers.** `tech_with_coverage` and `drive_to_qa` moved from `test_transition_table.py` into `_builders.py` so the stale-reply suite reuses the same drive sequences instead of duplicating them. No edge assertion changed; the 21 edge tests pass unmodified.
26. **Contract v1.2 makes notes 8, 9 and 15 normative text** (adjudication evaluation order, edge 14's split command cell, inclusive budget guards) — the code already matched, so nothing changed for them; §9 now states outright that `PersistState` is an advisory marker. Nit fixed: `plan.py` cited "spec Clarification 9", corrected to 11.

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
