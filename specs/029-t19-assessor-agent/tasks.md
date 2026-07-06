# Tasks: Assessor agent wrapper (T19)

**Input**: Design documents from `specs/029-t19-assessor-agent/`
**Prerequisites**: plan.md, spec.md; contract `prompts/assessor/v0001/schema.json` (T17, committed)

**Organization**: single branch, `agent: backend-engineer` throughout. Story labels map to spec.md: US1 = typed scoring call, US2 = retry policy, US3 = non-blocking acceptance.

## Phase 1: Package scaffolding

- [X] T001 Create `app/backend/agents/__init__.py` with the byte-agreed empty-surface docstring (re-exports nothing; identical file lands on the T18 sibling branch)
- [X] T002 Create `app/backend/tests/agents/__init__.py` as an empty file (0 bytes, tests/services convention; byte-identical on the sibling branch)

## Phase 2: Wrapper implementation (US1+US2)

- [X] T003 [US1] `app/backend/agents/assessor.py`: `PROMPT_VERSION = "v0001"`, prompts root resolved as `Path(__file__).resolve().parents[3] / "prompts"`, module-cached assembly of `system.md` + `level-guide.md` (`lru_cache`), `schema.json` loaded once and served as a fresh dict per call
- [X] T004 [US1] Frozen `AssessorTurnInput` mirroring system.md §3 INPUTS — typed `session_id`/`turn_id: UUID`, permissive `dict[str, Any]` for rubric-node/turn payloads (T20/Tier-4 refines), `to_user_payload()` re-nesting ids under `turn_metadata` so the JSON matches the prompt contract key-for-key
- [X] T005 [US1] Output models mirroring `schema.json` exactly: `AssessmentItem` (level `Literal[1,2,3,4]`, confidence ≤ 0.99, rationale ≤ 600, non-empty evidence spans), `RedFlagItem` (5-value enum, nullable node id/span), `AssessorOutput` (`extra="forbid"` everywhere)
- [X] T006 [US1+US2] `run_assessor_turn(inputs, *, sink, ledger, settings)`: `call_model` with `agent="assessor"`, committed schema as `json_schema`, default §12 caps; one fresh retry on `VertexSchemaError`/`ValidationError`; second miss → `AssessorOutputInvalid` chaining the cause (PII-free message); other wrapper errors propagate untouched

## Phase 3: Tests (US1+US2+US3)

- [X] T007 [US1] `app/backend/tests/agents/test_assessor.py`: prompt-assembly tests against the REAL `prompts/assessor/v0001` files (system before guide, notes.md excluded, cache identity, schema == committed file)
- [X] T008 [US1] Happy path + request-shape tests (`agent`, `json_schema`, default caps, §3-shaped `user_payload` with re-nested ids) — `call_model` monkeypatched at the assessor module boundary
- [X] T009 [US2] Retry matrix: schema miss → retry → success (2 calls); schema miss ×2 → `AssessorOutputInvalid` (2 calls, cause chained); bounds violations (confidence 1.0 / level 5 / empty `evidence_spans`) → retry-then-raise with `ValidationError` cause; violation-then-valid retry succeeds
- [X] T010 [US2] Non-schema wrapper errors (`VertexTimeoutError`, `VertexUpstreamUnavailableError`, `SessionBudgetExceeded`, `TraceWriteError`) propagate untouched after exactly 1 call
- [X] T011 [US3] T19 acceptance: event-gated slow `call_model` fake; `run_assessor_turn` as `asyncio.Task`; stand-in "Interviewer produces turn N+1" coroutine (T18 NOT imported) completes while scoring is pending; task then resolves to a valid `AssessorOutput`; deterministic, no real sleeps beyond `wait_for` safety timeouts

## Phase 4: Quality gates

- [X] T012 `uv run pytest app/backend/tests` green (173 passed / 78 pre-existing skips); `ruff check` + `ruff format --check` clean; `mypy --strict app/backend` clean; `scripts/check-no-provider-sdk-imports.sh` exits 0
- [X] T013 Spec Kit artefacts (this directory) committed with the feature branch
