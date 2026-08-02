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

## Phase 7 — reviewer-gate fix round (PASS-WITH-FINDINGS, contract v1.2)

- [x] T017 (finding 1) Stale-reply no-op guard per §6.9a in `_on_interviewer_reply` / `_on_interviewer_failed`; `test_stale_replies.py` covers the preempted-probe race, the failure ladder, the edge-15 QA path and CLOSE
- [x] T018 (finding 5) Purity guards: attribute-form randomness scan, `import uuid` ban, `ast.Match` subjects + case guards, `description_en` / `manual_review_reason_en` added to the prose set
- [x] T019 (nit 6) `plan.py` Clarification citation 9 → 11
- [x] T020 (nit 8) Re-measure the DB suite and record the actual counts + why the reviewer's 464 and the original 440 differ (scope, not outcome)
- [x] T021 Gates green without and with `DATABASE_URL`; push the branch
