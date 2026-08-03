# Feature spec — T23 End-to-end Mock Session (Tier-3 gate)

**Status**: Implemented · **Branch**: `035-t23-e2e-mock-session`
**Authored & implemented by**: main-loop orchestrator — the implementation plan assigns T23 `agent: orchestrator`, and CLAUDE.md policy rev. 2 keeps gate-design in the brain. Fixture recording was mechanical (scripted generator, see Clarification 3).

## What / why

The Tier-3 exit gate: a scripted interview driven end-to-end through the REAL stack — dev-session shell → T20 state machine → T18/T19 agent wrappers → `call_model` → mock backend → T21 durable trace sink — with the full LLM-call sequence pinned as a fixture table. Green means the core interview loop is integration-proven, deterministic, and auditable; this is the test that guards every future Tier against silently breaking the interview flow.

## Functional requirements

- **FR-035-1** `app/backend/tests/e2e/test_mock_session.py`: an 8-scripted-turn interview (plus a QA sign-off turn, see Clarification 2) over 2 competencies, reaching COMPLETED.
- **FR-035-2** The exact ordered `(agent, issued_move)` sequence of all 15 LLM calls is pinned (`EXPECTED_CALLS`) and asserted against the durable trace rows — the "transitions match the fixture table" acceptance from the implementation plan.
- **FR-035-3** Path coverage beyond the 033 happy path: proceed_planned on empty coverage (×2), CLARIFY→second probe (×2), ANSWERED→multi-seed advance, ANSWERED→competency advance, level-0 short-circuit→NONE on the last competency, late assessment acceptance (§6.8), edge-16 QA exit on a turn.
- **FR-035-4** Audit completeness asserted on every row (outcome ok, turn_id, prompts, response_text, parsed, v0003 pin on assessor rows); coverage tells the designed story (py.async best 3; db.transactions best 2 / latest 0, not-assessable false); cost total equals the row sum; transcript bookends are the repo scripts.
- **FR-035-5** Determinism test: two consecutive full runs produce identical call tables and cost — the property behind the 5/5 stability acceptance. Verified 5× consecutively at authoring time; CI re-runs on every push.

## Clarifications (decided)

1. **The §6.1 lag is designed into the script**: the reply to turn N is decided from coverage as of turn N-1 (the Assessor never blocks — ADR-007). The expected table was derived from state-machine contract §5/§10 WITH this lag, then confirmed empirically; the one authoring correction was assessor rows carrying `issued_move=None` (scoring is not a move).
2. **"8-turn session"** (implementation plan) = 8 scripted interview turns; a 9th QA sign-off turn triggers edge 16 (qa_minutes=0 → budget already reached → scripted closing, no LLM call). Same shape as the 033 happy path.
3. **Fixture recording** was mechanical: run → mock writes request envelopes to `_unrecorded/` → a generator (scratchpad, not committed) built responses from the authored script table (levels/confidences/rationales/evidence spans) → re-run to green. 15 new SHA-keyed envelopes committed (8 interviewer, 7 assessor).
4. **No new backend code** — the test consumes 033's service/scheduler as-is; the only production-code diff is zero.

## Success criteria

- SC-1 5/5 consecutive green runs locally (done: 5×"2 passed"); CI stability follows on every subsequent push.
- SC-2 Full gates green both DB modes (538 with DB / 383+155 skips without; ruff ×2, mypy --strict, sdk-import guard).
- SC-3 Diff = test package + fixtures + spec kit only.
