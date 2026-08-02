# State Machine Contract — Interview Orchestrator (T20)

**Status:** v1 — committed contract (constitution §14). Consumers: `app/backend/orchestrator/state_machine.py` (T20), session/WS endpoints (T22/T29), e2e mock session (T23). Upstream producers that MUST satisfy the plan shape in §7: Planner (T24/T25).

**Prime directive (constitution §2, ADR-005):** LLMs produce content; this machine produces every routing decision. Transitions are pure functions of `(state, event, config)`. No branch anywhere may depend on free-text LLM output — only on typed, schema-validated fields (`level`, `confidence`, `internal_move_executed`, `needs_manual_review`, red-flag counts).

---

## 1. Architecture: functional core, imperative shell

- **Core** (`state_machine.py`): pure. `transition(state: SessionState, event: Event, config: OrchestratorConfig) -> TransitionResult(new_state, commands)`. No I/O, no clock reads, no randomness — timestamps arrive ON events.
- **Shell** (T22/T23 wiring + `orchestrator/persistence.py`): executes `commands` (call Interviewer wrapper, schedule Assessor, persist state, end session), feeds results back as new events.
- Every transition is auditable: `(state_before_hash, event, state_after_hash, commands)` — T21 records these alongside turn_trace.

## 2. Phases and terminal states

```
INTRO → TECH → QA → CLOSE → COMPLETED
  any state → ABORTED(reason ∈ {candidate_timeout, cost_ceiling, operator_abort, fatal_agent_error})
```

- **INTRO**: fixed scripted opening (from `prompts/shared/candidate-facing/opening.md` — NOT LLM-generated), collect readiness confirmation. One candidate turn max; then → TECH.
- **TECH**: the working phase; sub-state machine over the plan's competency sequence (§4).
- **QA**: candidate's own questions; `qa_minutes` budget from plan; Interviewer move `acknowledge_and_transition` variants only; no assessment scheduled in QA.
- **CLOSE**: fixed scripted closing; emit `EndSession(completed)`; → COMPLETED.

## 3. Events (input alphabet)

| Event | Payload | Emitted by |
|---|---|---|
| `SessionStarted` | `now` | shell, on session create/start |
| `CandidateTurnReceived` | `turn_id, text, now` | shell (WS/dev-UI) |
| `InterviewerReplyReady` | `turn_id, InterviewerOutput, now` | shell, after T18 wrapper returns |
| `InterviewerFailed` | `turn_id, error_kind, now` | shell, on typed wrapper error |
| `AssessmentCompleted` | `for_turn_id, AssessorOutput, now` | shell, after T19 wrapper returns (async) |
| `AssessmentFailed` | `for_turn_id, error_kind, now` | shell, on typed wrapper error |
| `TimerTick` | `now` | shell, coarse cadence (≥15 s) |
| `Reconnected` | `now` | shell, after resume/rehydrate |
| `OperatorAbort` | `reason, now` | shell (admin action) |

`text` from `CandidateTurnReceived` is NEVER inspected by the core (no keyword branching — §2); it is passed through to wrappers only.

## 4. TECH sub-state

```
SessionState = {                       # top level — turn-taking applies to ALL phases
  phase, awaiting: "interviewer" | "candidate" | null,
  last_issued_move: InterviewerMove | null,
  state_schema_version: int,
  tech: {
    competency_index: int,             # position in plan.competencies
    seed_index: int,                   # within current competency
    probes_used: int,                  # within current competency
    drift_count: int,                  # §6.4
    competency_started_at: ts,
    coverage: {node_id: CoverageCell}, # §5 adjudication results
    pending_assessments: [turn_id],    # scheduled, not yet completed
  }
}
```

`CoverageCell` tracks **both** aggregations §5 needs: `best_level`/`best_confidence` (max level; ties → latest) for the ANSWERED test, and `latest_level`/`latest_confidence` (most recently completed) for the level-0 NONE trigger; plus distinct markers `gap_not_assessable` / `assessment_failed` / `gap_budget_exhausted`.

Per-competency loop: seed k (`ask_seed` for the very first, otherwise folded into the advance move per §10) → adjudicate (§5) → `depth_probe` / next seed / advance → next competency or → QA. On ANSWERED for seed k: if `seed_questions_uk[k+1]` exists AND competency time remains → next seed; else advance to the next competency.

## 5. Turn adjudication — the owner's 2/1/0 table (decision recorded 2026-08-02/03)

Adjudication is computed **only** from completed `AssessorOutput`s for the CURRENT competency focus, plan `target_level`, and config thresholds. Verdicts:

| Verdict | Deterministic condition (evaluated in this order) | Machine reaction |
|---|---|---|
| **ANSWERED (2)** | max `level` over focus-node assessments ≥ `target_level` AND its `confidence` ≥ `confidence_min` | `acknowledge_and_transition` → next seed/competency |
| **CLARIFY (1)** | not ANSWERED, AND (`probes_used` < `max_probes_per_competency`) AND competency time remaining > `min_probe_seconds` | `depth_probe` (branch from plan; probe counter +1) |
| **NONE (0)** | not ANSWERED and probe budget/time exhausted, OR latest assessment `level == 0`, OR assessments empty ("not assessable") after ≥1 probe | record gap in coverage → `close_competency` → advance |

- Thresholds live in `configs/orchestrator.yaml` (§8) — **never** in prompts, never decided by an LLM.
- `level == 0` (None, evidence-backed) and `assessments == []` (not assessable) both adjudicate toward NONE but are stored distinctly in coverage (reviewer-visible difference; assessor contract v0003).
- `needs_manual_review == true` or any red flag: recorded in coverage + session flags; does NOT change the move sequence (measurement, not routing) except `LIKELY_CHEATING` count ≥ `cheat_flags_to_review` → set `flagged_for_review` (session continues; candidate is never confronted).

## 6. Deterministic policies for the awkward cases

1. **Async assessor (ADR-007 voice-readiness):** the machine NEVER blocks the next interviewer move on a pending assessment. If adjudication is needed and no assessment for the current focus has completed yet, policy `proceed_planned`: issue the next planned seed/probe; a late `AssessmentCompleted` updates coverage and influences only FUTURE decisions. An issued move is never retracted.
2. **Interviewer failure** (`InterviewerOutputInvalid`, timeout, upstream): retry budget is the WRAPPER's (already spent). The machine emits `FlagTurnDegraded` + repeats the move once with the same context; second consecutive failure → `ABORTED(fatal_agent_error)` + `session_decision(reason=agent_failure)` row command.
3. **Assessment failure**: coverage cell marked `assessment_failed`; adjudication treats it as "no assessment available" (policy 1). Never aborts the session — the interview is candidate-facing; scoring gaps become reviewer work.
4. **Drift detection (T18 contract):** if `InterviewerOutput.internal_move_executed != last_issued_move`, increment `drift_count`, keep the machine's own accounting (the ISSUED move is authoritative for state); `drift_count ≥ drift_to_review` → `flagged_for_review`.
5. **Timers**: all budgets evaluated on event arrival using event `now` (no internal clock). Competency over budget → force NONE path at next adjudication point. Session over `session_max_minutes` → jump to QA (if not yet) with `qa_minutes_min`, then CLOSE.
6. **Candidate silence**: `TimerTick` with `now - last_candidate_activity > candidate_timeout_minutes` → `ABORTED(candidate_timeout)` (Tier-5 reliability layer may soften this; the hook exists now).
7. **Event priority on one tick**: if a single `TimerTick` satisfies several conditions, candidate-timeout (§6.6) wins over session/competency/QA budgets — silence is the stronger signal.
8. **Late assessments**: `AssessmentCompleted`/`AssessmentFailed` are accepted in ANY non-terminal phase while their `for_turn_id` is still in `pending_assessments` — coverage updates even after the machine has moved past the competency or into QA. Terminal states remain sinks (edge 20).
9. **Determinism of identifiers**: command `turn_id`s are derived `uuid5(session_id, structural-counter path)` — never `uuid4()` — so re-issuing after resume (edge 21) is idempotent by construction.

## 7. Plan shape consumed (input contract — Planner T24/T25 must satisfy)

```jsonc
{
  "plan_version": 1,
  "competencies": [
    {
      "node_id": "py.async",            // rubric node id, must exist in session rubric_snapshot
      "label_uk": "Асинхронний Python",
      "target_level": 3,                 // 1..5 (0 is not a target)
      "minutes": 12,
      "seed_questions_uk": ["..."],      // ≥1
      "probe_branches_uk": ["..."]       // may be empty; probes fall back to generic depth_probe context
    }
  ],
  "qa_minutes": 5,
  "session_max_minutes": 60
}
```

Until T24 ships, this shape is produced by fixtures (T23) and hand-written dev plans. The orchestrator validates it at session start (`PlanInvalid` → session cannot start; config error, not a candidate-facing failure).

## 8. Configuration (`configs/orchestrator.yaml`, §16 configs-as-code)

```yaml
adjudication:
  confidence_min: 0.6        # ANSWERED requires at least this
  max_probes_per_competency: 2
  min_probe_seconds: 60
flags:
  cheat_flags_to_review: 1
  drift_to_review: 3
timing:
  candidate_timeout_minutes: 10
  tick_seconds: 15
state_schema_version: 1
```

Loader mirrors `models_config.py` (frozen pydantic, load-time validation, typed errors). Changing thresholds = config PR, no prompt/code change.

## 9. Persistence & resumability

- Forward-only migration: `interview_session.session_state JSONB NULL` (+ index nothing; single-row access by PK). `interview_session` is NOT in the §3 append-only set — in-place update of this working-state column is correct and intended; the audit trail lives in turn_trace/T21, not here.
- After EVERY transition the shell persists `new_state.model_dump_json()` (carries `state_schema_version`). Write-after-transition, before issuing wrapper calls, so a crash resumes at the last consistent point.
- Resume: rehydrate `SessionState` from JSONB → feed `Reconnected` → machine re-emits the pending command idempotently (commands carry deterministic `turn_id`s so the shell can dedupe).

## 10. Transition table (normative — every edge gets ≥1 test fixture)

| # | State (phase, awaiting) | Event | Guard | New state | Commands |
|---|---|---|---|---|---|
| 1 | created | SessionStarted | plan valid | INTRO/awaiting interviewer | EmitScriptedOpening, PersistState |
| 2 | created | SessionStarted | plan invalid | ABORTED(operator_abort) | RecordDecision(plan_invalid) |
| 3 | INTRO | CandidateTurnReceived | — | TECH/awaiting interviewer | RunInterviewer(ask_seed, c0), ScheduleNothing, PersistState |
| 4 | TECH/awaiting interviewer | InterviewerReplyReady | — | TECH/awaiting candidate | DeliverUtterance, PersistState |
| 5 | TECH/awaiting interviewer | InterviewerFailed | first failure | TECH/awaiting interviewer | RunInterviewer(same move, retry_flag), FlagTurnDegraded, PersistState |
| 6 | TECH/awaiting interviewer | InterviewerFailed | second consecutive | ABORTED(fatal_agent_error) | RecordDecision(agent_failure), PersistState |
| 7 | TECH/awaiting candidate | CandidateTurnReceived | — | TECH/awaiting interviewer | RunAssessor(turn) [except in INTRO/QA], RunInterviewer(next move per §5 adjudication), PersistState |
| 8 | TECH/any | AssessmentCompleted | — | same (coverage updated) | PersistState |
| 9 | TECH/any | AssessmentFailed | — | same (coverage cell failed) | PersistState |
| 10 | TECH at adjudication | — | ANSWERED & next seed or competency remains | next seed / next competency | ONE RunInterviewer(move=`acknowledge_and_transition`, move_context carries the next seed question) |
| 11 | TECH at adjudication | — | CLARIFY | same competency, probes+1 | RunInterviewer(depth_probe, branch ctx) |
| 12 | TECH at adjudication | — | NONE & competencies remain | next competency | ONE RunInterviewer(move=`close_competency`, move_context carries the NEXT competency's first seed), RecordGap |
| 13 | TECH | — | last competency exits (any verdict) | QA | RunInterviewer(acknowledge_and_transition, qa ctx) |
| 14 | TECH/any | TimerTick | session_max exceeded | QA (or CLOSE if already QA) | as #13 |
| 15 | QA | CandidateTurnReceived | qa time remains | QA | RunInterviewer(acknowledge_and_transition, qa ctx) — no RunAssessor |
| 16 | QA | TimerTick / turn | qa budget exhausted | CLOSE | EmitScriptedClosing, PersistState |
| 17 | CLOSE | InterviewerReplyReady / immediate | — | COMPLETED | EndSession(completed), RecordDecision(completed) |
| 18 | any non-terminal | TimerTick | candidate timeout | ABORTED(candidate_timeout) | RecordDecision(timeout), PersistState |
| 19 | any non-terminal | OperatorAbort | — | ABORTED(operator_abort) | RecordDecision(operator), PersistState |
| 20 | terminal | any event | — | unchanged | none (idempotent sink) |
| 21 | any non-terminal | Reconnected | — | unchanged | ReissuePendingCommand (idempotent), PersistState |

Adjudication (§5) is evaluated inside edge #7's move selection — it is not a separate event; fixtures must cover ANSWERED/CLARIFY/NONE × {assessment present, pending (policy `proceed_planned`), failed}. Move vocabulary is the Interviewer contract's: advances are ONE call (`acknowledge_and_transition` or `close_competency` with the next seed in `move_context`) — never two round-trips; a bare `ask_seed` occurs only for the very first seed after INTRO. "ScheduleNothing" in edge 3 means the command is simply absent from the tuple — there is no no-op Command variant.

## Amendments

- **v1.1 (2026-08-03):** folded accepted refinements from the discarded first implementation round: top-level `awaiting`/`last_issued_move`; CoverageCell best/latest split; multi-seed iteration rule; one-call advance moves with contract vocabulary; tick priority (§6.7); late-assessment acceptance (§6.8); uuid5 command ids (§6.9). Adjudicated by the contract owner; the discarded round's remaining deviations were rejected or made moot.

## 11. Explicitly out of scope for T20

- Cost ceiling enforcement (T21) — the machine only exposes `ABORTED(cost_ceiling)` + `flagged_for_review` hooks.
- Durable turn_trace / transition audit rows (T21).
- WS/HTTP surface, scripted opening/closing delivery mechanics (T22/T29); dark-launch feature flag for live exposure ships WITH that surface (§9 satisfied at exposure point — the orchestrator alone has no user-facing path).
- Anti-cheat heuristics beyond consuming assessor red flags (T33).

---
*Amendments: none yet. Changes to this contract require updating the transition-table tests in the same PR.*
