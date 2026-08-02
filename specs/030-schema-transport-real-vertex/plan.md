# Implementation Plan: Real-Vertex schema transport (030 blocker fix)

**Branch**: `030-schema-transport-real-vertex` | **Date**: 2026-08-02 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `specs/030-schema-transport-real-vertex/spec.md`

- **agent:** `backend-engineer`
- **parallel:** false
- **depends_on:** [T04, T17, T18, T19]
- **contract:** `prompts/*/v0001/schema.json` (existing, unchanged — the whole point of the fix is that these files stay exactly as committed)

## Summary

Fix the confirmed real-Vertex blocker: `google-genai 0.8.0`'s `response_schema` transformer (`t_schema`) rejected every committed prompt schema before any network I/O, masked as `VertexUpstreamUnavailableError`. Chosen fix (A-vs-B decision recorded in spec Clarifications): bump the SDK to the 2.x GA line and transport the committed JSON-Schema documents verbatim via `response_json_schema`, rather than maintaining a lossy hand-rolled JSON-Schema → proto-`Schema` translator on a pre-GA 0.x pin.

Deliverables:

1. **Dependency bump** — `google-genai>=2.16,<3` (ships `py.typed` → stale mypy override removed); `google-api-core` removed (nothing imports it post-rework); `httpx` promoted from dev group to main deps (direct import in `_real_backend.py`; already in the prod closure via google-genai).
2. **`app/backend/llm/_real_backend.py`** — `response_json_schema` transport; SDK/httpx → `BackendError` translation (`classify_http_status` + `translate_transport_error`); `GenAiAPIError` re-export for tests only; ADC-only construction unchanged.
3. **`app/backend/llm/_backend_protocol.py`** — SDK-free transport-classification hierarchy: `BackendError` → `BackendTransientError` (retried) / `BackendDeadlineExceededError` (no retry → `VertexTimeoutError`) / `BackendCallerError` (no retry → `ModelCallConfigError`) / `BackendUpstreamError` (no retry → `VertexUpstreamUnavailableError`).
4. **`app/backend/llm/vertex.py`** — retryable set + classification consume only the SDK-free types (no provider-SDK import anywhere in the module); effective output cap `min(request.max_output_tokens, agent_cfg.max_output_tokens)` wires the previously dead `configs/models.yaml` pin (§16). §12 hard ceilings (30 s / 4096) untouched.
5. **Tests** — `test_prompt_schema_transport.py` (offline, glob-parametrized over `prompts/*/v*/schema.json`, exercises the SDK's actual pre-network Vertex request converter; guardrail-allowlisted); `test_real_backend.py` (taxonomy + stubbed `generate()` transport assertions, no SDK import); `test_vertex_wrapper.py` reworked to the transport-error types + two cap tests.
6. **Guardrail + docs** — allowlist entry in `scripts/check-no-provider-sdk-imports.sh`; `docs/engineering/vertex-integration.md` retry table / JSON-mode / cap sections updated.

## Technical Context

**Language/Version**: Python 3.12. **Primary Dependencies**: `google-genai 2.16.0` (bumped), `httpx 0.28.x` (promoted to main), tenacity, Pydantic v2. **Removed**: `google-api-core` (+ transitive protobuf/proto-plus/googleapis-common-protos).

**Verified against 2.16.0**: `Client(vertexai=True, project=..., location=...)` construction unchanged and credential-parameter-free; `response.text` / `usage_metadata.prompt_token_count` / `usage_metadata.candidates_token_count` / `model_version` unchanged; `response_json_schema` passes through the Vertex converter verbatim (`responseJsonSchema`); SDK built-in retry is opt-in only (`HttpOptions.retry_options`) and remains OFF; errors are `google.genai.errors.APIError`/`ClientError`/`ServerError` (classified by `.code` — 429 is a `ClientError`) plus raw `httpx` transport exceptions.

**Storage**: none. **Testing**: fully offline — no network, no ADC, no real client construction (stub api-client namespace for the converter; `__new__`-constructed backend with a stubbed private client for `generate()`).

**Out of scope**: `prompts/**`, `app/backend/agents/**`, `alembic/**`, CI workflow files, live-Vertex smoke (manual post-merge step).

## Constitution Check

| §   | Principle                    | Applies?                                                                                                                  | Status |
| --- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------ |
| 2   | Deterministic orchestration  | Indirect — error classification stays typed and deterministic; no LLM output drives routing.                                | Pass   |
| 5–6 | Secrets / WIF / ADC-only     | **Core.** `genai.Client` construction keeps zero credential parameters; `test_no_inline_credentials.py` still enforces.     | Pass   |
| 12  | LLM cost/latency caps        | **Core.** 30-s timeout and 4096-token hard ceilings unchanged; retry budget still 3 attempts under the wall clock.           | Pass   |
| 13  | Calibration never blocks     | N/A — no prompt content changes.                                                                                            | N/A    |
| 16  | Configs as code              | **Core.** The dead `configs/models.yaml` `max_output_tokens` pin becomes live (`min(request, pin)`); schemas stay in Git and travel verbatim. | Pass   |
| 17  | Specs precede implementation | Yes — this flow.                                                                                                            | Pass   |
| 18  | Multi-agent explicit         | Yes — single `backend-engineer` task, `parallel: false`, dispatched by the orchestrator.                                    | Pass   |

Sections not listed (1, 3–4, 7–11, 14–15, 19–20): N/A — no DB, no deploy surface, no PII path changes (error messages carry status codes, not payloads). **Gate result**: PASS.

## Project Structure

```text
specs/030-schema-transport-real-vertex/
├── spec.md
├── plan.md          # This file
└── tasks.md

pyproject.toml                                        # bump + dep moves + mypy override removal
uv.lock                                               # re-locked
app/backend/llm/_backend_protocol.py                  # + BackendError hierarchy
app/backend/llm/_real_backend.py                      # response_json_schema + translation
app/backend/llm/vertex.py                             # SDK-free taxonomy + effective cap
app/backend/llm/errors.py                             # docstring accuracy only
app/backend/tests/llm/test_vertex_wrapper.py          # taxonomy rework + 2 cap tests
app/backend/tests/llm/test_real_backend.py            # new — translation + stubbed generate()
app/backend/tests/llm/test_prompt_schema_transport.py # new — offline regression (allowlisted)
scripts/check-no-provider-sdk-imports.sh              # allowlist entry
docs/engineering/vertex-integration.md                # retry table / JSON mode / caps
```

## Phases

- **Phase 0**: reproduce the blocker on 0.8.0 (`t_schema` rejection for all three schemas) — done before any change.
- **Phase 1**: SDK bump + verification of the 2.16.0 surface (construction, response fields, converter pass-through, error family, retry-off default).
- **Phase 2**: transport + taxonomy implementation; cap wiring; tests.
- **Phase 3**: guardrail, docs, spec artefacts, quality gates.
