# Vertex AI Integration

This document describes how TechScreen calls Google Vertex AI for every LLM-driven operation. The goal is to make every call observable, bounded, and replaceable.

Related: [ADR-002](../adr/002-llm-provider-vertex-ai.md), [ADR-003](../adr/003-model-selection-gemini-flash-pro.md), [constitution §12](../.specify/memory/constitution.md).

---

## Scope

Everything that talks to a large language model goes through the Vertex adapter at `app/backend/llm/vertex.py`. Application code never:

- Calls Google AI Studio, Anthropic, or OpenAI APIs directly.
- Embeds API keys or credentials in source (constitution §5).
- Bypasses cost or latency caps.
- Skips persisting a `turn_trace` row for a call that reached the network.

---

## Layer structure

```
services/*        business-facing API, takes domain objects
    ↓ calls
llm/agents/*      one module per agent (interviewer, assessor, planner)
                  owns prompt assembly, response parsing, schema validation
    ↓ calls
llm/vertex.py     the adapter — retries, timeouts, cost tracking, tracing
    ↓ calls
Vertex AI API     via google-cloud-aiplatform SDK
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
2. Enforces the timeout (a hard upper bound; no caller can pass > 60s).
3. Enforces `max_output_tokens` (caller may request lower, never higher).
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

The adapter retries on this set of errors only:

| Error | Retries | Backoff |
| --- | --- | --- |
| `google.api_core.exceptions.ServiceUnavailable` | 3 | 0.5s, 1s, 2s (jittered) |
| `google.api_core.exceptions.DeadlineExceeded` | 1 | 2s |
| `google.api_core.exceptions.ResourceExhausted` | 2 | 4s, 8s |
| Connection errors / timeouts at the HTTP layer | 3 | 0.5s, 1s, 2s |

The adapter does **not** retry on:

- `InvalidArgument` — the request is malformed; retrying will not help.
- `PermissionDenied` — auth is broken; log and escalate.
- Schema validation failures (these are thrown by the agent module, not the adapter).

Total time across retries is still bounded by `timeout_s` on the call.

---

## JSON mode

When `json_schema` is provided the adapter:

1. Uses Vertex's native JSON output mode (`response_mime_type = "application/json"` + `response_schema`).
2. Validates the result against the schema using `pydantic.TypeAdapter`.
3. On validation failure, raises `LLMSchemaError` with the raw text attached for debugging — the adapter itself does not retry on schema failures.

Agent modules decide whether to retry on schema failure. Typically:

- **Assessor:** retry up to once with temperature bumped to 0.1 on schema failure. If still failing, mark the assessment as `needs_manual_review` and enqueue.
- **Planner:** retry up to twice; on repeated failure, fall back to the previous rubric version's default plan template.
- **Interviewer:** no retry — partial or malformed output is truncated and surfaced with a recruiter escalation flag.

---

## Cost and latency caps

- **Timeout:** 30 seconds per call (constitution §12). The adapter will not accept `timeout_s > 60`.
- **Max output tokens:** 4096 per call. The adapter will not accept a higher value.
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

In `docker-compose.yml` a `vertex-mock` service runs a minimal HTTP stub that returns deterministic responses keyed on the SHA of the input prompt. The mock:

- Lives at `app/backend/llm/_mock_server.py`.
- Is reachable at `http://vertex-mock:8080` inside the compose network.
- Uses fixture files under `app/backend/tests/fixtures/llm_responses/` — one JSON file per (agent, prompt-hash) pair.
- Records any unseen prompt hash into `tests/fixtures/llm_responses/_unrecorded/` so a developer can promote it into a proper fixture.

A helper script `scripts/llm/record-fixture.sh` replays a given session id through a real Vertex call and writes the response as a new fixture.

The adapter chooses `vertex-mock` vs real Vertex based on `LLM_BACKEND` env var: `mock` in dev/CI, `vertex` in prod. Production refuses to start with `LLM_BACKEND=mock`.

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

Dashboards live in Cloud Monitoring (see `docs/cloud-setup.md`). Critical alerts:

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
