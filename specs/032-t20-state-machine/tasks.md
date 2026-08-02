# Tasks — T20 Interview Orchestrator State Machine

> Check a box only when the item is actually done. Phases map to plan.md.

## Phase 2 — contract + spec kit (verbatim main-loop artifacts)

- [x] T001 Commit `docs/contracts/state-machine.md` (v1.1, verbatim)
- [x] T002 Commit `specs/032-t20-state-machine/{spec,plan,tasks}.md` (verbatim)

## Phase 3 — core

- [x] T003 `orchestrator/__init__.py` (docstring only) + `state_machine.py`: SessionState (top-level awaiting, tech sub-state, CoverageCell best/latest split), Event/Command unions, `transition()` per contract §10
- [x] T004 Adjudication per contract §5 with evaluation order fixed in code comments (ANSWERED → level-0 short-circuit → budget/not-assessable → CLARIFY)
- [x] T005 Policies §6.1–6.9 (proceed_planned, failure ladders, drift, tick priority, late assessments, uuid5 ids)
- [x] T006 `plan.py` — PlanSnapshot per §7 + `PlanInvalid`
- [x] T007 `config.py` + `configs/orchestrator.yaml` per §8 (loader mirrors models_config.py)

## Phase 4 — persistence

- [x] T008 Alembic migration: `interview_session.session_state JSONB NULL` (forward-only, reversible downgrade)
- [x] T009 `InterviewSession.session_state` mapping + `persistence.py` load/save with state_schema_version check
- [x] T010 DB-gated persistence tests (skip without DATABASE_URL)

## Phase 5 — tests

- [x] T011 Transition-table suite: named `test_edge_01…21` fixtures, every contract §10 edge
- [x] T012 Adjudication matrix: {ANSWERED, CLARIFY, NONE} × {present, pending→proceed_planned, failed}; boundary confidence == confidence_min; probe exhaustion; level-0 vs empty-array distinct coverage markers; multi-seed iteration
- [x] T013 Determinism + JSON round-trip tests
- [x] T014 Static purity guards (no clock/randomness/text-branching/`.should_*`)
- [x] T015 Full gate run green (pytest, ruff ×2, mypy --strict, sdk-import guard)

## Phase 6 — wrap-up

- [x] T016 Verify diff additivity per SC-5; report edge→test mapping; do NOT push until told
