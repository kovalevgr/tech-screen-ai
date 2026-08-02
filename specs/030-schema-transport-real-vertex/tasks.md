# Tasks: Real-Vertex schema transport (030 blocker fix)

**Input**: Design documents from `specs/030-schema-transport-real-vertex/`
**Prerequisites**: plan.md, spec.md; contract `prompts/*/v0001/schema.json` (existing, unchanged)

**Organization**: single branch, `agent: backend-engineer` throughout, `parallel: false`. Story labels map to spec.md: US1 = verbatim schema transport, US2 = retry taxonomy, US3 = live models.yaml pin.

## Phase 0: Reproduction (before any change)

- [X] T001 Reproduce the blocker on the pinned 0.8.0: `_transformers.t_schema` rejects all three committed schemas pre-network (interviewer `extra_forbidden` on `$schema`/`$id`/`additionalProperties`; assessor `AttributeError` on `"type": ["string","null"]`; planner 15 errors on `const` / integer enums)

## Phase 1: SDK bump (US1)

- [X] T002 [US1] `pyproject.toml`: `google-genai>=2.16,<3`; remove `google-api-core` (nothing imports it post-rework); promote `httpx>=0.28,<0.29` from dev group to main deps (direct import in `_real_backend.py`); remove the stale 0.x `ignore_missing_imports` mypy override (2.16 ships `py.typed`); `uv lock` + `uv sync`
- [X] T003 [US1] Verify the 2.16.0 surface offline: `Client(vertexai=True, project=..., location=...)` unchanged (ADC-only, zero credential params); `response.text` / `usage_metadata` token fields / `model_version` unchanged; `response_json_schema` passes the Vertex request converter verbatim; SDK built-in retry is opt-in only and stays OFF

## Phase 2: Transport + taxonomy (US1+US2)

- [X] T004 [US2] `app/backend/llm/_backend_protocol.py`: SDK-free `BackendError` hierarchy — `BackendTransientError` (retried), `BackendDeadlineExceededError` (no retry → `VertexTimeoutError`), `BackendCallerError` (no retry → `ModelCallConfigError`), `BackendUpstreamError` (no retry → `VertexUpstreamUnavailableError`); protocol docstring updated
- [X] T005 [US1] `app/backend/llm/_real_backend.py`: `response_json_schema` + `response_mime_type="application/json"` (legacy `response_schema` forbidden — its `t_schema` translator is the blocker); `classify_http_status` (429/5xx-except-504 → transient; 504 → deadline; 400/403 → caller; else upstream) + `translate_transport_error` (APIError by `.code`; `httpx.TimeoutException` → deadline; other `httpx.TransportError` → transient); `GenAiAPIError` re-export for tests only
- [X] T006 [US2] `app/backend/llm/vertex.py`: `_RETRYABLE_EXCEPTIONS = (BackendTransientError, ConnectionError)`; in-loop conversions (`BackendDeadlineExceededError` → `VertexTimeoutError`, `BackendCallerError` → `ModelCallConfigError`); post-loop `except (BackendError, ConnectionError)` classification; `google.api_core` import removed; `errors.py` docstrings updated
- [X] T007 [US3] `app/backend/llm/vertex.py`: effective cap `min(request.max_output_tokens, agent_cfg.max_output_tokens)` — `ModelCallRequest` semantics and §12 ceilings untouched

## Phase 3: Tests + guardrail (US1+US2+US3)

- [X] T008 [US2] `app/backend/tests/llm/test_vertex_wrapper.py`: scripted-backend scenarios reworked from `google.api_core` exceptions to the `BackendError` types (retry-then-success, budget-exhausted, deadline-not-retried, caller-error-not-retried, outcome matrix)
- [X] T009 [US3] `test_vertex_wrapper.py`: recording backend + 2 cap tests — interviewer pin 2048 with request default 4096 → backend receives 2048; explicit request 1024 → backend receives 1024
- [X] T010 [US2] `app/backend/tests/llm/test_real_backend.py` (new, no SDK imports — uses the `GenAiAPIError` re-export): full status-code taxonomy, httpx translation, defensive branch, and stubbed `generate()` (schema forwarded verbatim on `response_json_schema`, `response_schema` never set, envelope mapping, error-path translation)
- [X] T011 [US1] `app/backend/tests/llm/test_prompt_schema_transport.py` (new): glob-parametrized over `sorted(prompts/*/v*/schema.json)`; drives `types.GenerateContentConfig` + `models._GenerateContentParameters_to_vertex` (the SDK's actual pre-network path) with a stub api-client; asserts verbatim `responseJsonSchema`; fails on any future untransportable schema
- [X] T012 [US1] `scripts/check-no-provider-sdk-imports.sh`: allowlist `app/backend/tests/llm/test_prompt_schema_transport.py`; `test_no_provider_sdk_imports.py` still passes (clean-tree assertion + planted violation)

## Phase 4: Docs + gates

- [X] T013 `docs/engineering/vertex-integration.md`: retry-policy table rewritten to the 2.x taxonomy (`BackendError` classification, SDK retry OFF); JSON-mode §1 rewritten to `response_json_schema` verbatim transport; adapter/caps sections mention the `min(request, pin)` rule
- [X] T014 Quality gates: `uv run pytest app/backend/tests` green; `ruff check` + `ruff format --check` clean; `mypy --strict app/backend` clean; `scripts/check-no-provider-sdk-imports.sh` exits 0; transport proof passes for all three schemas
- [X] T015 Spec Kit artefacts (this directory) committed with the feature branch

## Phase 5: Reviewer gate fixes (PASS-WITH-FINDINGS, 2026-08-02)

- [X] T016 `app/backend/llm/vertex.py` module docstring: stale "SDK-side ``response_schema``" corrected to ``response_json_schema``
- [X] T017 502-widening honesty: spec.md Clarification "Semantics preserved" rewritten (pre-030 only 429/500/503 were retried; 030 deliberately widens to blanket 5xx-except-504, resolving the pre-030 docstring-vs-table contradiction in the docstring's favor); `classify_http_status` docstring no longer claims preservation; same one-liner added to the vertex-integration.md 030 note
- [X] T018 [US2] `test_vertex_wrapper.py`: wrapper-level `BackendUpstreamError` test — scripted backend raises it → `VertexUpstreamUnavailableError`, exactly 1 backend call, trace `outcome="upstream_unavailable"` (spec US2 scenario 4 now covered at the wrapper layer, not just classification)
- [X] T019 T04 contract amendment: dated notes appended to `specs/007-t04-vertex-client-wrapper/contracts/wrapper-contract.md` and `data-model.md` — error taxonomy superseded by this spec; `google.api_core` references are historical (no in-place rewrites)
- [X] T020 Guardrail hardening: `scripts/check-no-provider-sdk-imports.sh` second check fails any `GenAiAPIError` occurrence outside `_real_backend.py` / `test_real_backend.py` (closes the re-export bypass); `test_no_provider_sdk_imports.py` still passes
- [X] T021 `test_prompt_schema_transport.py`: comment above the SDK-private converter usage (AttributeError ⇒ converter moved on an SDK bump; re-pin the path — schemas themselves are probably fine); all gates re-run green
