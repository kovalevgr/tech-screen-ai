# Feature Specification: Interviewer agent wrapper (T18)

**Feature Branch**: `028-t18-interviewer-agent`
**Created**: 2026-07-06
**Status**: Implemented
**Input**: T18 — Interviewer agent wrapper per `docs/engineering/implementation-plan.md` Tier 3. `app/backend/agents/interviewer.py`: build the runtime system prompt from the pinned `prompts/interviewer/v0001/` version, call `call_model` with the committed output schema, validate, retry once on schema miss, surface a typed parsed object. Pure — no DB writes (turn tracing flows through the wrapper's injected sink; T21 lands the durable sink).

## Clarifications

### Session 2026-07-06

- Q: The plan names `prompts/interviewer/v0001/schema.json` as T18's contract, but T17 never created it. → A: Closed as a preliminary commit on this branch (`docs(T17-gap)`): the schema file codifies the existing `system.md` §4 output contract verbatim — `utterance` (string, 1..1200 chars) + `internal_move_executed` (5-move enum), `additionalProperties: false`. No prompt text changed, so no new prompt version (prompt-edit playbook: version bumps are for behavioural changes).
- Q: `docs/engineering/vertex-integration.md` § "JSON mode" sketches "Interviewer: no retry" — which policy wins? → A: The implementation plan's T18 acceptance ("Schema miss → single retry → failure → typed exception") wins; it is the task's own contract and postdates the sketch. Initially deferred as a follow-up doc PR; the reviewer gate (PASS-WITH-FINDINGS, 2026-07-06) directed the fix onto this branch instead — the paragraph now states the implemented single-retry policy, alongside two sibling doc-drift fixes (implementation-plan T17 stale schema sketch, coding-conventions backend layout gaining `agents/`). A fourth followed on 2026-07-07: the T19 reviewer flagged the adjacent Assessor bullet (a temperature bump is impossible at the wrapper level — `ModelCallRequest` has no temperature field — and synthesizing `needs_manual_review` in the wrapper would be a §2 routing decision); rewritten here because this branch already owns the edits to that doc file, keeping the T19 branch purely additive (recorded in the T19 spec).
- Q: Where does the system prompt get its §5/§6 appendices? → A: Assembled at runtime by this wrapper: `system.md` + `level-guide.md` + `prompts/shared/ukrainian-anchors.md`, in that order. The prompt files say so themselves ("Pulled in as an appended section at runtime", "The anchors are part of this prompt at runtime").
- Q: How are the `interview_plan_snapshot` / `current_competency` / `move_context` inputs typed? → A: Permissive `dict[str, Any]` on purpose. Their concrete shapes belong to the Planner and orchestrator contracts (T20 / Tier 4); tightening them here would force churn on this module when those land.
- Q: Does `session_id` go into the model payload? → A: No. It drives cost-ledger attribution and trace correlation via `ModelCallRequest.session_id`; `system.md` §3 does not list it as a model input, so the serialized `user_payload` excludes it.

## User Scenarios & Testing *(mandatory)*

The "user" of this feature is the deterministic orchestrator (T20): in each `TECH`-phase state it has already selected `next_planned_move` and needs exactly one schema-valid Ukrainian utterance back — or a typed failure it can route on. Secondary users are reviewers/operators, who rely on every model call flowing through `call_model` (one trace per invocation, §12 caps intact).

### User Story 1 — Orchestrator gets a typed utterance for its chosen move (Priority: P1)

The orchestrator passes the frozen plan snapshot, current competency, last ≤ 8 turns, the deterministically selected move, move context, and the candidate's first name. The wrapper assembles the versioned prompt, calls the model once, and returns a frozen `InterviewerOutput` whose `internal_move_executed` lets the orchestrator detect drift.

**Why this priority**: This is the task — Tier 3's dialogue loop cannot exist without it.

**Acceptance Scenarios**:

1. **Given** valid inputs and a schema-valid model response, **When** `run_interviewer_turn` runs, **Then** it returns `InterviewerOutput` after exactly one `call_model` invocation.
2. **Given** the issued `ModelCallRequest`, **Then** `agent == "interviewer"`, `json_schema` equals the committed `schema.json`, `session_id` is passed through, and the §12 default caps (30 s / 4096 tokens) are untouched.
3. **Given** the assembled system prompt, **Then** it contains `system.md`, `level-guide.md`, and the shared Ukrainian anchors, in that order.

### User Story 2 — Schema miss costs exactly one retry, then fails typed (Priority: P1)

The wrapper layer raises `VertexSchemaError` immediately on a schema miss (T04 Clarifications 2026-04-26 — per-agent policies live in agent modules). The Interviewer's policy: one fresh `call_model` retry on a schema-class failure (`VertexSchemaError` or parsed-output validation failure); a second failure raises `InterviewerOutputInvalid` chaining the cause. Non-schema wrapper errors (timeout, upstream, budget, config, trace-write) propagate untouched with zero agent-side retries.

**Why this priority**: T18's acceptance criterion in the implementation plan, and the boundary that keeps cost bounded (§12) and flow control deterministic (§2).

**Acceptance Scenarios**:

1. **Given** a schema miss then a valid response, **Then** the call succeeds with exactly 2 `call_model` invocations.
2. **Given** two consecutive schema misses, **Then** `InterviewerOutputInvalid` is raised, `__cause__` is the second failure, and exactly 2 invocations occurred.
3. **Given** a parsed payload violating the enum, the 1200-char cap, `minLength`, or `additionalProperties: false`, **Then** the same retry-then-raise path runs.
4. **Given** `VertexTimeoutError` (or `SessionBudgetExceeded`), **Then** it propagates after exactly 1 invocation.

### Edge Cases

- `result.parsed is None` despite `json_schema` being set (wrapper invariant break): validated through the same Pydantic path → same retry-then-raise behaviour, no special casing.
- More than 8 `recent_turns`, or an unknown `next_planned_move`: rejected at input-model construction — the orchestrator's bug surfaces before any network I/O or cost.
- Prompt files resolve via `Path(__file__).resolve().parents[3] / "prompts"` — correct both in the repo checkout and in the Docker image (`WORKDIR /app`, `COPY prompts ./prompts`).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: `app/backend/agents/interviewer.py` MUST expose one public async entry point `run_interviewer_turn(inputs, *, sink, ledger, settings) -> InterviewerOutput` and MUST NOT import any model-provider SDK (pre-commit `no-provider-sdk-imports`); its only LLM dependency is `app.backend.llm`.
- **FR-002**: Inputs MUST be a frozen Pydantic model mirroring `system.md` §3 (`interview_plan_snapshot`, `current_competency`, `recent_turns` ≤ 8 typed role+text entries, `next_planned_move` 5-move enum, `move_context`, optional `candidate_first_name`) plus `session_id: UUID` for attribution.
- **FR-003**: The system prompt MUST be assembled at runtime as `system.md` + `level-guide.md` + `prompts/shared/ukrainian-anchors.md` from the version pinned by module constant `PROMPT_VERSION = "v0001"`, cached at module level (version files are immutable), never read from `active.txt`.
- **FR-004**: The call MUST go through `call_model` with `agent="interviewer"`, `json_schema` loaded from the committed `prompts/interviewer/v0001/schema.json`, and default §12 caps (no timeout/token increases).
- **FR-005**: `result.parsed` MUST be validated into `InterviewerOutput`, a frozen Pydantic mirror of `schema.json` (`extra="forbid"`, 1..1200-char utterance, 5-move enum).
- **FR-006**: Retry policy: exactly one fresh `call_model` retry on `VertexSchemaError` or parsed-output `ValidationError`; second failure raises module-level `InterviewerOutputInvalid` chaining the cause; all other wrapper errors propagate untouched.
- **FR-007**: The module MUST be pure — no DB access, no routing decisions (§2), no side effects beyond `call_model`'s own injected sink/ledger writes.

### Key Entities

- **`InterviewerTurnInputs` / `RecentTurn`**: frozen typed inputs (system.md §3 + `session_id`).
- **`InterviewerOutput`**: frozen typed mirror of the committed output contract.
- **`InterviewerOutputInvalid`**: the typed terminal failure the orchestrator routes on.
- **`prompts/interviewer/v0001/schema.json`**: the T17-owned contract this wrapper loads verbatim (created on this branch as gap closure).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Unit suite (mocked `call_model` at the interviewer module boundary; real committed prompt files) covers: happy path, schema-miss → retry → success, schema-miss ×2 → typed exception with exactly 2 invocations, enum/caps violations on the same path, and non-retry propagation of non-schema wrapper errors — the T18 acceptance matrix.
- **SC-002**: `pytest app/backend/tests`, `ruff check`, `ruff format --check`, and `mypy --strict` all pass with the new module included.
- **SC-003**: Additive at the application layer: no existing source file modified. Existing-file changes are confined to `prompts/interviewer/v0001/notes.md` (dated addendum) plus four one-spot engineering-doc amendments applied per reviewer findings (`vertex-integration.md` Interviewer retry line, `implementation-plan.md` T17 stale schema sketch, `coding-conventions.md` backend layout + `agents/`, and — on behalf of the T19 reviewer, since this branch owns that file's edits — the `vertex-integration.md` Assessor retry bullet). T19 can land in parallel with zero shared-line conflicts (`app/backend/agents/__init__.py` re-exports nothing by design).
