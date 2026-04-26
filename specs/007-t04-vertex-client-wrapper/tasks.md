# Tasks: Vertex AI Client Wrapper (T04)

**Input**: Design documents from `/specs/007-t04-vertex-client-wrapper/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/wrapper-contract.md`, `quickstart.md` — all present.

**Tests**: Tests are REQUIRED for this feature — the spec defines a 10-test FR-017 matrix in [`contracts/wrapper-contract.md` §10](contracts/wrapper-contract.md). Each test maps to a specific spec FR and is exercised in the user-story phases below.

**Organization**: Foundational phase (Phase 2) lands ALL implementation files (the wrapper module, support types, guardrail, configs, fixtures) — this is honest about how a single-PR T04 actually flows: the wrapper file is one cohesive piece, not five independently-shippable slices. User-story phases (Phases 3–7) own their **test slices** — each story's tests can be run independently to verify the corresponding FR set in isolation. Polish phase (Phase 8) covers docs, the docfix, the README, and the post-merge verification commands.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5). Setup / Foundational / Polish phases carry no story label.
- File paths are absolute under repo root.

## Path Conventions

This is a backend monorepo slice. All Python source lives under `app/backend/`, all tests under `app/backend/tests/`, configs under `configs/` (new top-level), shell scripts under `scripts/`, docs under `docs/engineering/`. Two top-level files (`pyproject.toml`, `.env.example`, `.pre-commit-config.yaml`, `README.md`) are edited.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Land the dependency manifest changes, pytest configuration, and empty package layout so every later phase has somewhere to put its files.

- [X] T001 Add runtime deps `google-genai>=0.5,<1`, `tenacity>=9.0,<10`, `pydantic-settings>=2.6,<3` to `pyproject.toml` `[project].dependencies`; add `pytest-asyncio>=0.23,<1` to `[dependency-groups].dev`; add `[tool.pytest.ini_options].asyncio_mode = "auto"`; run `uv lock` to regenerate `uv.lock`.
- [X] T002 [P] Add the three non-secret env keys to `.env.example`: `LLM_BACKEND=mock`, `LLM_BUDGET_PER_SESSION_USD=5.00`, `LLM_FIXTURES_DIR=app/backend/tests/fixtures/llm_responses` (per ADR-022 these may carry non-secret defaults). `APP_ENV=dev` is **already** present from T01 — `Settings` reads it as the canonical runtime selector (no new selector introduced).
- [X] T003 [P] Create empty package marker `app/backend/llm/__init__.py` (will be populated in T017 with public re-exports).
- [X] T004 [P] Create empty package marker `app/backend/tests/llm/__init__.py`.
- [X] T005 [P] Create the fixtures directory tree: `app/backend/tests/fixtures/llm_responses/{interviewer,assessor,planner}/` and `app/backend/tests/fixtures/llm_responses/_unrecorded/.gitkeep`.

**Checkpoint**: `uv sync` succeeds; the new env keys are visible in `.env.example`; the new package directories exist.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Land every implementation file — typed errors, Settings, pricing, models config, backend protocol, trace sink, cost ledger, mock backend, real backend, the wrapper itself, the static guardrail, and `main.py` wiring. After this phase, the wrapper is fully functional; user-story phases add only tests.

**⚠️ CRITICAL**: No user story phase can start until Phase 2 is complete. The user-story phases consume the modules and types this phase lands.

### Typed support modules (most can run in parallel — distinct files, no cross-deps yet)

- [X] T006 [P] Implement typed error hierarchy in `app/backend/llm/errors.py`: `WrapperError` base + `ModelCallConfigError`, `VertexTimeoutError`, `VertexUpstreamUnavailableError`, `VertexSchemaError(message, *, raw_payload)`, `SessionBudgetExceeded`, `TraceWriteError`. Match the structure in [data-model.md §6](data-model.md#6-typed-error-hierarchy).
- [X] T007 [P] Implement `Settings` class in `app/backend/settings.py` using `pydantic-settings` with the four fields and `assert_safe_for_environment()` method as specified in [data-model.md §10](data-model.md#10-settings-pydantic-settings-env-loader). The method MUST raise `RuntimeError` for the production+mock and production+budget>5 cases.
- [X] T008 [P] Implement pricing.yaml at `app/backend/llm/pricing.yaml` with the two model entries (Gemini 2.5 Flash and Pro) using string-encoded Decimal prices per [`contracts/wrapper-contract.md` §5](contracts/wrapper-contract.md). Implement the loader at `app/backend/llm/pricing.py` with `ModelPricing`, `PricingTable`, and `PricingTable.cost_for(model, input_tokens, output_tokens) -> Decimal` raising `ModelCallConfigError` on unknown model.
- [X] T009 [P] Implement `configs/models.yaml` with the three agent entries (`interviewer`, `assessor`, `planner`) per [`contracts/wrapper-contract.md` §4](contracts/wrapper-contract.md). Implement the loader at `app/backend/llm/models_config.py` with `ModelConfig`, `ModelsConfig`, and `ModelsConfig.for_agent(name) -> ModelConfig` raising `ModelCallConfigError` on unknown agent.
- [X] T010 [P] Implement the backend `Protocol` in `app/backend/llm/_backend_protocol.py`: `VertexBackend(Protocol)` with `async def generate(...)` per [data-model.md §7](data-model.md#7-vertexbackend-protocol-and-concrete-backends), and `RawBackendResult` Pydantic model.
- [X] T011 [P] Implement `app/backend/llm/trace.py`: `TraceRecord` Pydantic model (frozen, all fields per [data-model.md §3](data-model.md#3-tracerecord--append-only-audit-row)), `TraceSink(Protocol)` with `async def write(record)`, and `InMemoryTraceSink` concretion with capacity bound that raises `TraceWriteError` on overflow.
- [X] T012 [P] Implement `app/backend/llm/cost_ledger.py`: `CostLedger(Protocol)` with `async def session_total(session_id)` and `async def add(session_id, cost_usd)`, plus `InMemoryCostLedger` concretion using `asyncio.Lock` per [data-model.md §9](data-model.md#9-costledger-protocol-and-inmemorycostledger).

### Backends (depend on T006 errors and T010 protocol)

- [X] T013 Implement `MockVertexBackend` in `app/backend/llm/_mock_backend.py`: SHA-256 prompt-canonicalisation per research §13, fixture lookup under `<fixtures_dir>/<agent>/<sha>.json`, `_unrecorded/` capture on miss raising `RuntimeError("fixture missing for prompt SHA <hex>; see _unrecorded/<sha>.json")`. Depends on T006, T010.
- [X] T014 Implement `RealVertexBackend` in `app/backend/llm/_real_backend.py` using `google-genai` async client (`Client(vertexai=True, location="europe-west1").aio.models.generate_content(...)`). This is the **only** non-test module allowed to import a model-provider SDK. Depends on T006, T010.

### Initial fixture set (depend on T013 mock backend behaviour for the SHA recipe)

- [X] T015 Author the four initial fixture files under `app/backend/tests/fixtures/llm_responses/`: one schema-valid sample per agent (`interviewer/<sha>.json`, `assessor/<sha>.json`, `planner/<sha>.json`) plus one deliberately schema-INVALID fixture (`assessor/<sha-of-broken-prompt>.json`). Use the canonical SHA recipe from research §13 against the test prompts the wrapper-tests will use. Filenames are full SHA-256 hex strings. Envelope per [`contracts/wrapper-contract.md` §9](contracts/wrapper-contract.md). Depends on T013.

### Wrapper (consumes everything above)

- [X] T016 Implement `async def call_model(request, *, sink, ledger, settings) -> ModelCallResult` in `app/backend/llm/vertex.py`. Follow the 10-step behaviour contract in [`contracts/wrapper-contract.md` §1](contracts/wrapper-contract.md): validate request → resolve agent config → look up pricing → consult ledger (short-circuit on budget) → choose backend by `settings.llm_backend` → wrap call in `tenacity.AsyncRetrying` (3-attempt budget, exclude `DeadlineExceeded`) under `asyncio.wait_for(timeout_s)` → if `json_schema is not None` validate via `pydantic.TypeAdapter(dict).validate_python` (no retry on schema miss per Clarifications 2026-04-26) → compute cost via `pricing.cost_for(...)` → increment ledger → build `TraceRecord` (`outcome="ok"`) and `await sink.write(record)` synchronously (raise `TraceWriteError` on sink failure) → return `ModelCallResult`. Emit one structlog `llm_call` event per terminal state with the field set in research §15 (NO prompt text, NO output text). **REQUIRED inline comment block** above the `RETRY_BUDGET = AsyncRetrying(...)` definition citing constitution §12 and FR-003: "3 attempts × max ~4 s backoff ≈ 12 s worst case; the hard 30-s wall-clock cap is enforced by `asyncio.wait_for(...)`. Changing backoff parameters requires re-verifying the math vs the 30-s cap and FR-003." (Per analysis finding C2: a human-readable invariant note prevents future drift without introducing a flaky timing-based test.) Depends on T006, T007, T008, T009, T010, T011, T012, T013, T014.
- [X] T017 Implement public re-exports in `app/backend/llm/__init__.py`: `call_model`, `ModelCallRequest`, `ModelCallResult`, plus the seven error classes from `errors.py`. Depends on T016.

### Wiring (depends on T007 Settings)

- [X] T018 Wire `Settings().assert_safe_for_environment()` into `app/backend/main.py` module init (call at the same place `configure_logging()` is called). Depends on T007.

### Static guardrail (depends on T016 wrapper existing)

- [X] T019 Implement `scripts/check-no-provider-sdk-imports.sh` per research §8: ripgrep regex `^(import|from)\s+(vertexai|google\.genai|google\.cloud\.aiplatform|anthropic|openai)([. ]|$)`, allowlist `app/backend/llm/_real_backend.py` and `app/backend/llm/_mock_backend.py`, exit 1 on any other match with the violation file:line in stderr. Make the script executable.
- [X] T020 Wire the `no-provider-sdk-imports` local hook into `.pre-commit-config.yaml` invoking `bash scripts/check-no-provider-sdk-imports.sh`, scoped to `^app/backend/.*\.py$`. Depends on T019.

### Shared test fixtures (depends on T011, T012, T013)

- [X] T021 Extend `app/backend/tests/conftest.py` with shared pytest fixtures: `mock_backend` (configured `MockVertexBackend` pointed at the test fixtures dir), `in_memory_trace_sink`, `in_memory_cost_ledger`, `sample_pricing` (loaded `PricingTable`), `sample_models_config` (loaded `ModelsConfig`), `test_settings` (a `Settings` instance with `llm_backend="mock"`). Depends on T007, T008, T009, T011, T012, T013.

**Checkpoint**: Foundation complete. The wrapper exists and is fully functional. The static guardrail blocks bypass. `app/backend/main.py` refuses to start in production-mock mode. `pricing.yaml` and `configs/models.yaml` ship with the documented entries. The mock backend can serve fixture-keyed responses. Each user story phase below adds tests that verify a specific FR slice.

---

## Phase 3: User Story 1 — Single sanctioned call path enforces hard §12 caps (Priority: P1) 🎯 MVP

**Goal**: Verify that the wrapper exposes one canonical async function, rejects out-of-cap requests before any network I/O, retries transient upstream failures within a 30-s wall-clock budget, and that the static guardrail blocks any module-level bypass attempt.

**Independent Test**: A backend engineer runs `pytest app/backend/tests/llm/test_vertex_wrapper.py -k "config or guardrail or retry"` plus `bash scripts/check-no-provider-sdk-imports.sh` and observes that all caps + guardrail behaviour is provably correct against the FR-002, FR-003, FR-004, FR-014 set.

### Implementation for User Story 1

- [X] T022 [P] [US1] Write `test_timeout_above_30s_rejected_at_construction` in `app/backend/tests/llm/test_vertex_wrapper.py`: assert `ModelCallRequest(timeout_s=31, ...)` raises `pydantic.ValidationError`; assert wrapper is never called. Maps to FR-002, FR-017b, SC-002.
- [X] T023 [P] [US1] Write `test_max_tokens_above_4096_rejected_at_construction` in `app/backend/tests/llm/test_vertex_wrapper.py`: assert `ModelCallRequest(max_output_tokens=4097, ...)` raises `pydantic.ValidationError`. Maps to FR-002, FR-017b, SC-002.
- [X] T024 [P] [US1] Write `test_unknown_agent_raises_config_error` in `app/backend/tests/llm/test_vertex_wrapper.py`: assert `ModelCallRequest(agent="unknown", ...)` is caught at the pydantic enum validator; the wrapper re-raises as `ModelCallConfigError`. Maps to FR-019.
- [X] T025 [P] [US1] Write `test_unknown_model_override_raises_config_error` in `app/backend/tests/llm/test_vertex_wrapper.py`: pass `model_override="gemini-no-such"`; assert `ModelCallConfigError` from the pricing-table lookup; assert no backend call happened. Maps to FR-010.
- [X] T026 [P] [US1] Write `test_retry_on_transient_then_succeeds` in `app/backend/tests/llm/test_vertex_wrapper.py`: configure mock backend to raise `google.api_core.exceptions.ServiceUnavailable` once, then return success; assert wrapper retries (attempts=2) and returns `ModelCallResult`. Maps to FR-004.
- [X] T027 [P] [US1] Write `test_retry_budget_exhausted_raises_upstream_unavailable` in `app/backend/tests/llm/test_vertex_wrapper.py`: configure mock to raise `ServiceUnavailable` 3 times; assert `VertexUpstreamUnavailableError`; assert `attempts == 3`. Maps to FR-004.
- [X] T028 [P] [US1] Write `test_deadline_exceeded_not_retried` in `app/backend/tests/llm/test_vertex_wrapper.py`: configure mock to raise `google.api_core.exceptions.DeadlineExceeded`; assert wrapper raises `VertexTimeoutError` immediately (no retry); assert `attempts == 1`. Maps to FR-004 + Clarifications 2026-04-26.
- [X] T029 [P] [US1] Write `test_invalid_argument_not_retried` in `app/backend/tests/llm/test_vertex_wrapper.py`: configure mock to raise `google.api_core.exceptions.InvalidArgument`; assert wrapper raises `ModelCallConfigError` (re-classified) immediately. Maps to FR-004.
- [X] T030 [P] [US1] Write `test_no_provider_sdk_imports.py` in `app/backend/tests/llm/`: invoke `scripts/check-no-provider-sdk-imports.sh` via `subprocess`; assert exit 0 on the post-T04 tree; create a tmp file `app/backend/services/_demo.py` with `import vertexai`, re-run the script, assert exit 1 with the violation in stderr; clean up the tmp file. Maps to FR-014, SC-003.

**Checkpoint**: User Story 1 complete. The wrapper is callable, caps are enforced, retries work, and the guardrail blocks bypass. **MVP-ready** — the wrapper would be deployable as the single sanctioned call path even without the additional verifications in US2-US5.

---

## Phase 4: User Story 2 — Local dev and CI run without real Vertex credentials (Priority: P1)

**Goal**: Verify that the mock backend works deterministically, that production refuses mock mode, and that the fixture-promotion flow is documented.

**Independent Test**: A reviewer runs `docker compose -f docker-compose.test.yml run --rm backend pytest app/backend/tests/llm/test_mock_backend.py app/backend/tests/test_settings.py -v` on a clone with **zero** GCP credentials configured and observes a green run.

### Implementation for User Story 2

- [X] T031 [P] [US2] Write `test_mock_backend.py` in `app/backend/tests/llm/`: assert `MockVertexBackend.generate(...)` with a known prompt returns the expected fixture content; assert SHA stability across two Python invocations (compute the SHA inline, compare to filename); assert that an unseen prompt writes `_unrecorded/<sha>.json` with the request envelope and raises `RuntimeError`; assert the canonical SHA includes the schema (changing only the schema produces a different SHA). Maps to FR-005, FR-006.
- [X] T032 [P] [US2] Write `test_settings.py` in `app/backend/tests/`: assert defaults load (`llm_backend == "mock"`, `app_env == "dev"`, etc.); assert `Settings(app_env="prod", llm_backend="mock").assert_safe_for_environment()` raises `RuntimeError` with FR-007 in the message; assert `Settings(app_env="prod", llm_backend="vertex", llm_budget_per_session_usd=Decimal("10"))` raises `RuntimeError` with §12 in the message; assert non-production settings with `llm_backend="mock"` are accepted. Maps to FR-005, FR-007, SC-010.
- [X] T033 [P] [US2] Write `test_successful_call_with_schema_returns_parsed_json` in `app/backend/tests/llm/test_vertex_wrapper.py`: end-to-end mock-mode call with a JSON schema; assert `result.parsed is not None`; assert `result.text` is the JSON-encoded payload; assert `result.input_tokens > 0` and `result.output_tokens > 0`; assert one trace record with `outcome="ok"`. Maps to FR-002, FR-005, FR-011, FR-017a.
- [X] T034 [US2] Author `app/backend/tests/fixtures/llm_responses/README.md` documenting the SHA-named fixture convention, the JSON envelope shape, the `_unrecorded` capture rule, and the manual promotion flow per [`contracts/wrapper-contract.md` §9](contracts/wrapper-contract.md). Depends on T015.

**Checkpoint**: User Story 2 complete. Mock mode works without GCP credentials; production refuses to start in mock mode; the fixture flow is documented for future test authors.

---

## Phase 5: User Story 3 — Every model call produces an audit-quality trace (Priority: P1)

**Goal**: Verify that exactly one trace record is produced for every wrapper invocation regardless of outcome, that the record carries the FR-008 field set, that the trace is written synchronously before the call returns, and that no log line carries prompt text / output text / PII.

**Independent Test**: A reviewer runs `pytest app/backend/tests/llm/test_vertex_wrapper.py -k "trace or log_event"` plus `pytest app/backend/tests/llm/test_trace_sink.py` and observes a green run.

### Implementation for User Story 3

- [X] T035 [P] [US3] Write `test_trace_sink.py` in `app/backend/tests/llm/`: assert `InMemoryTraceSink` accepts records up to capacity; assert `TraceWriteError` raised on capacity overflow; assert `records` property returns a defensive copy (mutating the returned list does not affect future writes). Maps to FR-009.
- [X] T036 [P] [US3] Write `test_trace_sink_failure_raises_trace_write_error` in `app/backend/tests/llm/test_vertex_wrapper.py`: inject a sink whose `write` always raises; perform a successful upstream call (mock backend OK); assert wrapper raises `TraceWriteError` and does NOT return a `ModelCallResult` (auditability §1 trumps the otherwise-OK response). Maps to FR-009 + Clarifications 2026-04-26.
- [X] T037 [P] [US3] Write `test_one_trace_per_invocation_in_every_scenario` in `app/backend/tests/llm/test_vertex_wrapper.py` parametrised over the seven outcomes (`ok`, `schema_error`, `timeout`, `upstream_unavailable`, `budget_exceeded`, `config_error`, `trace_write_error`); assert `len(sink.records) == 1` after each invocation; assert record's `outcome` field matches the parameter; assert all FR-008 fields are populated. Maps to FR-008, SC-004, SC-007.
- [X] T038 [P] [US3] Write `test_log_event_carries_no_prompt_text_no_pii` in `app/backend/tests/llm/test_vertex_wrapper.py`: capture log records (e.g. via `caplog` or a custom `structlog` test handler) during one wrapper invocation with `system_prompt="secret_marker_string"` + `user_payload="candidate@example.com asked: secret_marker_string"`; assert no log entry contains the marker string OR the email; assert exactly one `llm_call` event with the field set from research §15. Maps to FR-013, §15.
- [X] T039 [P] [US3] Write `test_canonical_prompt_sha_is_stable_and_includes_schema` in `app/backend/tests/llm/test_mock_backend.py`: invoke the SHA function twice with identical inputs → identical outputs; change only `json_schema` → different SHA; change only `model` → different SHA. Maps to research §13, FR-008.

**Checkpoint**: User Story 3 complete. Every wrapper invocation leaves exactly one append-only trace record. Sync-write semantics hold. Logs are PII-free.

---

## Phase 6: User Story 4 — Structured JSON output is schema-validated before the caller sees it (Priority: P2)

**Goal**: Verify that schema validation happens (Stage 2 in pydantic) and that on failure the wrapper raises immediately with the raw payload attached — NO wrapper-level retry, per Clarifications 2026-04-26.

**Independent Test**: A reviewer runs `pytest app/backend/tests/llm/test_vertex_wrapper.py -k schema_miss` and observes that the schema-error path is correct.

### Implementation for User Story 4

- [X] T040 [P] [US4] Write `test_schema_miss_raises_immediately_with_raw_payload` in `app/backend/tests/llm/test_vertex_wrapper.py`: configure the mock backend to return the deliberately schema-INVALID fixture (from T015) for the test prompt + schema; assert the wrapper raises `VertexSchemaError` on the **first** attempt (not after a retry); assert `attempts == 1` in the trace; assert `e.raw_payload` equals the broken JSON string the mock returned; assert one trace record with `outcome="schema_error"`. Maps to FR-011, FR-017c (per Clarifications), Spec User Story 4 Acceptance Scenario 2.
- [X] T041 [P] [US4] Write `test_no_schema_passes_text_through_unparsed` in `app/backend/tests/llm/test_vertex_wrapper.py`: invoke wrapper with `json_schema=None`; assert `result.parsed is None`; assert `result.text` is the mock's raw text; assert no schema-validation code path was exercised (no `VertexSchemaError` on a valid call). Maps to FR-011, Spec User Story 4 Acceptance Scenario 3.

**Checkpoint**: User Story 4 complete. Schema validation works correctly; agent modules (T18-T21) own their per-agent retry policies on top.

---

## Phase 7: User Story 5 — Per-session cost ceiling halts a runaway session (Priority: P2)

**Goal**: Verify that the wrapper consults the cost ledger before each call, refuses with `SessionBudgetExceeded` when the ceiling is hit, and increments the ledger on success.

**Independent Test**: A reviewer runs `pytest app/backend/tests/llm/test_cost_ledger.py app/backend/tests/llm/test_vertex_wrapper.py -k budget` and observes that budget enforcement is provably correct.

### Implementation for User Story 5

- [X] T042 [P] [US5] Write `test_cost_ledger.py` in `app/backend/tests/llm/`: assert `InMemoryCostLedger.session_total(unknown_session)` returns `Decimal("0")`; assert `add(session, Decimal("0.001"))` then `session_total(session)` returns `Decimal("0.001")`; assert concurrent `await asyncio.gather(*[ledger.add(session, Decimal("0.001")) for _ in range(100)])` produces a final total of `Decimal("0.100")` (atomicity); assert `add(session, Decimal("-1"))` raises `ValueError`. Maps to FR-012.
- [X] T043 [P] [US5] Write `test_session_at_budget_raises_before_backend_call` in `app/backend/tests/llm/test_vertex_wrapper.py`: seed the ledger with `Decimal("5.00")` for a session id; invoke wrapper with that session id; assert `SessionBudgetExceeded` raised; assert the mock backend was never called (use a sentinel that fails the test if `generate` runs); assert one trace record with `outcome="budget_exceeded"`, `cost_usd=Decimal("0")`, `input_tokens=0`, `output_tokens=0`. Maps to FR-012, FR-017d, SC-006.
- [X] T044 [P] [US5] Write `test_successful_call_increments_ledger_by_actual_cost` in `app/backend/tests/llm/test_vertex_wrapper.py`: start with empty ledger; invoke wrapper; assert ledger total after call equals `pricing.cost_for(model, result.input_tokens, result.output_tokens)`; assert `cost_usd > 0` in the trace record. Maps to FR-010, FR-012.
- [X] T045 [P] [US5] Write `test_failed_call_does_not_increment_ledger` in `app/backend/tests/llm/test_vertex_wrapper.py`: start with empty ledger; invoke wrapper such that it raises `VertexSchemaError` (use the broken fixture from T015); assert ledger total is still `Decimal("0")` after the call; assert one trace record with `cost_usd > 0` (Vertex still billed) but ledger NOT incremented (failure case — wrapper passes `Decimal("0")` to `ledger.add` per `contracts/wrapper-contract.md` §8). Maps to FR-008, FR-012.

**Checkpoint**: User Story 5 complete. Budget enforcement works at both directions: short-circuits before the call when ceiling hit, and increments only on success.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Documentation reconciliation, README updates, supporting unit tests for cross-cutting modules, and the final verification commands the reviewer runs from `quickstart.md`.

### Supporting test coverage (not story-specific)

- [X] T046 [P] Write `test_pricing.py` in `app/backend/tests/llm/`: assert `PricingTable.from_yaml(pricing.yaml)` loads both committed models; assert `cost_for("gemini-2.5-flash", 1000, 1000)` equals `Decimal("0.000075") + Decimal("0.000300") = Decimal("0.000375")`; assert `cost_for("unknown-model", ...)` raises `ModelCallConfigError`; assert non-positive prices in YAML fail at load time. Maps to FR-010.
- [X] T046b [P] Write `test_no_inline_credentials.py` in `app/backend/tests/llm/`: import `RealVertexBackend` from `app.backend.llm._real_backend` and `Settings` from `app.backend.settings`; for each class, walk `inspect.signature(cls.__init__).parameters` and assert that no parameter name appears in the forbidden set `{"credentials", "api_key", "key", "token", "service_account", "pem", "private_key", "google_application_credentials"}`. Test failure means a future PR has added a public surface for inline credentials, violating FR-015 / ADR-013 / constitution §5–§6. Maps to FR-015 (per analysis finding C1 — closes the structural-test gap so the invariant is enforced at `pytest run`, not only at code review).
- [X] T047 [P] Write `test_models_config.py` in `app/backend/tests/llm/`: assert `ModelsConfig.from_yaml(configs/models.yaml)` loads all three agents; assert `for_agent("interviewer")` returns the expected `ModelConfig` with `model="gemini-2.5-flash"` and `prompt_version="v0001"`; assert `for_agent("unknown")` raises `ModelCallConfigError`; assert a YAML missing one agent fails at load time; assert out-of-range temperature fails at load time. Maps to FR-019.

### Documentation reconciliation (per Clarifications 2026-04-26)

- [X] T048 [P] Edit `docs/engineering/implementation-plan.md` T04 acceptance bullet: replace "schema miss retries then raises VertexSchemaError" with "schema miss raises VertexSchemaError immediately; per-agent retry policies live in agent modules". Add a one-line note pointing at `specs/007-t04-vertex-client-wrapper/spec.md` Clarifications 2026-04-26.
- [X] T049 [P] Edit `docs/engineering/vertex-integration.md` "Retry policy" section: replace the per-error-type table with a uniform 3-attempt policy table (`ServiceUnavailable`, `InternalServerError`, `ResourceExhausted`, `ConnectionError` → 3 attempts; `DeadlineExceeded` → no retry; `InvalidArgument` / `PermissionDenied` → no retry). Add a one-line note pointing at the spec's Clarifications.

### README and developer-facing docs

- [X] T050 [P] Add a "Vertex wrapper" subsection under the existing "Backend dev loop" section of `README.md`: link to `app/backend/llm/`, document the canonical call path (`from app.backend.llm import call_model`), document the mock-mode default in dev/CI, document where fixtures live and the `_unrecorded` promotion flow, document the production-mode startup refusal.

### Final verification (sequential — depend on the entire test suite passing)

- [X] T051 Run `docker compose -f docker-compose.test.yml run --rm backend pytest -v` and confirm: total wall-time < 60 s (SC-005), all FR-017 matrix tests pass, no new test takes longer than 5 s individually.
- [X] T052 Run `docker compose -f docker-compose.test.yml run --rm backend ruff check app/backend && mypy --strict app/backend/llm` and confirm zero diagnostics (SC-008).
- [X] T053 Run `docker compose -f docker-compose.test.yml run --rm backend python -m app.backend.generate_openapi && git diff --exit-code app/backend/openapi.yaml` and confirm exit 0 — wrapper introduces no HTTP route, OpenAPI is byte-identical (FR-018, SC-009).
- [X] T054 Run the 8-step `quickstart.md` walkthrough end-to-end and check every box in its acceptance checklist.

**Checkpoint**: T04 complete. All five user stories independently verifiable; FR-017 matrix landed as 10 named tests; documentation reconciled; reviewer-facing quickstart green.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately.
- **Foundational (Phase 2)**: Depends on Setup (the deps and package layout exist). BLOCKS all user stories.
- **User Stories (Phases 3–7)**: All depend on Foundational. Once Foundational lands, the five user stories can in principle be worked in parallel by separate test-authors (each story owns disjoint test files except for `test_vertex_wrapper.py`, which is shared but each story owns disjoint test functions within it).
- **Polish (Phase 8)**: Depends on all user stories being complete (the verification commands in T051-T054 require the full test suite + every implementation to be in place).

### User Story Dependencies

- **US1 (P1, MVP)**: Caps + retry + guardrail tests. Independent.
- **US2 (P1)**: Mock-backend + production-refusal tests. Independent of US1's tests but uses the same wrapper.
- **US3 (P1)**: Trace tests. Independent.
- **US4 (P2)**: Schema validation tests. Independent.
- **US5 (P2)**: Cost ledger + budget tests. Independent.

All five stories share the same `test_vertex_wrapper.py` file but operate on disjoint test functions; if two test-authors edit the same file in parallel, a clean merge is straightforward.

### Within Each User Story

- All tests within a story are independent and can be written in parallel ([P] marked).
- Each test exercises an already-implemented behaviour from the foundational phase — there are no models/services/endpoints to build inside the story phases.

### Parallel Opportunities

- **Within Setup**: T002, T003, T004, T005 all `[P]` — distinct files.
- **Within Foundational support modules**: T006–T012 all `[P]` — seven distinct files with no cross-deps.
- **Foundational backends**: T013 and T014 are sequential after T006/T010 (both depend on errors and protocol) but can run in parallel with each other once those land.
- **Foundational fixtures + wrapper**: T015 (fixtures) depends on T013 (mock backend defines the SHA recipe). T016 (wrapper) depends on everything else. T017 depends on T016. T018 depends on T007. T019 (script) and T020 (pre-commit hook) sequential. T021 (conftest) parallel with the wrapper if the conftest imports happen after the modules exist.
- **Across user stories**: All test-writing tasks in Phases 3–7 are `[P]`-able **as long as the test functions live in different functions of `test_vertex_wrapper.py` and adjacent test files** — they don't share state.
- **Polish T046, T047, T048, T049, T050** are all `[P]` — distinct files.

---

## Parallel Example: User Story 1 (the MVP)

```bash
# After Foundational completes, all US1 tests can be written in parallel:
Task: "T022 Write test_timeout_above_30s_rejected_at_construction"
Task: "T023 Write test_max_tokens_above_4096_rejected_at_construction"
Task: "T024 Write test_unknown_agent_raises_config_error"
Task: "T025 Write test_unknown_model_override_raises_config_error"
Task: "T026 Write test_retry_on_transient_then_succeeds"
Task: "T027 Write test_retry_budget_exhausted_raises_upstream_unavailable"
Task: "T028 Write test_deadline_exceeded_not_retried"
Task: "T029 Write test_invalid_argument_not_retried"
Task: "T030 Write test_no_provider_sdk_imports.py"
```

All nine tests live in different functions / files; merge friction is minimal.

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (this is the bulk of the implementation work).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: Run the US1 test slice. The wrapper is callable, caps are enforced, the static guardrail blocks bypass.
5. T04 is **MVP-deployable** at this point — every later LLM-touching task could in theory consume the wrapper as-is. US2-US5 add proof of additional FRs but the wrapper code is already complete.

### Incremental Delivery

1. Complete Setup + Foundational → wrapper exists and works.
2. Add US1 → caps + guardrail tests pass.
3. Add US2 → mock + production-refusal tests pass.
4. Add US3 → trace tests pass.
5. Add US4 → schema-validation tests pass.
6. Add US5 → budget tests pass.
7. Add Polish → docs reconciled, README updated, final verification clean.

For T04, this incremental delivery happens **inside one PR** (single committer, single agent). The phasing is for reviewer ergonomics — a reviewer can scan story-by-story and tick off the FR slice.

### Single-Agent Strategy (T04 default)

`agent: backend-engineer`, `parallel: false` for T04 itself. One developer / sub-agent works through Phase 1 → Phase 8 sequentially, taking advantage of `[P]` markers where the file boundary makes parallelism honest (e.g., banging out the seven Foundational support modules as a small batch). The PR lands as one cohesive change for reviewer focus.

The parallel fan-out T04 enables happens **after** T04 merges, on T17–T21.

---

## Notes

- `[P]` tasks = different files, no dependencies.
- `[Story]` label maps each test task to the FR it verifies for traceability.
- The Foundational phase is intentionally large for T04 because the wrapper is one cohesive piece of code that wouldn't naturally split across user-story phases. User-story phases own their **test slices** rather than independent implementation slices.
- Verify each test fails before the corresponding implementation is in place (TDD discipline) — for T04 the implementation is in Foundational, so tests can be written immediately after the corresponding foundation task lands.
- Commit after each task or logical group (a single foundational module + its checkpoint, an entire user-story phase, etc.). The project convention `auto_commit: false` means no Spec Kit hook will commit for you.
- Stop at Phase 3's checkpoint to validate MVP independently if you want a halfway-deployable wrapper; otherwise carry through to Phase 8 in one sitting.
- The wrapper file `app/backend/llm/vertex.py` is touched by exactly one task (T016). Tests touching it (T022-T029, T033, T036-T041, T043-T045) only add new test functions, so the wrapper is not re-edited by user-story phases.
