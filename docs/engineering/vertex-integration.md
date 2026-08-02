# Vertex AI Integration

This document describes how TechScreen calls Google Vertex AI for every LLM-driven operation. The goal is to make every call observable, bounded, and replaceable.

Related: [ADR-002](../../adr/002-llm-provider-vertex-ai.md), [ADR-003](../../adr/003-model-selection-gemini-flash-pro.md), [constitution §12](../../.specify/memory/constitution.md).

---

## Scope

Everything that talks to a large language model goes through the Vertex wrapper package at `app/backend/llm/`. The single sanctioned entry point is `app.backend.llm.call_model` (re-exported from `vertex.py`); the package's private leaves `_real_backend.py` (google-genai async client) and `_mock_backend.py` (in-process fixture stub) are the only modules in the codebase allowed to import a model-provider SDK — the `scripts/check-no-provider-sdk-imports.sh` guardrail (pre-commit + CI) enforces this. Application code never:

- Calls Google AI Studio, Anthropic, or OpenAI APIs directly.
- Embeds API keys or credentials in source (constitution §5).
- Bypasses cost or latency caps.
- Skips persisting a `turn_trace` row for a call that reached the network.

---

## Layer structure

```
services/*                business-facing API, takes domain objects
    ↓ calls
llm/agents/*              one module per agent (interviewer, assessor, planner)
                          owns prompt assembly, response parsing, schema validation
    ↓ calls
llm/                      the wrapper package — `call_model` orchestrates retry,
  ├── vertex.py           timeout, cost tracking, tracing, schema validation
  ├── errors.py           typed error hierarchy (WrapperError + 6 children)
  ├── trace.py            TraceRecord + TraceSink protocol + InMemoryTraceSink
  ├── cost_ledger.py      CostLedger protocol + InMemoryCostLedger
  ├── pricing.py          PricingTable loader (pricing.yaml)
  ├── models_config.py    per-agent model selection (configs/models.yaml)
  ├── _backend_protocol.py
  ├── _real_backend.py    Vertex SDK adapter — google-genai async client
  └── _mock_backend.py    in-process deterministic stub (fixture-keyed)
    ↓ calls
Vertex AI API             via the google-genai SDK (Vertex mode)
```

Services never see a prompt string. Agent modules never see an HTTP response.

---

## The Vertex adapter

### Input

```python
class LLMCall(BaseModel):
    agent: Literal["interviewer", "assessor", "planner"]
    model: str                         # e.g. "gemini-2.5-flash"
    system_prompt: str
    user_content: list[Part]
    json_schema: dict | None = None    # if set → JSON mode + validation
    temperature: float = 0.0
    max_output_tokens: int = 4096      # hard cap (constitution §12)
    timeout_s: float = 30.0            # hard cap (constitution §12)
    session_id: UUID                   # always required for tracing
    trace_metadata: dict | None = None
```

### Output

```python
class LLMResult(BaseModel):
    text: str                          # raw string
    parsed: dict | None                # set iff json_schema was provided
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int
    model: str
    model_version: str
    turn_trace_id: UUID                # FK into turn_trace
```

### Responsibilities of the adapter

The adapter is the only place that:

1. Authenticates to Vertex (via Application Default Credentials, resolved from the runtime service account).
2. Enforces the timeout (a hard upper bound; no caller can pass > 30s — `le=30` on `ModelCallRequest.timeout_s`, constitution §12).
3. Enforces `max_output_tokens`: the effective cap sent to the backend is `min(request.max_output_tokens, configs/models.yaml per-agent pin)` — the caller may request lower, never higher, and the agent pin can only lower it further (constitution §16).
4. Retries on transient errors (see "Retry policy" below).
5. Computes per-call cost from token counts and model price table.
6. Persists `turn_trace` before returning — even on failure (the row records the error).
7. Emits a structured log line (`logger.info("llm_call", extra=...)`).

The adapter does **not** own:

- Prompt assembly (that is the agent module).
- Response parsing or schema validation in the business sense (also the agent module).
- Deciding whether to retry on semantic errors (the agent module can re-issue the call).

---

## Retry policy

> **Note:** Reconciled per `specs/007-t04-vertex-client-wrapper/spec.md` Clarifications 2026-04-26 to a single uniform 3-attempt budget across every retryable error class. Reworked in 030 (`specs/030-schema-transport-real-vertex/`): the pinned `google-genai` 2.x raises `google.genai.errors.APIError` (`ClientError` 4xx / `ServerError` 5xx, classified by `.code` — 429 arrives as a *ClientError*) plus raw `httpx` transport exceptions; `google.api_core` is gone from the closure. `_real_backend.py` translates every SDK exception into the SDK-free `BackendError` hierarchy (`_backend_protocol.py`) so `vertex.py` never imports a provider SDK. The SDK's own opt-in retry layer stays OFF (`HttpOptions.retry_options` never set) — the wrapper owns the budget. One deliberate widening: 5xx codes other than 500/503 were previously not retried (only 429/500/503 were in the pre-030 retryable tuple); 030 widens to blanket 5xx-except-504, resolving the pre-030 docstring-vs-table contradiction in the docstring's favor.

The adapter applies a uniform **3-attempt total** budget (1 initial + 2 retries) with exponential backoff and jitter:

| Upstream condition                                                                                              | Backend classification          | Attempts | Notes                                                                                                                  |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| HTTP 429 (quota) · HTTP 5xx except 504 · connection-level `httpx.TransportError` (refused, reset, broken stream) | `BackendTransientError`         | 3        | Exponential backoff with jitter; total wall clock still bounded by the 30-s `asyncio.wait_for` cap (constitution §12).   |
| HTTP 504 · `httpx.TimeoutException`                                                                              | `BackendDeadlineExceededError`  | 1        | **No retry** — the timeout already fired; repeating it only burns the remaining 30-s budget. Raised as `VertexTimeoutError`. |
| HTTP 400 (invalid argument) · HTTP 403 (permission denied)                                                       | `BackendCallerError`            | 1        | **No retry** — request is malformed or auth is broken; re-raised as `ModelCallConfigError`.                             |
| Any other `APIError` code (401, 404, 408, …)                                                                     | `BackendUpstreamError`          | 1        | **No retry** — surfaced as `VertexUpstreamUnavailableError` (pre-030 catch-all semantics preserved).                    |

Schema validation failures are **never** retried by the adapter — the wrapper raises `VertexSchemaError` immediately with `raw_payload` attached. Per-agent retry / fallback / escalation policies live in the agent modules (Assessor, Planner, Interviewer in T18–T21) and are described under "JSON mode" below.

Total time across retries is still bounded by `timeout_s` on the call (default 30 s).

---

## JSON mode

When `json_schema` is provided the adapter:

1. Uses Vertex's native JSON output mode: `response_mime_type = "application/json"` + `response_json_schema` (google-genai ≥ 1.22; we pin 2.x). The committed `prompts/<agent>/<version>/schema.json` document is transported to the API **verbatim** — no client-side translation. The legacy `response_schema` field is forbidden: its `t_schema` translator rejects standard JSON-Schema keywords (`$schema`, `$id`, `additionalProperties`, `"type": [..., "null"]` unions, `const`) before any network I/O, which is exactly the 030 blocker. The offline regression `app/backend/tests/llm/test_prompt_schema_transport.py` pins the verbatim-transport behaviour for every committed and future prompt schema.
2. Validates the result against the schema using `pydantic.TypeAdapter`.
3. On validation failure, raises `VertexSchemaError` with the raw text attached for debugging — the adapter itself does not retry on schema failures.

Agent modules decide whether to retry on schema failure. Typically:

- **Assessor:** retry once on schema miss, parsed-output validation failure, or echoed-id equality mismatch (the response must echo the requested turn/session/competency ids) — with an identical fresh request; on the second failure the wrapper raises a typed `AssessorOutputInvalid` surfaced to the orchestrator, which owns the escalation policy (e.g. marking `needs_manual_review`). See `app/backend/agents/assessor.py` (T19).
- **Planner:** retry up to twice; on repeated failure, fall back to the previous rubric version's default plan template.
- **Interviewer:** retry once on schema miss (or parsed-output validation failure); on the second failure the wrapper raises a typed `InterviewerOutputInvalid` surfaced to the orchestrator, which owns the escalation policy. See `app/backend/agents/interviewer.py` (T18).

---

## Cost and latency caps

- **Timeout:** 30 seconds per call (constitution §12). The adapter will not accept `timeout_s > 30` (`le=30` on `ModelCallRequest`).
- **Max output tokens:** 4096 hard ceiling per call; the per-agent `max_output_tokens` pin in `configs/models.yaml` lowers the effective cap (`min(request, pin)`). The adapter will not accept a higher request value.
- **Per-session cost ceiling:** $5 in production. The orchestrator checks session aggregate cost before every LLM call; above the ceiling, the session state transitions to `SESSION_HALTED_COST_CEILING`.
- **Monthly budget alert:** $50, configured in GCP Billing. Alerts at 50%, 90%, 100%.

The price table (`llm/pricing.yaml`) is committed in repo and versioned. When Google changes prices, we update the table in a PR.

---

## Tracing

Every LLM call produces a `turn_trace` row with the following fields:

- `id`, `session_id`, `turn_id` (if applicable).
- `agent`, `model`, `model_version`.
- `system_prompt_hash`, `user_content_hash` (for dedup + replay) — not the full text, which is stored under a size-bounded `prompt_blob` column.
- `raw_output` (truncated to 8 KB; full output under a separate blob column if larger).
- `input_tokens`, `output_tokens`, `cost_usd`.
- `latency_ms`.
- `error_code` and `error_message` if the call failed.
- `created_at`.

This row is the basis for cost analysis, calibration replay (ADR-018), and regression detection.

---

## Vertex mock for dev and tests

The mock backend (`app/backend/llm/_mock_backend.py`) is **in-process** — no separate HTTP service, no docker-compose entry, no network I/O. The wrapper selects it via the runtime `LLM_BACKEND` env var (`mock` in dev/CI, `vertex` in prod). Production refuses to start with `LLM_BACKEND=mock` (FR-007 enforced by `Settings.assert_safe_for_environment()` at `app/backend/main.py` boot).

The mock:

- Computes a canonical SHA-256 of `{system_prompt, user_payload, json_schema, agent, model}` (sorted JSON encoding) — including the schema in the SHA prevents stale-fixture bugs across schema changes.
- Looks up `app/backend/tests/fixtures/llm_responses/<agent>/<sha256-hex>.json`. Each fixture envelope is `{text, input_tokens, output_tokens, model, model_version}`.
- On miss, writes the request envelope to `app/backend/tests/fixtures/llm_responses/_unrecorded/<sha>.json` and raises `RuntimeError("fixture missing for prompt SHA <hex>; see _unrecorded/<sha>.json")` so the developer can inspect what was asked, craft the desired response, and `git mv` it into the agent directory.

The promotion flow is documented in `app/backend/tests/fixtures/llm_responses/README.md`.

---

## Prompt assembly

Agent modules (`llm/agents/*`) own prompt assembly. Contract:

```python
def build_assessor_prompt(
    rubric_snapshot: RubricSnapshot,
    turn: Turn,
    prior_turns: list[Turn],
) -> LLMCall:
    ...
```

Each `build_*_prompt` function:

- Reads its system prompt text from `prompts/<agent>/<active_version>/system.md`.
- Applies variable substitution using an explicit context (no generic `{**context}`).
- Appends standardised footer (date, session context, role anchor).
- Returns a fully-populated `LLMCall`.

The active prompt version is pinned per environment in `configs/models.yaml`. A prompt change is a version bump, not an in-place edit (see `agent-prompt-edit` skill).

---

## Observability

Every `turn_trace` row is indexed so we can answer:

- "Show all calls for session X" — a common debugging query.
- "Cost over the last 24 hours by agent" — billing sanity.
- "p95 latency for Assessor over the last 7 days" — regression detection.
- "Rate of schema validation failures per model version" — calibration signal.

Dashboards live in Cloud Monitoring (see `./cloud-setup.md`). Critical alerts:

- Session cost ceiling hit — routed to on-call email.
- Error rate > 2% over 10 minutes — routed to on-call email.
- Latency p95 > 10s — routed to on-call email (may indicate a Vertex outage).

---

## When Vertex is down

Vertex outages happen. Our response:

1. The adapter returns `LLMUpstreamUnavailable` after retry exhaustion.
2. The orchestrator's state machine transitions the session to `SESSION_PAUSED_UPSTREAM`.
3. The candidate sees: "We are experiencing a brief pause. Please wait." (Ukrainian: stored in `prompts/shared/candidate-facing/pause.md`.)
4. A background retry loop polls Vertex health and resumes when green.
5. If the pause exceeds 3 minutes, the session is marked `SESSION_HALTED_UPSTREAM`, the recruiter is paged, and the candidate is informed that the session will be rescheduled.

All paused / halted sessions are preserved in full detail — nothing is lost.
