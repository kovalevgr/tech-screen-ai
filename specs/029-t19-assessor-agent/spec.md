# Feature Specification: Assessor agent wrapper (T19)

**Feature Branch**: `029-t19-assessor-agent`
**Created**: 2026-07-06
**Status**: Draft
**Input**: User description: T19 — Assessor agent wrapper per `docs/engineering/implementation-plan.md` Tier 3. `app/backend/agents/assessor.py`: typed input mirroring `prompts/assessor/v0001/system.md` §3 INPUTS, typed output mirroring `prompts/assessor/v0001/schema.json`, one async entry point over `call_model` with the per-agent schema-retry policy (retry once, then typed failure). Runs in parallel with T18 (Interviewer wrapper) on a sibling branch.

## Clarifications

### Session 2026-07-06

- Q: `implementation-plan.md` T17 describes the Assessor output as `{concepts_covered, concepts_missing, red_flags, level_estimate, confidence}` — but the committed contract disagrees. → A: The committed `prompts/assessor/v0001/schema.json` (turn_id, session_id, competency_focus, assessments[], red_flags[], needs_manual_review, manual_review_reason_en) **wins**; the plan one-liner is stale. Per the T17 ownership note, per-agent schema files are the single source of truth and backend wrappers bind to them directly.
- Q: Which prompt files are part of the runtime system prompt? → A: `system.md` plus `level-guide.md` (system.md §5 defers level semantics to it). `schema.json` travels as the wrapper's `json_schema` argument, not as prompt text. `notes.md` is design history — never sent to the model.
- Q: Where do the rubric-node / turn input types come from? → A: They do not exist in code yet. The input model keeps those payloads permissive (`dict[str, Any]`) with explicit comments; T20 / Tier-4 refines them. `session_id` and `turn_id` are typed `UUID` now.
- Q: Retry semantics on a contract miss? → A: One fresh `call_model` retry on `VertexSchemaError` **or** on a payload that passes the wrapper's structural pass but violates the tighter `AssessorOutput` bounds (level enum, confidence ≤ 0.99, non-empty evidence spans). Second miss → typed `AssessorOutputInvalid` chaining the cause. Every other wrapper error propagates untouched — matching T04 Clarifications 2026-04-26 and `docs/engineering/vertex-integration.md` ("Assessor: retry up to once").

### Session 2026-07-07 (reviewer gate — PASS-WITH-FINDINGS)

- Q: Are the echoed `turn_id` / `session_id` in the model output trusted after UUID-shape validation? → A: **No — equality-enforced by the wrapper.** After the Pydantic pass, `_score_once` compares the echoed ids to the request's ids; a mismatch (a hallucinated-but-well-formed UUID) is a contract miss (`AssessorEchoMismatch`) on the same retry-once path, so it can never flow downstream into the append-only audit trail (§3). This is integrity enforcement, not a routing decision (§2). Relatedly, `to_user_payload()` spreads caller `turn_metadata` FIRST so the typed ids always win in the wire payload — trace/ledger attribution and the payload can never disagree.
- Q: Who enforces the cross-field rule "confidence < 0.4 sets `needs_manual_review`" (schema.json prose + system.md §4)? → A: **Nobody at this layer — deliberately.** `schema.json` cannot express the cross-field constraint and the wrapper does not add it; the output reaches T20 unenforced and the orchestrator must decide how to treat a low-confidence assessment without the flag. Recorded here so T20 picks it up as an explicit input.
- Q: `docs/engineering/vertex-integration.md` (~line 127) says the Assessor retries "with temperature bumped" and on repeated failure "marks the assessment as needs_manual_review and enqueues" — neither is possible at wrapper level (no temperature override on `ModelCallRequest`; synthesising an assessment would be flow control, §2). → A: The doc line is being amended in the sibling T18 PR, which already owns edits to that file; this branch stays purely additive and does not touch `docs/engineering/**`.

## User Scenarios & Testing *(mandatory)*

The "users" are the orchestrator (T20) that needs a typed, non-blocking scoring call per candidate turn, and the reviewers whose audit trail depends on the Assessor's output conforming to the committed contract.

### User Story 1 — Orchestrator scores a turn and gets a typed result (Priority: P1)

The orchestrator hands the wrapper the rubric subset, the turn, prior context, and the focus competency. It gets back a validated `AssessorOutput` — per-node levels 1–4 with confidence ≤ 0.99, evidence spans, red flags from the five-value enum, and the manual-review signal — or a typed exception it can route on deterministically (§2: routing uses typed fields, never LLM free text).

**Acceptance Scenarios**:

1. **Given** a mocked `call_model` returning a schema-conformant payload, **When** `run_assessor_turn` is awaited, **Then** it returns an `AssessorOutput` echoing `turn_id` / `session_id` after exactly one model call.
2. **Given** the request captured at the mock boundary, **Then** `agent="assessor"`, the `json_schema` equals the committed `schema.json`, the system prompt is system.md + level-guide.md, the caps are the wrapper defaults (30 s / 4096 tokens), and the `user_payload` carries exactly the five §3 INPUTS keys with ids re-nested under `turn_metadata`.

### User Story 2 — Contract misses are retried once, then surfaced typed (Priority: P1)

A malformed model output (wrapper `VertexSchemaError`, bounds violations like `confidence: 1.0`, `level: 5`, empty `evidence_spans`, or echoed `turn_id`/`session_id` not equal to the request's — Clarifications 2026-07-07) triggers exactly one fresh retry; a second miss raises `AssessorOutputInvalid` with the cause chained. Non-schema wrapper errors (timeout, upstream, budget, trace-write) propagate untouched with no retry.

**Acceptance Scenarios**:

1. Schema miss → retry → success: result returned, exactly 2 `call_model` invocations.
2. Schema miss → retry → second miss: `AssessorOutputInvalid`, exactly 2 invocations, `__cause__` is the second miss.
3. Bounds-violating payloads (confidence 1.0 / level 5 / empty spans) follow the same retry-then-raise path with a `ValidationError` cause.
4. Echoed-id mismatch (hallucinated-but-valid UUID) → one retry → success; mismatch ×2 → `AssessorOutputInvalid`, exactly 2 invocations, cause an `AssessorEchoMismatch` naming the field with expected vs got.
5. `VertexTimeoutError` (and peers) propagate after exactly 1 invocation.

### User Story 3 — Scoring never blocks the interview (Priority: P1, T19 acceptance)

Per ADR-007 (voice-readiness) the Assessor call is a plain awaitable coroutine with no blocking I/O: the Interviewer can produce turn N+1 while the Assessor is still scoring turn N.

**Acceptance Scenarios**:

1. **Given** a slow (event-gated) fake `call_model`, **When** `run_assessor_turn` runs as an `asyncio.Task`, **Then** a stand-in "Interviewer produces turn N+1" coroutine completes while the scoring task is still pending, and the scoring task subsequently resolves to a valid `AssessorOutput`. Deterministic — asyncio events, no real sleeps beyond safety timeouts.

### Edge Cases

- **Prompt files** are read once and cached at module level (immutable per version); no per-call file I/O on the event loop.
- **Schema dict** is returned fresh per call so caller mutation cannot poison the cache.
- **`AssessorOutputInvalid` message is PII-free** (§15): candidate text lives only on the chained cause / `raw_payload`, never in the message.
- **The Assessor never routes** (§2): the module contains no control-flow on model output beyond validation; the orchestrator consumes the typed result.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `app/backend/agents/assessor.py` MUST expose one public async entry point `run_assessor_turn(inputs, *, sink, ledger, settings) -> AssessorOutput` calling `call_model` with `agent="assessor"`, the committed `schema.json` as `json_schema`, and default §12 caps (never raised).
- **FR-002**: A frozen Pydantic input model MUST mirror `system.md` §3 INPUTS (`rubric_snapshot_subset`, `turn`, `prior_turns`, `competency_focus`, `turn_metadata`) with typed `session_id: UUID` / `turn_id: UUID`; structures that do not exist in code yet stay permissive `dict[str, Any]` with a refining-owner comment (T20 / Tier-4).
- **FR-003**: Typed output models MUST mirror `prompts/assessor/v0001/schema.json` exactly: level ∈ {1,2,3,4}, confidence ∈ [0, 0.99], `rationale_en` ≤ 600 chars, `evidence_spans` non-empty, five-value red-flag enum, `needs_manual_review`, `manual_review_reason_en` ≤ 400 chars, `additionalProperties: false` → `extra="forbid"`.
- **FR-004**: System prompt assembly MUST load `system.md` + `level-guide.md` from the `prompts/` tree (`Path(__file__).resolve().parents[3] / "prompts"` — valid in-repo and in the Docker image), pinned via module constant `PROMPT_VERSION = "v0001"`, cached at module level.
- **FR-005**: Retry policy: exactly one fresh retry on a contract miss — `VertexSchemaError`, output-model `ValidationError`, or `AssessorEchoMismatch` (echoed `turn_id`/`session_id` ≠ request ids); second miss raises module-level `AssessorOutputInvalid` chaining the cause; all other wrapper errors propagate untouched.
- **FR-008**: `to_user_payload()` MUST give the typed `turn_id`/`session_id` precedence over any caller-supplied `turn_metadata` keys of the same name (caller metadata spread first), so the wire payload can never diverge from trace/ledger attribution.
- **FR-006**: The module MUST be pure (no DB, no side effects beyond `call_model`'s injected sink/ledger), import no provider SDK (only `app.backend.llm`), and import nothing from `app.backend.agents.interviewer` (sibling branch).
- **FR-007**: `app/backend/agents/__init__.py` re-exports nothing (byte-agreed with the T18 branch so parallel tasks never touch the same line).

### Key Entities

- **`AssessorTurnInput`** — frozen input model + `to_user_payload()` producing the §3-shaped JSON.
- **`AssessorOutput` / `AssessmentItem` / `RedFlagItem`** — the typed contract mirror.
- **`AssessorOutputInvalid`** — the typed retry-exhausted failure.
- **`AssessorEchoMismatch`** — the typed echoed-id contract miss (Clarifications 2026-07-07).
- **`run_assessor_turn`** — the single public coroutine.

## Success Criteria *(mandatory)*

- **SC-001**: `uv run pytest app/backend/tests` green including `tests/agents/test_assessor.py` (happy path, request shape, retry matrix, error propagation, concurrency acceptance) against the real prompt files.
- **SC-002**: `ruff check`, `ruff format --check`, `mypy --strict` clean on `app/backend`.
- **SC-003**: `scripts/check-no-provider-sdk-imports.sh` exits 0 (no provider SDK outside the wrapper allowlist).
- **SC-004**: Purely additive: no existing file modified (settings, `app/backend/llm/**`, `prompts/**`, Docker, CI untouched).
