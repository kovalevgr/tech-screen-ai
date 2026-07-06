# Tasks: Interviewer agent wrapper (T18)

**Input**: Design documents from `specs/028-t18-interviewer-agent/`
**Prerequisites**: plan.md, spec.md

**Tests**: fully unit-tested locally — `call_model` mocked at the interviewer module boundary, real committed prompt files, no DB/network. No operator/live phase.

**Organization**: single agent (`backend-engineer`) on this branch; the branch itself is `parallel: true` with T19 per plan.md. Story labels map to spec.md: US1 = typed utterance for the chosen move, US2 = bounded retry policy.

## Phase 0: Contract (T17 gap closure, §14 precondition) — commit 1

- [X] T001 [US1] Create `prompts/interviewer/v0001/schema.json` codifying the system.md §4 output contract verbatim (`utterance` 1..1200 chars, `internal_move_executed` 5-move enum, `additionalProperties: false`); prompt text untouched
- [X] T002 [US1] Append dated addendum (2026-07-06) to `prompts/interviewer/v0001/notes.md`: schema.json added as machine-readable §4 contract (T17 deliverable gap), no behavioural change, no new prompt version
- [X] T003 Commit 1: `docs(T17-gap): codify Interviewer output contract as schema.json`

## Phase 1: Wrapper module — agent: backend-engineer

- [X] T004 Create `app/backend/agents/__init__.py` — docstring-only package init, re-exports nothing (byte-identical file on the T19 sibling branch)
- [X] T005 [US1] Create `app/backend/agents/interviewer.py`: `PROMPT_VERSION = "v0001"`; frozen `RecentTurn` / `InterviewerTurnInputs` (system.md §3 mirror, `recent_turns` ≤ 8, 5-move `Literal`, permissive dicts for plan/competency/context per spec Clarifications); frozen `InterviewerOutput` mirroring schema.json (`extra="forbid"`, enum + 1..1200 caps); `InterviewerOutputInvalid`
- [X] T006 [US1] Runtime prompt assembly: system.md + level-guide.md + shared/ukrainian-anchors.md from `Path(__file__).resolve().parents[3] / "prompts"`, module-level `lru_cache`; schema loaded from the committed schema.json; `active.txt` never read
- [X] T007 [US1] `run_interviewer_turn(inputs, *, sink, ledger, settings)`: serialize inputs (minus `session_id`) as deterministic JSON `user_payload`; `call_model` with `agent="interviewer"`, the loaded schema, §12 default caps; validate `result.parsed` into `InterviewerOutput`
- [X] T008 [US2] Retry policy: one fresh `call_model` retry on `VertexSchemaError` / parsed-output `ValidationError`; second failure → `InterviewerOutputInvalid` chaining the cause; every other wrapper error propagates untouched; no provider-SDK imports, no DB, no logging

## Phase 2: Tests + gates — agent: backend-engineer

- [X] T009 Create `app/backend/tests/agents/__init__.py` (empty, 0 bytes — tests/services convention; byte-identical on the T19 sibling branch)
- [X] T010 [US1] `test_interviewer.py` assembly + request tests: real prompt files contain all three parts in order; loaded schema equals committed schema.json; `PROMPT_VERSION` matches `configs/models.yaml`; request carries agent/session/schema/default caps; payload excludes `session_id`
- [X] T011 [US1+US2] Acceptance matrix: happy path (1 invocation); schema miss → retry → success (2); schema miss ×2 → `InterviewerOutputInvalid` with `VertexSchemaError` cause (exactly 2); parsed-output violations (enum, >1200 chars, empty, extra property, `parsed=None`) → same retry-then-raise path; invalid-then-valid recovers; `VertexTimeoutError` / `SessionBudgetExceeded` propagate after exactly 1 invocation; input-model rejections (9 turns, unknown move)
- [X] T012 Quality gates from worktree root: `pytest app/backend/tests` (175 passed, 78 skipped — DB suite skips without `DATABASE_URL`, unchanged from main), `ruff check app/backend` clean, `ruff format --check app/backend` clean, `mypy --strict app/backend` clean
- [X] T013 Spec Kit artefacts (this directory) committed with the feature branch
