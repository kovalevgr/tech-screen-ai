# Implementation Plan: Vertex AI Client Wrapper (T04)

**Branch**: `007-t04-vertex-client-wrapper` | **Date**: 2026-04-26 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/007-t04-vertex-client-wrapper/spec.md`

## Summary

T04 introduces the **single sanctioned doorway** for every LLM token in the system. It lands eight things in one PR, in the order a reviewer should validate them:

1. The wrapper module at `app/backend/llm/vertex.py` — async, exposes one primary `call_model(...)` coroutine, enforces constitution §12 caps (≤30 s timeout, ≤4096 max output tokens), retries transient upstream failures with a uniform 3-attempt budget, validates JSON output against caller-supplied schemas, consults an injected per-session cost ledger, and writes a trace record synchronously before returning.
2. The typed call surface (Pydantic models + the wrapper-error class hierarchy): `ModelCallRequest`, `ModelCallResult`, `TraceRecord`, plus six typed errors — `ModelCallConfigError`, `VertexTimeoutError`, `VertexUpstreamUnavailableError`, `VertexSchemaError`, `SessionBudgetExceeded`, `TraceWriteError`.
3. Two **injectable interfaces** with in-memory implementations: `TraceSink` (append-only, records every call attempt's terminal state) and `CostLedger` (per-session running USD total). The durable database-backed implementations land in T05; T04 ships the in-memory ones so the wrapper is exercisable end-to-end without a DB.
4. The **mock backend** at `app/backend/llm/_mock_backend.py` — deterministic, keyed by SHA-256 of the canonicalised prompt content. Fixtures under `app/backend/tests/fixtures/llm_responses/<agent>/<prompt-sha>.json`. Unseen prompts are captured under `app/backend/tests/fixtures/llm_responses/_unrecorded/` and the call raises a clear test-time error.
5. **Configs as code** (constitution §16):
   - `app/backend/llm/pricing.yaml` — committed price table for Gemini 2.5 Flash and Gemini 2.5 Pro in `europe-west1` (per ADR-003 / ADR-015).
   - `configs/models.yaml` — agent → model + prompt_version + temperature + max_output_tokens map for `interviewer`, `assessor`, `planner` (per Clarifications 2026-04-26 the `prompt_version` is the placeholder string `"v0001"`; T17 later replaces with real prompt content under `prompts/<agent>/v0001/`).
6. The **static guardrail** that refuses any commit which imports a model-provider SDK (`vertexai`, `google.genai`, `google-cloud-aiplatform`, `anthropic`, `openai`) from a module other than `app/backend/llm/vertex.py` and `app/backend/llm/_mock_backend.py`. Implemented as a shell-based pre-commit hook + a CI step running the same script (mirrors the T03 visual-discipline pattern).
7. The backend `Settings` extension introducing `LLM_BACKEND` (`mock` default for non-production, mandatory `vertex` for production). It also reads the pre-existing `APP_ENV` env var (already set by `Dockerfile` and every `docker-compose*.yml`) so the production-mode guard fires under the existing infra wiring without requiring a new env var. The startup check in `app/backend/main.py` refuses to boot when `APP_ENV=prod` and `LLM_BACKEND=mock`.
8. A **documentation-fix slice** that reconciles two older docs to the spec's clarified policies (per Clarifications 2026-04-26):
   - `docs/engineering/implementation-plan.md` T04 acceptance: "schema miss retries then raises" → "schema miss raises immediately; per-agent retry policies live in agent modules".
   - `docs/engineering/vertex-integration.md` retry table (per-error-type counts) → uniform 3-attempt budget excluding `DeadlineExceeded`.

The PR adds **no** Alembic migration, **no** HTTP endpoint (the wrapper is internal), **no** OpenAPI diff (`app/backend/openapi.yaml` is byte-identical before/after — the existing T02 regen-and-diff guardrail keeps us honest), **no** authentication middleware, and **no** content under `prompts/`.

## Technical Context

**Language/Version**: Python 3.12 (matches T01/T02 baseline pinned by `pyproject.toml` `requires-python = ">=3.12,<3.13"`). No new language requirement.

**Primary Dependencies** (added to `pyproject.toml` `[project].dependencies`):

- `google-genai >= 0.5, < 1` — Google's **new** generative SDK (the successor to the `google-cloud-aiplatform`-only path) which provides a first-class `aio.generate_content` async coroutine and Vertex-mode credentials via Application Default Credentials. The single-SDK choice keeps the wrapper compact and mirrors `vertex-integration.md`'s "single adapter module" intent. Research §1 documents the alternative considered (`google-cloud-aiplatform` direct) and rejected.
- `tenacity >= 9.0, < 10` — retry primitives with exponential backoff and jitter; the implementation-plan T04 description names this library by name. Research §2.
- `pydantic-settings >= 2.6, < 3` — the canonical successor to Pydantic v1's `BaseSettings`. Used to construct the slim `Settings` class introduced in this PR (`LLM_BACKEND`, `APP_ENV`, `LLM_BUDGET_PER_SESSION_USD`, `LLM_FIXTURES_DIR`). Pydantic itself is already pulled in transitively by FastAPI.

`pyyaml` (already present from T02) is reused to load `pricing.yaml` and `configs/models.yaml`. `httpx` (already a `dev` dep) is unused at runtime — the SDK manages its own transport.

**Dev dependencies** (added to `pyproject.toml` `[dependency-groups].dev`):

- `pytest-asyncio >= 0.23, < 1` — `asyncio_mode = "auto"` in `[tool.pytest.ini_options]`. Lets `async def test_*` functions run without `@pytest.mark.asyncio`. Research §3 evaluates `anyio` plugin as alternative; `pytest-asyncio` wins on simpler config and the larger ecosystem.

No new top-level dependency on `jsonschema` or any other JSON-validation library: the spec's `json_schema` parameter is **a Python dict that maps to Vertex's `response_schema`**, and validation of the parsed payload is done by `pydantic.TypeAdapter` against a Pydantic model the caller passes (or, when callers pass a raw dict schema, by the SDK's own structured-output validation). Research §4.

**Storage**: N/A at T04 runtime. The `TraceSink` and `CostLedger` interfaces are in-memory at T04 (correct for single-process, single-event-loop tests). Durable Postgres-backed implementations land with T05 (DB schema baseline). The wrapper has zero direct DB imports — FR-009.

**Testing**: `pytest` ≥ 8.3 (already in T02 dev deps) + `pytest-asyncio` for async test methods. Tests live under `app/backend/tests/llm/`:

- `test_vertex_wrapper.py` — the FR-017 matrix: success-with-schema, config-violations, schema-miss, budget-exceeded, trace-record-per-scenario.
- `test_pricing.py` — price-table loader; unknown-model raises `ModelCallConfigError`.
- `test_models_config.py` — `configs/models.yaml` loader; agent resolution; missing-agent error.
- `test_mock_backend.py` — fixture loading, prompt-SHA keying, unseen-prompt capture.
- `test_trace_sink.py` — in-memory trace sink contract; sink failure → `TraceWriteError`.
- `test_cost_ledger.py` — in-memory ledger contract; budget-exceeded short-circuit.
- `test_no_provider_sdk_imports.py` — the static guardrail's positive-and-negative paths (the same script the pre-commit hook runs, invoked from a test).
- `test_settings.py` — the production-mode + mock-backend startup refusal (FR-007 / SC-010).

The fixture directory `app/backend/tests/fixtures/llm_responses/` ships the smallest possible set: one fixture per agent that produces a schema-valid output, plus one deliberately-invalid fixture used by the schema-miss test.

**Target Platform**: Linux container (Python 3.12-slim, the same image as T02). The wrapper has no platform-specific dependencies; mock mode uses no network. Production resolves Application Default Credentials to a Workload-Identity-Federation principal injected by Cloud Run (constitution §6, ADR-013) — that wiring lives in T06, not T04.

**Project Type**: Backend library slice within the existing FastAPI monorepo. No frontend changes. No infra changes (Dockerfile/compose updates wait for T06/T09 and use the existing image).

**Performance Goals**:

- Wrapper trace-write overhead (in-memory sink): < 1 ms p95, measured with `perf_counter` in a micro-benchmark inside the test suite. (Sanity check, not a Spec SC.)
- Backend test suite (post-T04, including all new T04 tests + T02's existing tests) wall time: < 60 s on a clean tree without GCP credentials (this is SC-005 from the spec).
- `ruff check app/backend` and `mypy --strict app/backend/llm` each exit zero in < 10 s on the post-T04 tree (extends SC-008 to a concrete time budget).
- The wrapper itself imposes zero per-call latency overhead beyond: prompt SHA computation (negligible, < 0.1 ms for 4 KB prompts), pricing-table lookup (O(1) hash), trace-record build (< 0.1 ms), and the synchronous sink write (< 1 ms in-memory, < 20 ms expected for the future durable sink).

**Constraints**:

- **§12 Hard caps** — wrapper rejects any caller-supplied `timeout_s > 30` or `max_output_tokens > 4096` at the Pydantic validation layer (`Field(le=30)`, `Field(le=4096)`) — i.e., before the call function even runs. FR-002.
- **§1 Auditability** — sync trace write is non-negotiable per the Clarifications 2026-04-26 decision. The wrapper raises `TraceWriteError` on sink failure rather than swallowing.
- **§5 / §6 / ADR-013 — secrets** — wrapper authenticates via Application Default Credentials only. No JSON service-account key is read or accepted as a parameter. `.env.example` gains no new key (the `LLM_BACKEND`, `LLM_BUDGET_PER_SESSION_USD`, `LLM_FIXTURES_DIR` are non-secret; per ADR-022 they may carry non-secret defaults in `.env.example`). `APP_ENV` was already present from T01.
- **§14 Contract-first** — the `ModelCallRequest`/`ModelCallResult`/`TraceRecord` Pydantic surface and the per-agent JSON-schema contract are committed in this PR before any consumer (T17–T21) lands. Documented in `contracts/wrapper-contract.md`.
- **§15 PII containment** — wrapper logs only `trace_id` plus non-PII metadata; raw prompt text never appears in any log line. The wrapper reuses the project structlog pipeline configured in T02 (`pii_redaction_processor` already strips `candidate_email` and email-shaped substrings), and adds zero log calls that could carry candidate text.
- **§16 Configs as code** — `pricing.yaml`, `configs/models.yaml` ship versioned in Git; the wrapper rejects any unknown model identifier rather than silently defaulting.
- **§7 Docker parity** — the wrapper runs **identically** in dev (`docker compose up backend` with `LLM_BACKEND=mock`), CI (the same compose file), and prod (`LLM_BACKEND=vertex`). The selection is a runtime env var, not a build-time flag. T04 adds no new Docker stage.
- **No OpenAPI diff** (FR-018) — the wrapper exposes no HTTP route. The T02 `python -m app.backend.generate_openapi` regen-and-diff guardrail must continue to pass with zero diff.
- **`mypy --strict` clean** (FR-016) — every public symbol in `app/backend/llm/` has a complete type. The Pydantic models give us most of this for free.
- **Pre-commit guardrails from T01/T02** — `gitleaks`, `detect-secrets`, `ruff`, `ruff-format`, `actionlint`, `check-yaml`, `check-toml` all pass on every T04-introduced file. T04 only **adds** one new local hook (`no-provider-sdk-imports`); never weakens existing ones.

**Scale/Scope**: Single PR, ≈ 25 new files (≈ 700 LOC source + ≈ 600 LOC tests + 2 YAML configs + 4 fixture files + 1 guardrail script + 2 doc-fix edits). One committer (`agent: backend-engineer`). No sub-agent fan-out from inside T04 — the fan-out T04 enables happens afterwards on T17 (prompt artefacts), T18 (Interviewer service), T19 (Assessor service), T20 (orchestrator), T21 (Planner service), T11 (Tier-1 deploy gate's `/debug/vertex-ping`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

T04 lands the constitution's most consequential single piece of code: the place where every LLM token in the project flows through. Every invariant below is either satisfied by design (most of them) or out-of-scope (those involving DB tables, screens, or deploy mechanics that are later tasks).

| §   | Principle                              | Applies to T04?                                                                                                                                                                                                                                                                                | Status |
| --- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| 1   | Candidates and reviewers come first    | Directly — sync trace write per call is the *foundation* of every later auditability claim. The clarification 2026-04-26 (sync trace + `TraceWriteError` halts session) explicitly chose §1 over latency.                                                                                       | Pass   |
| 2   | Deterministic orchestration            | Indirectly — the wrapper supports §2 by enforcing JSON-schema validation on structured calls (FR-011), so the orchestrator (T20) can route on typed JSON fields rather than free text. The wrapper itself does no routing.                                                                       | Pass   |
| 3   | Append-only audit trail                | Indirect — `TraceRecord` is designed to be append-only-compatible (no `id` mutation, no `update_*` field), so when T05 lands the durable sink the same record shape works. T04 adds no DB tables.                                                                                                  | Pass   |
| 4   | Immutable rubric snapshots             | N/A — no rubric code.                                                                                                                                                                                                                                                                            | N/A    |
| 5   | No plaintext secrets                   | Yes — `gitleaks`/`detect-secrets` pass on every new file. ADC only; FR-015 forbids any inline credential parameter. `.env.example` gains three non-secret keys (`LLM_BACKEND=mock`, `LLM_BUDGET_PER_SESSION_USD=5.00`, `LLM_FIXTURES_DIR=app/backend/tests/fixtures/llm_responses`); the existing `APP_ENV=dev` from T01 is reused. | Pass   |
| 6   | Workload Identity Federation only      | Yes — ADC at runtime resolves to the WIF principal in production (T06's wiring); locally ADC resolves to the developer's `gcloud auth application-default login` identity, which is exempt from the §6 rule about JSON keys. No SA JSON keys touched.                                            | Pass   |
| 7   | Docker parity dev → CI → prod          | Yes — the wrapper runs the same code path everywhere; backend selection is runtime env-var (`LLM_BACKEND`). No new Docker stage; existing `Dockerfile` reused.                                                                                                                                  | Pass   |
| 8   | Production-only topology               | N/A — no deploy in T04.                                                                                                                                                                                                                                                                          | N/A    |
| 9   | Dark launch by default                 | Indirect — the wrapper itself is not user-visible. Consumers (T18–T21) ship behind feature flags per their own scope. T11 calls the wrapper via `/debug/vertex-ping` which is gated and removed before that tier's PR closes (per the T11 task description).                                      | Pass   |
| 10  | Migration approval                     | N/A — no Alembic migration in T04 (FR-018).                                                                                                                                                                                                                                                       | N/A    |
| 11  | Hybrid language                        | Indirect — wrapper passes prompt text through unchanged (English instructions / Ukrainian candidate output is the agent module's contract, T17–T21). Wrapper logs are English (constitution requires English log/code/comment language).                                                          | Pass   |
| 12  | LLM cost and latency caps              | **This is T04's primary purpose.** §12 is enforced by Pydantic validation (`timeout_s ≤ 30`, `max_output_tokens ≤ 4096`), the 30-s wall-clock budget across retries (FR-003), the `SessionBudgetExceeded` short-circuit (FR-012), and the trace record's `cost_usd` field (FR-008).                | Pass   |
| 13  | Calibration never blocks merge         | N/A — no calibration in T04. The future calibration runner (the `calibration-run` skill) consumes the wrapper.                                                                                                                                                                                    | N/A    |
| 14  | Contract-first for parallel work       | Yes — the wrapper's typed call surface (`ModelCallRequest`/`ModelCallResult`/`TraceRecord` Pydantic models) and the `configs/models.yaml` schema are the contract that T17–T21 fan out against. Committed in this PR; documented in `contracts/wrapper-contract.md`.                              | Pass   |
| 15  | PII containment                        | Yes — wrapper logs only `trace_id` and non-PII metadata; raw prompt text and raw model output never appear in log lines. Reuses the T02 `pii_redaction_processor`. Fixtures under `app/backend/tests/fixtures/llm_responses/` use synthetic, non-PII content (`"What is recursion?"` style).        | Pass   |
| 16  | Configs as code                        | Yes — `pricing.yaml` and `configs/models.yaml` ship in Git as the source of truth. The wrapper rejects any unknown model identifier rather than silently defaulting.                                                                                                                              | Pass   |
| 17  | Specifications precede implementation  | Yes — `/speckit-specify` produced `spec.md`; `/speckit-clarify` resolved 5 high-impact ambiguities; this `/speckit-plan` produces the artefacts before any source code is written.                                                                                                              | Pass   |
| 18  | Multi-agent orchestration is explicit  | Yes — plan declares `agent: backend-engineer`, `parallel: false` for T04 itself (single-committer PR; the parallelism this PR enables happens *after* T04 lands, on T17–T21).                                                                                                                       | Pass   |
| 19  | Rollback is a first-class operation    | Indirect — T04 introduces no production state, so `git revert` is sufficient. The runtime `LLM_BACKEND=mock` switch also acts as a kill-switch when paired with a feature flag in T18+.                                                                                                            | Pass   |
| 20  | Floor, not ceiling                     | Pass.                                                                                                                                                                                                                                                                                            | Pass   |

**Gate result**: PASS. No violations. Complexity Tracking stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-t04-vertex-client-wrapper/
├── spec.md                            # Feature spec (written in /speckit-specify, clarified in /speckit-clarify)
├── plan.md                            # This file
├── research.md                        # Phase 0 — design-altitude decisions
├── data-model.md                      # Phase 1 — typed entities (Pydantic models, interfaces, error hierarchy)
├── contracts/
│   └── wrapper-contract.md            # Phase 1 — wrapper API surface, fixture format, trace schema, models.yaml schema
├── quickstart.md                      # Phase 1 — reviewer-facing validation walkthrough
├── checklists/
│   └── requirements.md                # From /speckit-specify (passed)
└── tasks.md                           # Created by /speckit-tasks (NOT this command)
```

### Source Code (repository root, after T04 merges)

Every bold/`NEW`/`EDITED` entry is touched by T04. Pre-existing files (from T01/T02/T03) are untouched unless explicitly marked.

```text
.
├── app/
│   └── backend/
│       ├── __init__.py                              # untouched
│       ├── main.py                                  # EDITED — call new `Settings.assert_safe_for_environment()` from module init; no route changes
│       ├── settings.py                              # NEW — slim pydantic-settings `Settings` class: LLM_BACKEND, APP_ENV (already set by Dockerfile/compose), LLM_BUDGET_PER_SESSION_USD, LLM_FIXTURES_DIR; production+mock = startup error
│       ├── logging.py                               # untouched (T02's pii_redaction_processor reused)
│       ├── generate_openapi.py                      # untouched
│       ├── openapi.yaml                             # untouched (FR-018: byte-identical)
│       ├── llm/
│       │   ├── __init__.py                          # NEW — public re-exports: call_model, ModelCallRequest, ModelCallResult, errors
│       │   ├── vertex.py                            # NEW — the wrapper: `async def call_model(...)`, retry orchestration, sync trace write, cost ledger consult
│       │   ├── _real_backend.py                     # NEW — `google-genai` async wrapper; only module besides _mock_backend.py allowed to import the SDK
│       │   ├── _mock_backend.py                     # NEW — fixture-keyed deterministic stub; SHA-256 of canonicalised prompt content; "_unrecorded" capture
│       │   ├── _backend_protocol.py                 # NEW — `class VertexBackend(Protocol)` — the shape both _real and _mock implement
│       │   ├── errors.py                            # NEW — typed error hierarchy (see data-model.md)
│       │   ├── pricing.py                           # NEW — pricing.yaml loader + per-call cost computation (Decimal)
│       │   ├── pricing.yaml                         # NEW — Gemini 2.5 Flash + Pro for europe-west1 (per ADR-003 / ADR-015)
│       │   ├── models_config.py                     # NEW — configs/models.yaml loader; agent → ModelConfig resolution
│       │   ├── trace.py                             # NEW — `TraceRecord` Pydantic model + `TraceSink` Protocol + `InMemoryTraceSink` impl
│       │   └── cost_ledger.py                       # NEW — `CostLedger` Protocol + `InMemoryCostLedger` impl + budget-exceeded check
│       └── tests/
│           ├── conftest.py                          # EDITED — add fixtures: mock_backend, in_memory_trace_sink, in_memory_cost_ledger, sample_pricing, sample_models_config
│           ├── test_health.py                       # untouched
│           ├── test_logging_pii.py                  # untouched
│           ├── test_openapi_regeneration.py         # untouched
│           ├── test_settings.py                     # NEW — Settings env-load + production+mock startup refusal (FR-007 / SC-010)
│           ├── llm/
│           │   ├── __init__.py                      # NEW — empty package marker
│           │   ├── test_vertex_wrapper.py           # NEW — FR-017 matrix (success, config violations, schema miss, budget exceeded, trace per scenario)
│           │   ├── test_pricing.py                  # NEW — pricing.yaml loader tests; unknown-model error
│           │   ├── test_models_config.py            # NEW — models.yaml loader tests
│           │   ├── test_mock_backend.py             # NEW — fixture loading, prompt-SHA stability, unseen capture
│           │   ├── test_trace_sink.py               # NEW — in-memory sink contract; sink failure path
│           │   ├── test_cost_ledger.py              # NEW — ledger arithmetic, budget short-circuit
│           │   └── test_no_provider_sdk_imports.py  # NEW — runs the same script the pre-commit hook runs, asserts pass on the tree, fail on a fixture violation
│           └── fixtures/
│               └── llm_responses/
│                   ├── README.md                    # NEW — explains the prompt-SHA naming convention and the _unrecorded promotion flow
│                   ├── interviewer/
│                   │   └── <sha256-of-canonical-test-prompt>.json    # NEW — schema-valid sample
│                   ├── assessor/
│                   │   ├── <sha256-of-canonical-test-prompt>.json    # NEW — schema-valid sample
│                   │   └── <sha256-of-broken-prompt>.json            # NEW — deliberately schema-INVALID for the schema-miss test
│                   ├── planner/
│                   │   └── <sha256-of-canonical-test-prompt>.json    # NEW — schema-valid sample
│                   └── _unrecorded/                # NEW (gitkeep) — directory exists; populated at test time when an unseen prompt SHA arrives
│                       └── .gitkeep                 # NEW
├── configs/
│   └── models.yaml                                  # NEW — interviewer/assessor/planner → model + prompt_version + temperature + max_output_tokens
├── scripts/
│   └── check-no-provider-sdk-imports.sh             # NEW — ripgrep-backed guardrail; pre-commit hook + CI step both invoke this
├── docs/
│   └── engineering/
│       ├── implementation-plan.md                   # EDITED — T04 acceptance: "schema miss raises VertexSchemaError" (was "schema miss retries then raises")
│       └── vertex-integration.md                    # EDITED — Retry policy section: uniform 3-attempt budget; DeadlineExceeded excluded; per-error-type table replaced by uniform table
├── pyproject.toml                                   # EDITED — add `google-genai`, `tenacity`, `pydantic-settings` to [project].dependencies; add `pytest-asyncio` to [dependency-groups].dev; add `[tool.pytest.ini_options].asyncio_mode = "auto"`
├── uv.lock                                          # EDITED — regenerated by `uv lock` after pyproject.toml edits
├── .env.example                                     # EDITED — add LLM_BACKEND=mock, LLM_BUDGET_PER_SESSION_USD=5.00, LLM_FIXTURES_DIR=app/backend/tests/fixtures/llm_responses (all non-secret per ADR-022); APP_ENV is already present from T01 and is read by Settings unchanged
├── .pre-commit-config.yaml                          # EDITED — add one local hook: `no-provider-sdk-imports` invoking scripts/check-no-provider-sdk-imports.sh
├── README.md                                        # EDITED — "Vertex wrapper" subsection under Backend dev loop: how to run mock-mode tests, where fixtures live, how to add a new fixture
└── (every other path untouched)
```

**Structure Decision**: Backend slice only, contained under `app/backend/llm/` (new package) plus a small `app/backend/settings.py` introduction, the new top-level `configs/` directory (constitution §16), one shell script under `scripts/`, two doc-fixes under `docs/engineering/`, and the necessary `pyproject.toml` / `.env.example` / `.pre-commit-config.yaml` / `README.md` edits. The wrapper module layout follows the deliberate convention `vertex.py` (public surface) + `_real_backend.py` + `_mock_backend.py` (private leaves; underscore-prefixed) + `_backend_protocol.py` (shared shape). The protocol module's underscore is **load-bearing**: the SDK-import guardrail allows imports of `vertexai` / `google.genai` only from `_real_backend.py` (and tests' mock-backend internals from `_mock_backend.py`); naming any of these without the underscore would invite call sites to import from them directly.

**Tests live alongside code under `app/backend/tests/llm/`**, mirroring the existing `app/backend/tests/test_*.py` pattern from T02. The `fixtures/llm_responses/` directory uses the same naming convention as `vertex-integration.md`'s mock description.

**Single committer**: `agent: backend-engineer`, `parallel: false` for T04 itself. T04 unblocks downstream `parallel: true` fan-out on T17 (prompt artefacts), T18 (Interviewer service), T19 (Assessor service), T20 (orchestrator), T21 (Planner service).

### Task labelling (for §18 / `/speckit-tasks`)

| Task slice                                           | Agent              | Parallel? | Depends on                                                                | Contract reference                                                                |
| ---------------------------------------------------- | ------------------ | --------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `pyproject.toml` deps + `uv lock`                    | `backend-engineer` | false     | T01 (`pyproject.toml` exists)                                            | `wrapper-contract.md` §0 (dependency budget)                                       |
| `Settings` class + production+mock startup check     | `backend-engineer` | false     | deps installed                                                           | `wrapper-contract.md` §6 (env contract)                                            |
| `errors.py` typed exception hierarchy                | `backend-engineer` | false     | nothing (pure types)                                                     | `wrapper-contract.md` §3 (error contract)                                          |
| `pricing.yaml` + `pricing.py` loader                 | `backend-engineer` | false     | nothing (data + parser)                                                  | `wrapper-contract.md` §5 (pricing contract)                                        |
| `configs/models.yaml` + `models_config.py` loader    | `backend-engineer` | false     | nothing (data + parser)                                                  | `wrapper-contract.md` §4 (models.yaml contract)                                    |
| `trace.py` (`TraceRecord` + `TraceSink` + in-memory) | `backend-engineer` | false     | `errors.py`                                                              | `wrapper-contract.md` §7 (trace contract)                                          |
| `cost_ledger.py` (`CostLedger` + in-memory)          | `backend-engineer` | false     | `errors.py`                                                              | `wrapper-contract.md` §8 (cost-ledger contract)                                    |
| `_backend_protocol.py` + `_mock_backend.py`          | `backend-engineer` | false     | `errors.py`, fixtures committed                                          | `wrapper-contract.md` §2 (backend protocol) + §9 (mock fixture format)             |
| `_real_backend.py` (google-genai async)              | `backend-engineer` | false     | `_backend_protocol.py`                                                   | `wrapper-contract.md` §2                                                            |
| `vertex.py` (`call_model` orchestration)             | `backend-engineer` | false     | all the above                                                            | `wrapper-contract.md` §1 (public call surface)                                     |
| Test suite (`app/backend/tests/llm/*`)               | `backend-engineer` | false     | `vertex.py`                                                              | `wrapper-contract.md` §10 (test matrix)                                            |
| Static guardrail script + pre-commit hook            | `backend-engineer` | false     | `vertex.py` (so the allowlist has scope)                                 | `wrapper-contract.md` §11 (guardrail contract)                                     |
| Documentation-fix (implementation-plan + integration) | `backend-engineer` | false     | spec/plan committed (so the new wording is anchored)                     | n/a (in-PR clarification)                                                          |
| `.env.example` + `README.md` updates                 | `backend-engineer` | false     | wrapper + Settings landed                                                | T01/T02's existing README structure                                                 |

Every T04 slice is sequential inside a single PR; no sub-agent fan-out. `/speckit-tasks` will break these further but the parallelism boundary is "T04 as a whole → afterwards, T17–T21", not "inside T04".

## Phase 0 — Outline & Research

Research output: [research.md](./research.md).

The spec has zero `[NEEDS CLARIFICATION]` markers and the five clarifications from `/speckit-clarify` are already resolved. A handful of implementation-detail decisions still sit below spec altitude and above `/speckit-tasks` altitude — Phase 0 resolves them with rationale rooted in an existing repo artefact or a load-bearing external reference.

1. **Vertex SDK choice** — `google-genai` (the new SDK) vs `google-cloud-aiplatform` (the older one). Includes the version pin and the argument for picking the newer SDK despite the implementation-plan T04 wording mentioning Model Garden.
2. **Retry library** — `tenacity` (named in the implementation-plan T04 description) vs hand-rolled. Confirms the choice and pins the version.
3. **Async test runner** — `pytest-asyncio` vs `anyio` plugin; configuration shape (`asyncio_mode = "auto"` vs decorators).
4. **Schema validation strategy** — Vertex native `response_schema` vs caller-side `pydantic.TypeAdapter` vs `jsonschema`. Two-stage approach (SDK requests JSON mode; wrapper validates with `TypeAdapter` on the parsed result) and why we don't add a third dependency.
5. **Mock backend layout** — file-per-prompt-SHA vs single fixtures.yaml; the canonical-prompt SHA computation (what's hashed and why).
6. **Cost arithmetic precision** — `Decimal` (chosen) vs `float`. Implications for the trace record and the cost ledger.
7. **Settings library** — `pydantic-settings` vs raw `os.environ` parsing. Why this is the moment to introduce it (T02 deferred it; T04 needs it for `LLM_BACKEND` and the production-mode refusal).
8. **Static-guardrail mechanism** — ripgrep-backed shell script (chosen, mirroring T03's visual-discipline pattern) vs custom Python AST walker vs ESLint-style import rule.
9. **Trace sink and cost ledger interface shape** — `typing.Protocol` (chosen for structural typing + zero-runtime cost) vs `abc.ABC` vs Pydantic.
10. **Fixture file format** — JSON object with `{ "text": str, "input_tokens": int, "output_tokens": int, "model": str, "model_version": str }` vs richer envelope. Includes how the schema-INVALID fixture flips one field to violate the schema.
11. **`pricing.yaml` shape and units** — per-1k-tokens prices vs per-token prices; input/output split; currency (USD); how an unknown-region request is handled.
12. **`configs/models.yaml` shape** — flat agent-keyed YAML vs nested per-environment; T04 uses a flat single-environment shape because the project is production-only (constitution §8).
13. **What the canonical prompt SHA includes** — system_prompt + user_payload + json_schema (canonicalised) → SHA-256. Why the schema is part of the SHA: changing the schema must change the response, so a fixture cached against the old schema is stale.
14. **`/debug/vertex-ping` route** — explicitly **out of T04 scope**; T11 introduces and removes it. T04 makes sure `call_model` is callable from a route added later without any wrapper change.
15. **`structlog` event names** — wrapper emits one log event per call with name `llm_call` carrying `{trace_id, agent, model, model_version, outcome, attempts, latency_ms, cost_usd}`. Prompt content / output content NEVER in the log. (Reuses T02 redactor as a defence-in-depth.)

All 15 decisions are resolved in `research.md` with a Decision, Rationale, and Alternatives Considered.

## Phase 1 — Design & Contracts

**Prerequisites**: `research.md` complete.

### Data model

See [data-model.md](./data-model.md). T04 has zero persistent rows. The "entities" enumerated there are the in-process Pydantic models, the typed error hierarchy, and the two injectable interfaces a reviewer should be able to point at:

- `ModelCallRequest`, `ModelCallResult`, `TraceRecord`, `Pricing`, `ModelConfig`, `ModelsConfig` (Pydantic models with full field validation).
- `ModelCallConfigError`, `VertexTimeoutError`, `VertexUpstreamUnavailableError`, `VertexSchemaError`, `SessionBudgetExceeded`, `TraceWriteError` (typed errors, all rooted in a single `WrapperError` base for `except` ergonomics).
- `VertexBackend(Protocol)`, `TraceSink(Protocol)`, `CostLedger(Protocol)` (structural typing) + `InMemoryTraceSink`, `InMemoryCostLedger` (concrete in-memory implementations).
- `Settings` (pydantic-settings) — the slim env-config class.

Each entity carries its validation rules, lifecycle (immutable / mutated / append-only), and the constitution principles it serves.

### Contracts

See [contracts/wrapper-contract.md](./contracts/wrapper-contract.md). One consolidated document covers eleven surfaces:

1. **Public call surface** — `async def call_model(req: ModelCallRequest, *, sink: TraceSink, ledger: CostLedger, settings: Settings) -> ModelCallResult` — the only function any consumer imports.
2. **Backend protocol** — what `_real_backend.py` and `_mock_backend.py` both implement (`async def generate(req: ModelCallRequest, model_cfg: ModelConfig) -> RawBackendResult`).
3. **Error contract** — the six typed errors, their fields, the `outcome` value each maps to in the trace record.
4. **`configs/models.yaml` schema** — the YAML shape, the agents committed in this PR, the `prompt_version` placeholder convention.
5. **`pricing.yaml` schema** — model-keyed entries with `input_per_1k_tokens` / `output_per_1k_tokens` USD prices.
6. **Environment contract** — `LLM_BACKEND`, `APP_ENV` (the canonical runtime selector inherited from T01), `LLM_BUDGET_PER_SESSION_USD`, `LLM_FIXTURES_DIR`; defaults; production-mode startup refusal.
7. **Trace record schema** — the field set (FR-008), the `outcome` enum, the prompt-SHA recipe.
8. **Cost ledger contract** — the protocol methods, the budget-exceeded short-circuit, concurrency note.
9. **Mock fixture format** — JSON envelope, file naming convention (`<agent>/<sha256>.json`), the schema-invalid pattern, the `_unrecorded` capture rule.
10. **Test matrix** — the FR-017 scenarios mapped to specific `pytest` test names so the reviewer can run a single command and tick each FR off.
11. **Static-guardrail contract** — the regex the script greps for, the allowlisted modules, the failure output shape.

The runtime artefacts (`vertex.py`, `pricing.yaml`, `configs/models.yaml`, fixture files) are NOT duplicated under `specs/007-t04-vertex-client-wrapper/contracts/` — that would create two sources of truth that would silently drift. The contract document references the runtime paths.

### Quickstart

See [quickstart.md](./quickstart.md) — a reviewer-facing walkthrough that validates the T04 PR end-to-end in under 5 minutes, mirroring SC-005 (60-second backend test run on a clean tree without any GCP credential) and SC-007 (one trace record is enough to audit any historical call).

### Agent context update

`CLAUDE.md` does not carry `<!-- SPECKIT START -->` / `<!-- SPECKIT END -->` markers (verified via `grep` — zero matches, same as T02 / T03). T00 stripped them; the existing "How work happens here (Spec Kit)" section in `CLAUDE.md` already points sub-agents at the Spec Kit flow. T04 does not re-introduce the auto-generated block. **No `CLAUDE.md` edit in this step.**

### Re-evaluate Constitution Check (post-design)

Nothing in Phase 0 / Phase 1 changes the gate result. The commitments made in Phase 0 (`google-genai` SDK, `tenacity` retry, `pydantic-settings`, `pytest-asyncio` auto-mode, `Decimal` cost arithmetic, `Protocol`-based interfaces, ripgrep guardrail, file-per-prompt-SHA fixtures, prompt-SHA includes the schema) are fully consistent with §1, §5, §6, §7, §12, §14, §15, §16, §17, §18. Gate remains **PASS**.

## Complexity Tracking

Not applicable — no Constitution Check violations. This table is intentionally empty.

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------ |
| *(none)*  | —          | —                                    |
