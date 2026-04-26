# Feature Specification: Vertex AI Client Wrapper (T04)

**Feature Branch**: `007-t04-vertex-client-wrapper`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "T04 — Vertex client wrapper" (from `docs/engineering/implementation-plan.md`, Tier 1 / W1–W2)

## Clarifications

### Session 2026-04-26

- Q: On a JSON schema validation failure, does the wrapper itself retry, or does it raise immediately and let the agent module decide? → A: Wrapper raises a typed schema error immediately; per-agent retry / fallback / escalation policies live in the agent modules (Assessor, Planner, Interviewer each have different policies per `docs/engineering/vertex-integration.md`). The implementation-plan T04 acceptance wording will be reconciled in the plan phase as a documentation fix.
- Q: Is the wrapper API synchronous (`def`) or asynchronous (`async def`)? → A: Async-first. The wrapper exposes a single `async def` call function returning a coroutine. Agent modules, the orchestrator, and any LLM-touching service are also `async`. The T02-era sync FastAPI handlers stay sync until a given handler grows an LLM call, at which point that specific handler converts to `async def` (FastAPI supports both styles natively). Rationale: a 30-second LLM call would block a sync worker for its full duration; native Vertex SDK async paths exist (`generate_content_async`); the `vertex-call` skill already shows `await call_model(...)`.
- Q: When does the wrapper write the trace record — synchronously before returning, fire-and-forget after returning, or hybrid? → A: Synchronously, before returning the result (or before raising any wrapper-level error). If the trace sink itself fails, the wrapper raises a typed `TraceWriteError` (or equivalent) and the call is treated as failed — the orchestrator halts the session. Rationale: constitution §1 makes audit non-negotiable, not best-effort; a "lost trace" equals a call that escaped audit, which violates the principle. Database write latency (~5–20 ms on the local DB) is noise compared to a 1–10 s LLM call. Tests are simpler: when `await call_model(...)` returns, the trace is already in the sink — no `flush()` plumbing needed.
- Q: What is the canonical retry budget for transient upstream failures? → A: Uniform **3 attempts total** (1 initial + 2 retries) with exponential backoff and jitter, on the set: HTTP 5xx (`ServiceUnavailable`, `InternalServerError`), HTTP 429 (`ResourceExhausted` / rate-limit), and connection-level errors (refused, reset). `DeadlineExceeded` is **excluded** from retry — the timeout already fired, repeating it only burns the 30-second wall-clock budget. All retries together stay under the 30-second wall-clock cap. Per-error-type retry counts in `docs/engineering/vertex-integration.md` will be reconciled to this uniform policy in the plan-phase documentation-fix task (same task as the schema-retry reconciliation).
- Q: Does T04 ship the seed `configs/models.yaml`, or is it deferred to T17? → A: T04 ships it. The file contains entries for `interviewer`, `assessor`, and `planner` with model names per ADR-003 (Gemini 2.5 Flash for interviewer/assessor, Gemini 2.5 Pro for planner), per-agent temperature and max_output_tokens defaults, and `prompt_version: "v0001"` as a placeholder string. T17 later replaces the placeholder version when the actual prompt content lands under `prompts/<agent>/v0001/`. T04 does **not** add anything under `prompts/`. Rationale: without the file the wrapper's agent resolver code path goes untested in T04; constitution §16 (configs as code) treats this file as part of the system contract; the file is small (~15 lines) and T17 will touch it anyway.

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are the humans and AI sub-agents that build every later LLM-touching feature: `backend-engineer` writing the Interviewer (T18), Assessor (T19), Planner (T21) services and the orchestrator (T20); `prompt-engineer` running calibration jobs and prompt evals (T17, the `calibration-run` skill); `infra-engineer` wiring the deploy smoke (T11) and observability dashboards (T07); operators and reviewers auditing per-session cost, latency, and outcomes long after a session has ended; and the `reviewer` sub-agent enforcing constitution §12 (cost / latency caps) and ADR-013 (no plaintext credentials) on every PR. T04 is the **single sanctioned doorway** through which every model token flows for the lifetime of the product. Until it exists, no agent service can be written, no calibration can run, and the Tier-1 deploy gate (T11) cannot light up.

### User Story 1 — A single sanctioned call path enforces hard §12 caps (Priority: P1)

Every later agent task (T17–T21) needs a function it can call to ask Gemini something — without each of them having to re-derive the timeout policy, the retry policy, the cost cap, or the auth flow. Constitution §12 sets hard caps (30 s timeout, 4096 max output tokens) that must be enforced consistently. ADR-002 forbids any direct call to a non-Vertex provider. Without one canonical path, four downstream agents will each invent their own and at least one will silently violate a cap.

**Why this priority**: P1 because it is the entire point of T04. Every later LLM task depends on this path existing and being trustworthy. A single missed cap on a runaway loop in production costs real money and is reportable to leadership; a missed cap discovered after four agents have shipped is a multi-PR rollback.

**Independent Test**: A backend engineer (or sub-agent) writes a 10-line caller that imports the wrapper, asks for a structured-output completion, and receives parsed JSON — without importing the Vertex SDK directly anywhere. A second test that asks the wrapper for a completion with `timeout = 31 s` or `max_output_tokens = 4097` is rejected before any network call is made.

**Acceptance Scenarios**:

1. **Given** the post-T04 tree, **When** a developer calls the wrapper with a valid request (model, prompt, session id), **Then** they receive a typed result containing the raw text and (if a JSON schema was supplied) parsed and validated JSON, plus a trace identifier — without their code importing the Vertex SDK.
2. **Given** any caller passes a per-call `timeout` greater than 30 seconds or `max_output_tokens` greater than 4096, **When** the call is invoked, **Then** the wrapper raises a typed configuration error before any network I/O occurs.
3. **Given** a transient upstream failure (HTTP 5xx, rate-limit, network reset), **When** the wrapper handles the call, **Then** it retries with exponential backoff up to a documented small cap, all attempts together still bounded by the 30-second wall clock; on exhaustion it raises a typed upstream-unavailable error.
4. **Given** a static guardrail is in place, **When** any non-wrapper module imports the Vertex SDK (or any other model provider's SDK), **Then** the guardrail blocks the commit locally and the same check fails in CI.

---

### User Story 2 — Local dev and CI run the wrapper without real Vertex credentials (Priority: P1)

T04 unblocks several parallel downstream tasks (T17 prompts, T18 Interviewer, T19 Assessor, T20 orchestrator, T21 Planner). Each of those tasks has its own tests. None of those tests can require a live Vertex credential, an active GCP billing account, or network egress to `europe-west1` — that would make local dev painful, CI flaky, and CI cost unbounded. T04 must therefore ship a deterministic mock backend that presents the same interface as the real one, so call sites never branch on environment.

**Why this priority**: Co-equal P1 with User Story 1. Without a usable mock, the entire downstream pipeline is gated on Vertex credentials being provisioned for every developer and every CI runner — which contradicts ADR-013 (no JSON SA keys floating around). With the mock, T18–T21 can be developed and tested in parallel by sub-agents on a fresh laptop.

**Independent Test**: A developer clones the repo, runs the documented backend test command without ever exporting any GCP credential and without any GCP project configured, and observes a green test run that includes at least one wrapper smoke test exercising the mock backend end-to-end.

**Acceptance Scenarios**:

1. **Given** the wrapper backend is configured to mock mode (the documented dev/CI default), **When** a caller invokes the wrapper, **Then** the response is sourced from a deterministic, prompt-keyed fixture without any network I/O leaving the process or container.
2. **Given** the call site code, **When** the wrapper is run in mock mode versus real mode, **Then** the call site is identical — the result type, error types, and trace structure do not differ between modes.
3. **Given** a configuration intended for production, **When** the backend process starts with the mock backend selected, **Then** startup fails with a clear error before serving the first request.
4. **Given** a prompt whose SHA is not present in the fixture set, **When** the wrapper is invoked in mock mode, **Then** the wrapper records the unseen prompt to a documented "unrecorded" location and surfaces a deterministic, debuggable error so a developer can promote it into a fixture.

---

### User Story 3 — Every model call produces an audit-quality trace (Priority: P1)

Constitution §1 (auditability) and the calibration / replay obligation (ADR-018, ADR-019) require that every LLM interaction be reconstructable later. Cost monitoring (§12), latency regression detection, and the calibration-run skill all build on this signal. The wrapper is the only place every call passes through, so it is the only honest place to record the trace. The record must be produced for **every** attempt — successful, retried, timed-out, schema-violating, or budget-blocked — because the failures are exactly what we need to debug.

**Why this priority**: Co-equal P1. A skipped trace row is invisible debt: the call cost real money, affected a real candidate, and we can never explain it. The cheapest moment to make tracing inescapable is when the wrapper is born; retrofitting it later means combing every caller.

**Independent Test**: A reviewer runs the wrapper test suite, picks any single test invocation (success or failure), and confirms that exactly one trace record was produced with all required fields populated — agent, model, model version, session id, input/output token counts, cost, latency, attempts, outcome, prompt content hash, and a stable trace identifier.

**Acceptance Scenarios**:

1. **Given** any wrapper invocation reaches a terminal state (returned a result OR raised any typed error from this feature), **When** the call is observed by the trace sink, **Then** exactly one trace record is emitted that captures agent, model, model version, session id, input tokens, output tokens, cost (USD), latency (ms), attempt count, outcome category, prompt content hash, and a unique trace identifier.
2. **Given** the wrapper retries on transient failure, **When** the final outcome is recorded, **Then** the trace records the total attempt count and the final outcome (not just the first attempt), preserving cost across all attempts.
3. **Given** the constitution §15 PII obligation already enforced in T02 logs, **When** a trace record is observed, **Then** the record contains no raw prompt text, no raw model output text, no candidate PII, and no credential material — only hashes, identifiers, counts, and metadata. Operators look up details by trace identifier.
4. **Given** the trace sink is an injected interface in T04 (the database for `turn_trace` does not yet exist), **When** the wrapper is exercised in tests, **Then** an in-memory sink captures every trace record, and replacing it with the real (database) sink in a later task does not require any change to the wrapper or its callers.

---

### User Story 4 — Structured JSON output is schema-validated before the caller sees it (Priority: P2)

The Interviewer and Assessor agent contracts (T17) are strict JSON schemas — Interviewer returns `{message_uk, intent, next_topic_hint, end_of_phase}`, Assessor returns `{concepts_covered, concepts_missing, red_flags, level_estimate, confidence}`. Constitution §2 forbids LLM-driven flow control on free-text output; only validated typed JSON fields may drive routing. If schema validation lives at each call site, every agent author re-implements it slightly differently, and at least one of them silently lets a malformed object through into the orchestrator.

**Why this priority**: P2, because the P1 stories deliver the wrapper itself; this story makes the wrapper *useful* for the structured-output agents. T17–T21 cannot land without it, but it is a smaller scope item than the wrapper foundation.

**Independent Test**: A test calls the wrapper with a JSON schema and a prompt that produces a schema-conforming payload; the result is parsed and validated JSON. A second test forces (via the mock fixture) a schema-violating response; the wrapper raises a typed schema error immediately with the raw output attached for debugging — no wrapper-level retry.

**Acceptance Scenarios**:

1. **Given** a caller passes a JSON schema with the request, **When** the model returns a payload that conforms to the schema, **Then** the wrapper returns parsed JSON validated against the schema in the typed result.
2. **Given** a caller passes a JSON schema, **When** the model returns a payload that does not conform to the schema, **Then** the wrapper raises a typed schema-validation error immediately (no retry) and attaches the raw payload to the error so the agent module can inspect it and apply its own per-agent policy (retry with adjusted parameters, fall back, or escalate).
3. **Given** a caller does not pass a JSON schema, **When** the call succeeds, **Then** the wrapper returns the raw text without parsing, and schema-related errors are not in the error envelope.

---

### User Story 5 — Per-session cost ceiling halts a runaway session before it costs real money (Priority: P2)

Constitution §12 sets a per-session cost ceiling (default $5 USD). The orchestrator (T20) and recruiter dashboards (later tier) consume this signal, but the only place it can be enforced *before* spend happens is the wrapper, because the wrapper is the only point that knows the session id, the price table, and the projected cost of the next call.

**Why this priority**: P2. Cost overrun in a single dev session is small; cost overrun in production with a buggy retry loop is meaningful. Enforcement at the wrapper makes the ceiling a property of the system rather than a discipline of every author.

**Independent Test**: A test seeds an injected cost ledger with a session aggregate already at the ceiling; calling the wrapper with that session id raises a typed budget-exceeded error before any network I/O. A second test starts at $0 and measures that successful calls increment the ledger by the price-table amount.

**Acceptance Scenarios**:

1. **Given** a session whose injected cost-ledger total is below the ceiling, **When** the wrapper is invoked for that session, **Then** the call proceeds and the ledger is updated with the call's actual cost on completion.
2. **Given** a session whose injected cost-ledger total is at or above the per-session ceiling, **When** the wrapper is invoked for that session, **Then** the wrapper raises a typed budget-exceeded error before any network I/O, and a trace record is produced with outcome `budget_exceeded` and zero token counts.
3. **Given** the per-session ceiling is configurable, **When** the runtime is configured to a value above the documented production ceiling, **Then** in production the wrapper refuses to start; in tests, the configurability is allowed.

---

### Edge Cases

- **Caller passes an unknown agent identifier or unknown model identifier.** Treated as a configuration error and rejected before any network I/O. The price table acts as the canonical model registry; an unknown model has no price and therefore no cost projection.
- **Caller passes `timeout = 0` or `max_output_tokens = 0`.** Configuration error at the boundary; wrapper does not attempt the call.
- **Caller forgets to pass `session_id`.** Configuration error — the wrapper cannot enforce the per-session cost ceiling or attribute the trace without it.
- **Vertex returns HTTP 200 with a payload that is not parseable JSON when JSON mode was requested.** Treated as a schema mismatch: the wrapper raises a typed schema error immediately (no wrapper-level retry) with the raw payload attached. Per-agent retry / fallback / escalation policies live in the agent modules (see Clarifications 2026-04-26).
- **Vertex returns 5xx for the full retry budget.** Wrapper raises a typed upstream-unavailable error; the trace records the outcome and the total attempts.
- **Vertex hangs.** The 30-second wall clock fires; the wrapper aborts and raises a typed timeout error; trace records `outcome: timeout`.
- **Session aggregate cost was already above the ceiling at the moment of call.** Wrapper raises the typed budget error before any network I/O; the trace records `outcome: budget_exceeded`.
- **Concurrent calls for the same session id.** The cost-ledger interface defines the concurrency contract — its implementation owns it. T04 ships an in-memory implementation that is correct for single-process / single-event-loop use; the durable, multi-process ledger is a later-task concern.
- **PII in prompt content.** The wrapper does not inspect prompt content for PII — that is the agent module's job. The wrapper's logs and traces never contain prompt text, only prompt hashes; this preserves the §15 boundary established in T02.
- **Mock fixture missing for a given prompt SHA.** The wrapper records the unseen SHA into a documented "unrecorded" location and surfaces a clear, deterministic test-time error so the developer can promote it into a fixture. Production never reaches this branch — production refuses to start in mock mode.
- **`LLM_BACKEND` environment variable unset.** Mock is the dev/CI default; production must explicitly select the real backend at startup.
- **Caller catches `SessionBudgetExceeded` and retries in a loop.** This is a caller-side anti-pattern called out in the `vertex-call` skill; T04 cannot prevent it but must produce a trace per attempt so it is visible to operators.
- **Trace sink unavailable (e.g., DB connection lost, in-memory sink misconfigured).** The wrapper raises a typed `TraceWriteError` after the call has otherwise completed (whether the LLM call itself succeeded or failed). The orchestrator (T20) treats this as a session-halting condition because the call escaped audit. T04 ships the in-memory sink which fails only on programmer error (e.g., capacity bound exceeded in tests); the durable DB sink in T05+ may fail on infrastructure incidents.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The repository MUST contain a single backend module (the Vertex wrapper) at the canonical path established by the implementation plan (`app/backend/llm/vertex.py`). The wrapper MUST be the sole entry point for every model call made by any backend code or auxiliary script in the repository.
- **FR-002**: The wrapper MUST expose a single primary `async` call function (per Clarifications 2026-04-26) whose signature accepts at minimum: agent identifier, model identifier, system prompt, user input, optional response JSON schema, per-call timeout (seconds), max output tokens, and session identifier. The signature MUST refuse to accept a per-call timeout greater than 30 seconds or max output tokens greater than 4096; such requests MUST raise a typed configuration error before any network I/O. The wrapper MUST NOT expose a parallel synchronous variant — callers awaiting the wrapper convert their own surface to `async def` as needed.
- **FR-003**: The wrapper MUST enforce a hard 30-second wall-clock timeout per call covering all retry attempts combined; on expiry it MUST raise a typed timeout error.
- **FR-004**: The wrapper MUST retry on transient upstream failures using exponential backoff with jitter, with a uniform total cap of **3 attempts** (1 initial + 2 retries) per Clarifications 2026-04-26. The retried error set is: HTTP 5xx (`ServiceUnavailable`, `InternalServerError`), HTTP 429 / `ResourceExhausted` (rate-limit), and connection-level errors (refused, reset). The wrapper MUST NOT retry on `DeadlineExceeded`, on caller-side errors (`InvalidArgument`, `PermissionDenied`), or on JSON schema validation failures. All retries combined MUST remain under the 30-second wall-clock cap from FR-003.
- **FR-005**: The wrapper MUST select between a real Vertex backend and a local mock backend based on a documented runtime configuration value (e.g., environment variable). The two backends MUST present an identical interface so that no caller branches on the selected backend.
- **FR-006**: The mock backend MUST return deterministic responses keyed by a stable hash of the prompt content, sourced from a fixture directory committed to the repository. When invoked with a prompt whose hash is not in the fixture set, the mock MUST record the unseen hash to a documented "unrecorded" location and raise a deterministic test-time error.
- **FR-007**: A production deployment MUST refuse to start when the backend selection resolves to mock mode. The check MUST run at process startup, not on first call.
- **FR-008**: Every call attempt that reaches a terminal state (returned a result OR raised any typed wrapper error) MUST produce exactly one structured trace record capturing: agent identifier, model identifier and version, session identifier, input token count, output token count, cost in USD, latency in milliseconds, total attempt count, outcome category (`ok`, `schema_error`, `timeout`, `upstream_unavailable`, `budget_exceeded`, `trace_write_error`, or equivalent set), prompt content hash, and a unique trace identifier.
- **FR-009**: The trace record MUST be persisted via an injected sink interface, **synchronously, before the wrapper returns its result or raises any other wrapper-level error** (per Clarifications 2026-04-26). The wrapper MUST NOT import a database module directly. T04 MUST ship at least one in-memory implementation of the sink usable in tests; the durable implementation is delivered by T05 (DB schema baseline). If the sink itself fails, the wrapper MUST raise a typed `TraceWriteError` (or equivalent) — the call MUST NOT be returned as successful when its trace was not durably written, because constitution §1 (auditability) makes audit non-negotiable.
- **FR-010**: The wrapper MUST compute per-call cost from observed token counts and a committed price table located in `app/backend/llm/` (e.g., `pricing.yaml`). The price table MUST be versioned in source control. An unknown model identifier MUST raise a typed configuration error rather than silently default to a price of zero.
- **FR-011**: When a caller passes a JSON schema with the request, the wrapper MUST request structured JSON output from the underlying backend AND validate the parsed payload against the schema. On validation failure the wrapper MUST raise a typed schema error immediately (no wrapper-level retry) with the raw payload attached so the calling agent module can apply its own per-agent retry / fallback / escalation policy. (See Clarifications 2026-04-26.)
- **FR-012**: The wrapper MUST consult an injected per-session cost ledger before each call. If admitting the next call would result in the session aggregate exceeding the documented per-session ceiling (default $5 USD), the wrapper MUST raise a typed budget-exceeded error before any network I/O AND emit a trace record with outcome `budget_exceeded`.
- **FR-013**: Logs emitted by the wrapper MUST NOT contain raw prompt text, raw model output text, candidate PII, or credential material. Log lines MUST reference the trace identifier so operators can look up details. The wrapper MUST use the project logger configured in T02 — it MUST NOT install its own formatter that bypasses the §15 PII redaction.
- **FR-014**: A static guardrail MUST refuse any commit that imports a model-provider SDK (Vertex AI, Google AI Studio, Anthropic, OpenAI, etc.) from any module other than the canonical wrapper. The guardrail MUST run as a pre-commit hook AND as a CI step, with the same command in both places, matching the T01/T02 parity pattern.
- **FR-015**: The wrapper MUST authenticate to Vertex AI exclusively via Application Default Credentials. The wrapper MUST NOT accept a JSON service-account key, an inline private key, or any other secret material as a configuration parameter. No new secret keys MUST be added to `.env.example` by T04.
- **FR-016**: Backend lint and type-check from T01/T02 MUST exit zero on the post-T04 tree. `mypy --strict` MUST pass on `app/backend/llm/`.
- **FR-017**: At least one committed backend test MUST exercise the wrapper end-to-end via the mock backend, covering: (a) a successful call with a JSON schema returns parsed and validated JSON; (b) a request configured with timeout > 30 s or max output tokens > 4096 is rejected before any network I/O; (c) a deliberately schema-violating mock response causes the wrapper to raise a typed schema error immediately (no wrapper-level retry) with the raw payload attached; (d) a session whose ledger is at the ceiling raises a typed budget-exceeded error before any network I/O; (e) each of the above produces exactly one trace record with the required fields.
- **FR-018**: T04 MUST NOT introduce any database schema, any Alembic migration, any candidate-facing or admin-facing endpoint, any authentication middleware, or any change to the committed `app/backend/openapi.yaml`. The OpenAPI regeneration guardrail from T02 MUST continue to pass with no diff.
- **FR-019**: The active per-agent model, prompt version, temperature, and max output tokens MUST be resolved from a committed configuration file at `configs/models.yaml` (per the `vertex-call` skill); the wrapper MUST NOT contain hard-coded model names at the call site. T04 MUST ship the seed `configs/models.yaml` (per Clarifications 2026-04-26) with one entry each for `interviewer`, `assessor`, and `planner`, populated with the model identifiers from ADR-003, per-agent temperature and max_output_tokens defaults, and `prompt_version: "v0001"` as a placeholder string. T17 later replaces the placeholder when the actual prompt content lands under `prompts/<agent>/v0001/`. T04 MUST NOT add any file under `prompts/`.

### Key Entities

- **Vertex wrapper.** The single sanctioned backend module that every model call passes through. Owns timeout, retry, cost, schema validation, mock vs real backend routing, trace emission, and authentication.
- **Model call request.** Typed input describing agent, model, system prompt, user input, optional schema, per-call caps, and session identifier.
- **Model call result.** Typed output containing raw text, parsed JSON (only when a schema was supplied), token counts, computed cost, latency, total attempts, and trace identifier.
- **Trace record.** Append-only audit record produced for every call attempt's terminal state. Persisted via the injected sink interface; in T04 it is captured in memory for tests, in a later task it lands in the `turn_trace` database table.
- **Cost ledger.** Per-session running total of LLM spend, consulted before each call by the wrapper. Injected interface; T04 ships an in-memory implementation, the durable implementation arrives later.
- **Mock backend.** Deterministic stub returning fixture-keyed responses by prompt hash. Used by default in dev and CI; production refuses to start with the mock backend selected.
- **Price table.** Committed YAML mapping model identifier to per-token input/output prices. Authoritative for cost computation; an unknown model identifier is a configuration error.
- **Model registry config.** Committed YAML (`configs/models.yaml`) mapping agent name to active model, prompt version, temperature, and max output tokens. Read by the wrapper or its caller-side adapter so call sites do not hard-code model identifiers.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A backend engineer (human or sub-agent) writing a new agent service can issue a structured-output model call (prompt + schema → parsed JSON) in 10 lines of caller code or fewer, without importing any model-provider SDK and without configuring caps, timeouts, retries, auth, cost tracking, or trace persistence at the call site.
- **SC-002**: 100% of configured calls with `timeout > 30 s` or `max_output_tokens > 4096` are rejected before any network I/O, measured by parametric tests that assert the typed configuration error is raised.
- **SC-003**: 100% of attempts to import a model-provider SDK from a module other than the canonical wrapper are blocked by the guardrail before merge — verified by a fixture commit that intentionally violates the rule and observes the guardrail failing.
- **SC-004**: 100% of wrapper invocations that reach a terminal state in the test suite produce exactly one trace record with all required fields populated; zero invocations produce zero or more than one record.
- **SC-005**: A developer can clone the repository, run the documented backend test command on a clean tree without exporting any GCP credential and without any GCP project configured, and observe a green test run that includes at least one wrapper end-to-end smoke through the mock backend, in under 60 seconds total wall-clock.
- **SC-006**: When a session's projected aggregate cost would push it over the per-session ceiling, the wrapper refuses the call with a typed error in 100% of cases, before any network I/O — measured by a test that seeds the ledger at and above the ceiling.
- **SC-007**: A reviewer (human or sub-agent) can determine the agent, model, model version, token counts, cost, latency, attempt count, and outcome of any historical call from one trace record, without re-running the call.
- **SC-008**: `ruff check app/backend/llm` and `mypy --strict app/backend/llm` exit zero on the post-T04 tree.
- **SC-009**: The committed `app/backend/openapi.yaml` is byte-identical before and after T04 (the wrapper exposes no HTTP endpoint), measured by the existing T02 regeneration guardrail.
- **SC-010**: Production startup fails fast with a clear error in 100% of cases when the backend selection resolves to mock mode, measured by a test that constructs the production startup configuration with mock selected and asserts the startup error.

## Assumptions

- The implementation plan T04 description and the `.claude/skills/vertex-call/SKILL.md` document are the authoritative behavioural source for this feature. Where they conflict with older or auxiliary documents, those sources win. **Exceptions (per Clarifications 2026-04-26)** captured for a single plan-phase documentation-fix task that reconciles three sources (`implementation-plan.md`, `.claude/skills/vertex-call/SKILL.md`, `docs/engineering/vertex-integration.md`) against the spec: (1) the wrapper does **not** retry on schema validation failures — agent modules own per-agent policies; (2) the wrapper exposes a single uniform transient-error retry policy (3 attempts total) rather than the per-error-type table in `vertex-integration.md`; `DeadlineExceeded` is excluded from retry.
- The wrapper's primary call function is `async` (per Clarifications 2026-04-26). T04 introduces no change to the existing T02 sync FastAPI handlers — they remain `def` until a given handler grows an LLM call (which happens in T18/T20 and is that task's scope, not T04's). Test wiring uses `pytest-asyncio` (or `anyio` plugin); the choice between the two is an implementation detail captured in the plan phase.
- Database persistence of `turn_trace` rows and the `llm_cost` ledger arrives in T05 (DB schema baseline). T04 ships injectable sinks with in-memory implementations so the wrapper can be exercised end-to-end without a database, and the database-backed implementations later replace the in-memory ones with no caller-side changes.
- The mock backend in T04 is an in-process stub keyed by prompt SHA, sourced from a fixture directory under `app/backend/tests/fixtures/llm_responses/`. The Docker-compose `vertex-mock` HTTP service referenced in `docs/engineering/vertex-integration.md` is wired by T09 (Docker stacks); T04 is not on the hook for the HTTP server, only for the in-process backend selection and fixture loader.
- The committed price table covers Gemini 2.5 Flash and Gemini 2.5 Pro for `europe-west1` per ADR-003 and ADR-015. Adding a new model is a price-table PR.
- The default per-session cost ceiling is $5 USD per constitution §12 and the `vertex-call` skill. The ceiling is configurable via environment for tests but the wrapper MUST refuse to start in production with a value above the documented ceiling.
- The per-call timeout default is 30 seconds and max output tokens default is 4096 per constitution §12. Callers MAY request lower; the wrapper rejects higher.
- The "no direct provider SDK import outside the wrapper" guardrail is implemented as a pre-commit hook AND a CI step running the same command, matching the T01/T02 parity pattern.
- Authentication uses Application Default Credentials per ADR-013. T04 introduces no JSON service-account key, no inline private key, and no new secret in `.env.example` (per ADR-022 the `.env.example` may carry non-secret defaults but never secret values).
- T04 introduces no Alembic migration. The `turn_trace` table schema lands in T05.
- T04 does not change `app/backend/openapi.yaml` — the wrapper is internal and exposes no HTTP endpoint.
- T04 ships `configs/models.yaml` as a seed with entries for `interviewer`, `assessor`, and `planner` (per Clarifications 2026-04-26 — FR-019 promoted from MAY to MUST). Model identifiers come from ADR-003 (Gemini 2.5 Flash for interviewer/assessor, Gemini 2.5 Pro for planner); per-agent temperature and max_output_tokens defaults from the `vertex-call` skill; `prompt_version` is the placeholder string `"v0001"`. The actual prompt version *content* (`prompts/<agent>/v0001/system.md`, `schema.json`, `notes.md`) lands with T17; T04 only references the version string, not the content.
- The existing T02 PII redaction layer continues to apply automatically to the wrapper's log lines because the wrapper uses the project logger configured in T02. T04 must not bypass or reconfigure it.
- The `reviewer` sub-agent treats a passing backend test run, a clean OpenAPI regeneration diff, a passing guardrail (no out-of-wrapper SDK imports), and the existence of trace records on every test invocation as the minimum bar for T04 acceptance, alongside the existing T01/T02 guardrails.

## Dependencies

- **Upstream (required)**: T02 (FastAPI skeleton) — provides `app/backend/llm/`, the structured logger with §15 PII redaction, the lint/type-check targets, and the test wiring convention. T01a (Vertex AI quota + region request) — confirms `europe-west1` quota for Gemini 2.5 Flash and Pro is in place; without it, end-to-end smoke against the *real* backend is impossible (the *mock* backend has no such dependency).
- **Downstream (blocked until T04 merges)**: T17 (agent prompts + per-agent JSON schemas — call sites for the wrapper), T18 (Interviewer agent service), T19 (Assessor agent service), T20 (orchestrator state machine — every state transition that needs a model call uses the wrapper), T21 (Planner agent service), T11 (Tier-1 deploy gate — runs an end-to-end ping through the wrapper from a deployed Cloud Run revision). The `calibration-run` skill also depends on the wrapper (it issues real or mock model calls and inspects traces).
- **External**: Google Vertex AI in `europe-west1` reachable from the developer environment, *only* when running against the real backend (`LLM_BACKEND=vertex`); the mock backend has no external dependency. Application Default Credentials must resolve to a principal with the appropriate Vertex IAM role for non-mock invocations.
