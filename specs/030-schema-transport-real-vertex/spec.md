# Feature Specification: Real-Vertex schema transport (030 blocker fix)

**Feature Branch**: `030-schema-transport-real-vertex`
**Created**: 2026-08-02
**Status**: Draft
**Input**: Confirmed BLOCKER — the real Vertex backend cannot transport any committed prompt schema. `app/backend/llm/_real_backend.py` passed the raw committed JSON-Schema dict as `response_schema`; the pinned `google-genai 0.8.0` rejected ALL THREE committed schemas **pre-network** in `_transformers.t_schema`: interviewer failed on `$schema` / `$id` / `additionalProperties` (`extra_forbidden`), assessor crashed with `AttributeError: 'list' object has no attribute 'upper'` on `"type": ["string", "null"]`, planner failed with 15 errors (`const`, integer enums). The failure was masked as `VertexUpstreamUnavailableError`, so every real-backend structured call would have died with a misleading error the moment T18/T19 went live against Vertex.

## Clarifications

### Session 2026-08-02

- Q: **Fix A (SDK bump to `response_json_schema`) vs Fix B (hand-rolled JSON-Schema → `types.Schema` translator kept on 0.8.0)?** → A: **Fix A — SDK bump (decision made by the orchestrator before dispatch).** Rationale: (1) `response_json_schema` (google-genai ≥ 1.22) transports the committed document **verbatim** — the schema on the wire is byte-identical to the schema in Git, which is exactly the §16 configs-as-code posture and keeps `prompts/*/schema.json` the single contract for T17/T18/T19 with zero translation drift; (2) a hand-rolled translator would have to down-convert `$schema`/`$id`/`additionalProperties`/type-unions/`const` into the SDK's proto-shaped `Schema` — silently weakening the contract (e.g. `additionalProperties: false` is not representable in 0.8.0's `Schema`) and creating a maintenance liability the moment prompt-engineer ships v0002 schemas; (3) 0.x was pre-GA and unsupported; 2.x is the current GA line. The 2.0.0 breaking changes affect only the Interactions API surface, not `generate_content`.
- Q: Which exact pin? → A: **`google-genai>=2.16,<3`** (2.16.0 installed, current latest, July 2026). `response_json_schema` has existed since 1.22.0, so any future 2.x resolves fine; `<3` guards the next major. Fallback to latest 1.x was authorised if 2.x proved incompatible — it did not: `Client(vertexai=True, project=..., location=...)` construction, `response.text`, `response.usage_metadata.prompt_token_count` / `.candidates_token_count`, and `response.model_version` all hold unchanged. 2.x also ships `py.typed`, so the 0.x-era mypy `ignore_missing_imports` override was removed.
- Q: The bumped SDK no longer raises `google.api_core.exceptions.*` — what does it actually raise, and how does the wrapper stay SDK-free? → A: 2.x raises `google.genai.errors.APIError` (`ClientError` for 4xx, `ServerError` for 5xx — note **429 arrives as a `ClientError`**, so classification must use `.code`, not the subclass) and lets raw `httpx` transport exceptions (`ConnectError`, `TimeoutException`, other `TransportError`) propagate. **Design choice: backend-protocol-level translation.** `_real_backend.py` (allowlisted for SDK imports) translates every SDK/transport exception into a new SDK-free `BackendError` hierarchy in `_backend_protocol.py` (`BackendTransientError` / `BackendDeadlineExceededError` / `BackendCallerError` / `BackendUpstreamError`) before it escapes `generate()`. `vertex.py` classifies only those types — no provider-SDK import, guardrail intact. This was chosen over re-exporting SDK exception types into `vertex.py` because it keeps the retry policy testable without any SDK object and makes the mock/real backends symmetrical (both may raise `BackendError`s). A single narrow re-export (`GenAiAPIError`) exists on `_real_backend.py` for taxonomy tests only.
- Q: Semantics preserved across the taxonomy swap? → A: **Almost — with one deliberate widening.** 5xx codes other than 500/503 were previously not retried (pre-030, only `ServiceUnavailable`=503, `InternalServerError`=500, and `ResourceExhausted`=429 were in the retryable tuple; 501/502/505 fell to the 1-attempt catch-all); 030 deliberately widens to blanket 5xx-except-504, resolving the pre-030 docstring-vs-table contradiction (the wrapper module docstring already claimed "HTTP 5xx, HTTP 429, connection-level errors") in the docstring's favor. Everything else is preserved: HTTP 504 / transport timeout (the `DeadlineExceeded` equivalent) → NOT retried → `VertexTimeoutError`; HTTP 400/403 → `ModelCallConfigError`; every other upstream code → `VertexUpstreamUnavailableError`. The SDK's own opt-in retry layer stays OFF (`HttpOptions.retry_options` never set) so the wrapper keeps sole ownership of the 3-attempt budget.
- Q: `configs/models.yaml` pins per-agent `max_output_tokens: 2048` (interviewer/assessor) but `call_model` ignored it — dead config violates §16. In scope? → A: **Yes (explicit task item).** The effective cap sent to the backend becomes `min(request.max_output_tokens, agent_cfg.max_output_tokens)`. `ModelCallRequest` field semantics and its 4096 hard ceiling (§12) are unchanged; the agent pin can only lower, and an explicit lower request still wins.
- Q: `google-api-core` dependency? → A: **Removed.** It was declared solely because `vertex.py` imported `google.api_core.exceptions`; after the taxonomy rework nothing in the repo imports it (verified by grep), and google-genai 2.x does not pull it in. Its removal also drops protobuf/proto-plus/googleapis-common-protos from the closure. `httpx` moved from the dev group to main deps because `_real_backend.py` now imports it directly (it was already in the prod closure as a google-genai base dep).
- Q: Live-Vertex smoke test? → A: **Out of scope — explicit manual post-merge step.** Every test in this feature is fully offline (no network, no ADC, no real `genai.Client` construction): the schema-transport regression drives the SDK's actual pre-network Vertex request converter with a stub api-client namespace, and the real-backend tests stub the private client attribute via `__new__`.

## User Scenarios & Testing *(mandatory)*

The "users" are the T18/T19 agent wrappers (and T20's orchestrator behind them) whose structured-output calls must reach Vertex with the committed contract intact, and the operators who need honest error classification when Vertex misbehaves.

### User Story 1 — Committed schemas reach Vertex verbatim (Priority: P1)

Any `call_model` invocation carrying a committed `prompts/<agent>/<version>/schema.json` reaches the SDK's request builder without pre-network rejection and without mutation.

**Acceptance Scenarios**:

1. **Given** each of the three committed schemas, **When** it is placed on `GenerateContentConfig.response_json_schema` and run through the SDK's Vertex request converter (the exact pre-network path of `generate_content`), **Then** the wire-shaped request carries the schema byte-for-byte under `responseJsonSchema` plus `responseMimeType: application/json`.
2. **Given** a future `prompts/*/v*/schema.json` lands, **Then** the parametrized regression covers it automatically (glob-driven) and FAILS if the pinned SDK cannot transport it.
3. **Given** `RealVertexBackend.generate` with a `json_schema`, **Then** the config it hands the SDK uses `response_json_schema` (never the legacy `response_schema` translator path) — asserted against a stubbed client.

### User Story 2 — Honest, retry-correct error classification (Priority: P1)

Wrapper callers keep the documented error semantics under the new SDK: transient upstream failures are retried up to 3 attempts, deadline-equivalents are not retried, caller-side errors surface as `ModelCallConfigError`, and everything else surfaces as `VertexUpstreamUnavailableError` — with `vertex.py` importing zero provider-SDK symbols.

**Acceptance Scenarios**:

1. HTTP 429 / 500 / 502 / 503 and connection-level `httpx.TransportError` → `BackendTransientError` → retried; after 3 attempts → `VertexUpstreamUnavailableError` with `attempts == 3` on the trace.
2. HTTP 504 / `httpx.TimeoutException` → `BackendDeadlineExceededError` → exactly 1 attempt → `VertexTimeoutError`, trace `outcome="timeout"`.
3. HTTP 400 / 403 → `BackendCallerError` → exactly 1 attempt → `ModelCallConfigError`, trace `outcome="config_error"`.
4. HTTP 401 / 404 / 408 / unknown → `BackendUpstreamError` → 1 attempt → `VertexUpstreamUnavailableError`.
5. `scripts/check-no-provider-sdk-imports.sh` exits 0 on the tree (the only new allowlisted file is the schema-transport regression test).

### User Story 3 — The models.yaml token pin is live config (Priority: P2)

**Acceptance Scenarios**:

1. Interviewer request at the wrapper default `max_output_tokens=4096` + the committed pin 2048 → the backend receives 2048.
2. Explicit request `max_output_tokens=1024` (below the pin) → the backend receives 1024.

## Requirements

- **FR-030-1**: `pyproject.toml` pins `google-genai>=2.16,<3`; `uv.lock` updated; stale 0.x mypy override removed (2.x ships `py.typed`).
- **FR-030-2**: `_real_backend.py` transports `json_schema` via `response_json_schema` + `response_mime_type="application/json"`; construction stays ADC-only (no credential parameters — constitution §5/§6, ADR-013, enforced by `test_no_inline_credentials.py`).
- **FR-030-3**: SDK-free transport-error hierarchy in `_backend_protocol.py`; translation lives in `_real_backend.py`; `vertex.py`'s retryable set and classification consume only the SDK-free types. Documented semantics preserved (see Clarifications).
- **FR-030-4**: Effective output cap = `min(request.max_output_tokens, agent pin)`; §12 ceilings untouched.
- **FR-030-5**: Offline glob-parametrized schema-transport regression (`test_prompt_schema_transport.py`), allowlisted in the guardrail script.
- **FR-030-6**: `docs/engineering/vertex-integration.md` updated (retry table, JSON mode, cap description). `prompts/**`, `app/backend/agents/**`, alembic, CI workflows untouched.
- **FR-030-7**: Mock backend behaviour unchanged (SHA-recipe fixtures; `json_schema` participates in the hash only).

## Success Criteria

- **SC-1**: The pre-network transport proof passes for all three committed schemas (the 0.8.0 reproduction failed on all three).
- **SC-2**: `uv run pytest app/backend/tests`, `ruff check`, `ruff format --check`, `mypy --strict app/backend`, and `scripts/check-no-provider-sdk-imports.sh` all green.
- **SC-3**: No test performs network I/O or requires ADC.
