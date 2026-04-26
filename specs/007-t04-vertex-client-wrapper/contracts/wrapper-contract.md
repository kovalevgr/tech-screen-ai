# Wrapper Contract — Vertex AI Client Wrapper (T04)

This document defines the **eleven surfaces** T04 commits to. Every later LLM-touching task (T17 prompt artefacts, T18 Interviewer service, T19 Assessor service, T20 orchestrator, T21 Planner service, T11 Tier-1 deploy gate's `/debug/vertex-ping`, the `calibration-run` skill) consumes these surfaces unchanged. No surface defined here may be silently broken — a breaking change requires a new ADR.

The runtime artefacts (the wrapper module, fixture files, `pricing.yaml`, `configs/models.yaml`, the guardrail script) are **not** duplicated under this directory — that would create two sources of truth that would drift. This document references the runtime paths and pins their shape.

---

## §1. Public call surface

The single sanctioned entry point. Imported as:

```python
from app.backend.llm import call_model, ModelCallRequest, ModelCallResult
from app.backend.llm.errors import (
    WrapperError, ModelCallConfigError,
    VertexTimeoutError, VertexUpstreamUnavailableError,
    VertexSchemaError, SessionBudgetExceeded, TraceWriteError,
)
```

### Signature

```python
async def call_model(
    request: ModelCallRequest,
    *,
    sink: TraceSink,
    ledger: CostLedger,
    settings: Settings,
) -> ModelCallResult: ...
```

### Behaviour contract

| Step | Action                                                                                                                                                  | On failure                                                                                          |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| 1    | Validate `request` against pydantic constraints (caps from §12).                                                                                        | `pydantic.ValidationError` → wrapper re-raises as `ModelCallConfigError`. Trace written. No backend call. |
| 2    | Resolve `ModelConfig` for `request.agent` from `configs/models.yaml`.                                                                                   | Unknown agent → `ModelCallConfigError`. Trace written. No backend call.                              |
| 3    | Look up `ModelPricing` for the resolved (or overridden) model in `pricing.yaml`.                                                                        | Unknown model → `ModelCallConfigError`. Trace written. No backend call.                              |
| 4    | Consult `ledger.session_total(request.session_id)`. If `>= settings.llm_budget_per_session_usd`, short-circuit.                                          | `SessionBudgetExceeded` raised. Trace written with `outcome="budget_exceeded"`, `cost_usd=0`. No backend call. |
| 5    | Choose backend: `MockVertexBackend` if `settings.llm_backend == "mock"`, otherwise `RealVertexBackend`.                                                  | n/a                                                                                                 |
| 6    | Wrap the backend call in `tenacity.AsyncRetrying` with the §2 retry policy and the `request.timeout_s` wall-clock timeout (`asyncio.wait_for`).         | Retry budget exhausted on transient → `VertexUpstreamUnavailableError`. Wall-clock expired → `VertexTimeoutError`. Trace written. |
| 7    | If `request.json_schema is not None`, validate the parsed dict via `pydantic.TypeAdapter(dict).validate_python(...)` against the schema (Stage 2).      | `pydantic.ValidationError` → `VertexSchemaError(raw_payload=raw.text)`. **No retry** (per Clarifications 2026-04-26). Trace written. |
| 8    | Compute `cost_usd = pricing.cost_for(model, raw.input_tokens, raw.output_tokens)`. Increment `ledger.add(session_id, cost_usd)`.                        | n/a (Decimal arithmetic, never fails)                                                               |
| 9    | Build `TraceRecord` with `outcome="ok"` and call `sink.write(record)` synchronously.                                                                    | Sink failure → `TraceWriteError` raised. The successful upstream call is **NOT** returned to the caller — auditability (§1) is non-negotiable. |
| 10   | Return `ModelCallResult` to caller.                                                                                                                     | n/a                                                                                                 |

### Error envelope

Every error class is a subclass of `WrapperError`. Callers can `except WrapperError` for blanket handling, or catch specific subclasses for per-error policy. Schema-error specifically: `except VertexSchemaError as e:` exposes `e.raw_payload` for caller-side debugging or per-agent retry (Assessor with bumped temperature, Planner with fallback, Interviewer with escalation flag — see `vertex-integration.md`).

### Idempotency note

`call_model` has **no side effects beyond** (a) the upstream Vertex call, (b) one trace-record write, (c) one cost-ledger increment. Two identical successful calls produce two trace records and two ledger increments — this is by design (every attempt is auditable).

---

## §2. Backend protocol

Both the real and mock backends implement this protocol structurally (no inheritance). The protocol module is `app/backend/llm/_backend_protocol.py`.

```python
class VertexBackend(Protocol):
    async def generate(
        self,
        *,
        system_prompt: str,
        user_payload: str,
        json_schema: dict[str, Any] | None,
        model: str,
        temperature: float,
        max_output_tokens: int,
        timeout_s: float,
    ) -> RawBackendResult: ...
```

**Allowed implementations** (per the static guardrail):

- `app/backend/llm/_real_backend.py` — `RealVertexBackend`. The **only** non-test module allowed to import a model-provider SDK.
- `app/backend/llm/_mock_backend.py` — `MockVertexBackend`. Self-contained; never reaches the network.

### Retry policy (§2 of research)

```python
RETRY_BUDGET = AsyncRetrying(
    retry=retry_if_exception_type((
        google.api_core.exceptions.ServiceUnavailable,
        google.api_core.exceptions.InternalServerError,
        google.api_core.exceptions.ResourceExhausted,
        ConnectionError,
    )),
    stop=stop_after_attempt(3),                      # 1 initial + 2 retries
    wait=wait_exponential_jitter(initial=0.5, max=4.0),
    reraise=True,
)
```

`google.api_core.exceptions.DeadlineExceeded` is **excluded** — the timeout already fired; retrying just burns the remaining wall-clock budget.

`google.api_core.exceptions.InvalidArgument` and `google.api_core.exceptions.PermissionDenied` are **not retried**; they bubble up as `ModelCallConfigError`.

---

## §3. Error contract

| Error                            | When                                                                                                       | Carries                  | Trace `outcome`        |
| -------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------ | ---------------------- |
| `ModelCallConfigError`           | Out-of-cap request; unknown agent; unknown model; missing `session_id`; auth misconfiguration.             | error message            | `config_error`         |
| `VertexTimeoutError`             | 30-second wall-clock budget across all retries exceeded.                                                   | error message            | `timeout`              |
| `VertexUpstreamUnavailableError` | Retry budget (3 attempts) exhausted on transient errors.                                                   | error message            | `upstream_unavailable` |
| `VertexSchemaError`              | Caller passed `json_schema`; parsed payload failed Stage-2 pydantic validation.                            | `raw_payload: str`       | `schema_error`         |
| `SessionBudgetExceeded`          | Per-session cost ledger total ≥ ceiling at start of call.                                                  | error message            | `budget_exceeded`      |
| `TraceWriteError`                | Trace sink raised when wrapper called `sink.write(record)`.                                                | error message            | `trace_write_error`    |

All errors are `WrapperError` subclasses → `except WrapperError:` is a complete catch.

---

## §4. `configs/models.yaml` schema

Path: `configs/models.yaml` (new top-level `configs/` directory; created in this PR).

### Shape

```yaml
<agent>:
  model: <string>                  # one of: "gemini-2.5-flash", "gemini-2.5-pro" (the keys committed in pricing.yaml)
  prompt_version: <string>         # opaque version identifier; "v0001" placeholder until T17 lands prompts/<agent>/v0001/
  temperature: <float>             # range [0.0, 2.0]
  max_output_tokens: <int>         # range [1, 4096]
```

### Required agents (T04 ships all three per Clarifications Q5)

```yaml
interviewer:
  model: gemini-2.5-flash
  prompt_version: "v0001"
  temperature: 0.4
  max_output_tokens: 2048

assessor:
  model: gemini-2.5-flash
  prompt_version: "v0001"
  temperature: 0.1
  max_output_tokens: 2048

planner:
  model: gemini-2.5-pro
  prompt_version: "v0001"
  temperature: 0.3
  max_output_tokens: 4096
```

### Loader behaviour (`app/backend/llm/models_config.py`)

- Loaded once at process start; immutable thereafter.
- Missing agent → `ModelCallConfigError` at load.
- Out-of-range `temperature` or `max_output_tokens` → `ModelCallConfigError` at load (caps from constitution §12).
- Unknown agent in `for_agent(name)` → `ModelCallConfigError` at runtime.

---

## §5. `pricing.yaml` schema

Path: `app/backend/llm/pricing.yaml` (lives next to the wrapper module so it's clearly a wrapper-internal data file, not a user-editable config).

### Shape

```yaml
<model_id>:
  input_per_1k_tokens: "<decimal-as-string>"
  output_per_1k_tokens: "<decimal-as-string>"
```

### Committed entries (per ADR-003 / ADR-015, region `europe-west1`)

```yaml
gemini-2.5-flash:
  input_per_1k_tokens: "0.000075"
  output_per_1k_tokens: "0.000300"

gemini-2.5-pro:
  input_per_1k_tokens: "0.00125"
  output_per_1k_tokens: "0.00500"
```

Prices are **strings** in YAML; the loader parses them into `Decimal` (research §6) — storing as floats would defeat the precision choice.

### Loader behaviour (`app/backend/llm/pricing.py`)

- Loaded once at process start; immutable thereafter.
- Non-positive price → `ModelCallConfigError` at load.
- `cost_for(model, ...)` for unknown model → `ModelCallConfigError` (FR-010 — never returns 0).

---

## §6. Environment contract

Settings keys read from environment / `.env` file:

| Key                            | Type      | Default              | Production constraint                                       | Spec FR / Anchor      |
| ------------------------------ | --------- | -------------------- | ----------------------------------------------------------- | --------------------- |
| `LLM_BACKEND`                  | enum      | `mock`               | MUST be `vertex` in production. `mock` raises at startup.   | FR-005, FR-007, SC-010 |
| `APP_ENV`                      | enum      | `dev` (T01 default)  | One of `dev`/`test`/`prod`. The canonical runtime selector — already set by `Dockerfile` and every `docker-compose*.yml` from T01. `Settings` reads it; `prod` triggers the FR-007 + §12 guards. | FR-007, SC-010         |
| `LLM_BUDGET_PER_SESSION_USD`   | Decimal   | `5.00`               | MUST NOT exceed `5.00` in production.                       | FR-012, §12            |
| `LLM_FIXTURES_DIR`             | Path      | `app/backend/tests/fixtures/llm_responses` | Ignored when `LLM_BACKEND=vertex`.                          | FR-006                 |

All four are non-secret per ADR-022. T04 adds three of them to `.env.example` (LLM_BACKEND, LLM_BUDGET_PER_SESSION_USD, LLM_FIXTURES_DIR); `APP_ENV` is reused unchanged from T01.

### Startup check

```python
# app/backend/main.py
from app.backend.settings import Settings
Settings().assert_safe_for_environment()  # raises RuntimeError if production+mock or budget>5
```

The assertion happens at module init, **before** FastAPI starts serving — Cloud Run sees a process that exits with non-zero rather than a process that serves degraded.

---

## §7. Trace record schema

Path: `app/backend/llm/trace.py` defines `TraceRecord` (see [data-model.md §3](../data-model.md#3-tracerecord--append-only-audit-row) for the full field list).

### Outcome enum (frozen at T04)

`Literal["ok", "schema_error", "timeout", "upstream_unavailable", "budget_exceeded", "config_error", "trace_write_error"]`

Adding a new outcome requires a coordinated PR that touches: this contract, `data-model.md`, `errors.py`, the wrapper's outcome-mapping switch, and (in T05+) the durable sink's storage schema.

### Prompt SHA recipe (frozen at T04)

```python
def canonical_prompt_sha(req: ModelCallRequest, *, model: str) -> str:
    payload = json.dumps(
        {
            "system_prompt": req.system_prompt,
            "user_payload": req.user_payload,
            "json_schema": req.json_schema,
            "agent": req.agent,
            "model": model,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

Including the schema and model in the SHA prevents stale-fixture bugs (research §13).

### What is NOT in the trace record

- Raw prompt text — only the SHA.
- Raw model output text — only token counts.
- Candidate PII — never (constitution §15).
- Credentials — never.

Operators look up the prompt content via the trace ID + the `_unrecorded/` directory in dev or via a future trace-content table in prod (T05+ scope, not T04).

---

## §8. Cost ledger contract

Path: `app/backend/llm/cost_ledger.py` defines the `CostLedger` protocol and `InMemoryCostLedger` implementation (see [data-model.md §9](../data-model.md#9-costledger-protocol-and-inmemorycostledger)).

### Behaviour

- `session_total(session_id)` returns `Decimal("0")` for an unknown session — first-call-for-session sees zero.
- `add(session_id, cost_usd)` is monotonic — only increments. The wrapper passes `Decimal("0")` for failed-call traces (so failures don't burn budget).
- The in-memory implementation uses an `asyncio.Lock` — concurrent `add` calls within one event loop sum correctly.
- Multi-process coordination is a T05 concern (durable sink uses Postgres atomic `UPDATE ... SET total = total + $cost`).

### Budget-exceeded short-circuit (FR-012)

```python
current = await ledger.session_total(req.session_id)
if current >= settings.llm_budget_per_session_usd:
    raise SessionBudgetExceeded(
        f"session {req.session_id} at {current} ≥ ceiling {settings.llm_budget_per_session_usd}"
    )
```

The check is **before any backend call** — no upstream cost is incurred when the ceiling is hit. The trace record is still written (with `outcome="budget_exceeded"`, `cost_usd=0`).

---

## §9. Mock fixture format

Path: `app/backend/tests/fixtures/llm_responses/<agent>/<sha256-hex>.json` (per research §5).

### Envelope

```json
{
  "text": "...",
  "input_tokens": 132,
  "output_tokens": 87,
  "model": "gemini-2.5-flash",
  "model_version": "gemini-2.5-flash-001"
}
```

For JSON-mode calls, `text` contains the JSON-encoded string the wrapper will parse. For non-JSON calls, `text` is the plain text.

### Schema-INVALID fixture

Used by the schema-miss test: `text` is a JSON-encoded object that's missing a required field of the schema the test passes. Filename is the SHA of the prompt + the (deliberately broken-fixture-paired) schema, so the same prompt + schema lookup hits this fixture.

### `_unrecorded/` capture rule

When the mock backend receives a prompt whose SHA is not in the fixture set:

1. Compute the canonical envelope: `{system_prompt, user_payload, json_schema, agent, model}`.
2. Write `<fixtures_dir>/_unrecorded/<sha>.json` with the envelope (so a developer can inspect what was asked).
3. Raise `RuntimeError("fixture missing for prompt SHA <hex>; see _unrecorded/<sha>.json")`.

The `_unrecorded/` directory is committed (with a `.gitkeep` file); contents are `.gitignore`d at the directory level (only the `.gitkeep` is tracked).

### Promotion flow (documented in `app/backend/tests/fixtures/llm_responses/README.md`)

1. Run the failing test → mock writes `_unrecorded/<sha>.json`.
2. Manually craft the desired response (or replay against real Vertex via a one-off script in T17+ scope).
3. `mv _unrecorded/<sha>.json <agent>/<sha>.json`.
4. Re-run the test → green.

### Production never reaches this code

Production refuses to start in mock mode (FR-007 / SC-010). The `_unrecorded/` directory exists only for dev and CI.

---

## §10. Test matrix

The FR-017 scenarios mapped to specific test names in `app/backend/tests/llm/test_vertex_wrapper.py`. A reviewer running `docker compose -f docker-compose.test.yml run --rm backend pytest app/backend/tests/llm/test_vertex_wrapper.py -v` should see each of these pass (and a single failed assertion in any one of them is grounds for blocking the PR).

| Test name                                                  | Asserts                                                                                                                                     | Spec FR / SC          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------- |
| `test_successful_call_with_schema_returns_parsed_json`     | Mock returns valid JSON; wrapper parses + Stage-2 validates; result has `parsed is not None`; one trace with `outcome="ok"`.                 | FR-002, FR-011, FR-017a |
| `test_timeout_above_30s_rejected_at_construction`          | `ModelCallRequest(timeout_s=31)` raises `pydantic.ValidationError`; wrapper never called.                                                    | FR-002, FR-017b, SC-002 |
| `test_max_tokens_above_4096_rejected_at_construction`      | `ModelCallRequest(max_output_tokens=4097)` raises `pydantic.ValidationError`; wrapper never called.                                          | FR-002, FR-017b, SC-002 |
| `test_schema_miss_raises_immediately_with_raw_payload`     | Mock returns schema-invalid JSON; wrapper raises `VertexSchemaError(raw_payload=...)` on **first** attempt; one trace with `outcome="schema_error"`. | FR-011, FR-017c (per Clarifications) |
| `test_session_at_budget_raises_before_backend_call`        | Ledger seeded at $5.00; `call_model` raises `SessionBudgetExceeded` without invoking the mock backend; trace `outcome="budget_exceeded"`, `cost_usd=0`. | FR-012, FR-017d, SC-006 |
| `test_unknown_agent_raises_config_error`                   | `ModelCallRequest(agent="unknown")` — caught at pydantic enum validation; `ModelCallConfigError` re-raised by wrapper.                       | FR-019                 |
| `test_unknown_model_override_raises_config_error`          | `ModelCallRequest(..., model_override="gemini-no-such")` raises `ModelCallConfigError` from pricing-table lookup.                            | FR-010                 |
| `test_trace_sink_failure_raises_trace_write_error`         | Sink configured to raise; wrapper raises `TraceWriteError` even on otherwise-successful upstream call.                                       | FR-009, §1             |
| `test_one_trace_per_invocation_in_every_scenario`          | Parametrised over the seven outcomes; asserts `len(sink.records) == 1` after each.                                                            | FR-008, SC-004         |
| `test_log_event_carries_no_prompt_text_no_pii`             | Capture log records during a call; assert no log line contains `system_prompt`, `user_payload`, or any value matching the email regex.       | FR-013, §15            |

Plus the supporting tests in adjacent files:

- `test_pricing.py` — load valid YAML; reject unknown model in `cost_for`.
- `test_models_config.py` — load valid YAML; reject missing agent; reject out-of-range temperature.
- `test_mock_backend.py` — fixture loading; SHA stability across Python invocations; `_unrecorded` capture writes the file; canonical SHA includes the schema.
- `test_trace_sink.py` — capacity bound raises `TraceWriteError`.
- `test_cost_ledger.py` — first call returns 0; concurrent `add` calls sum correctly.
- `test_no_provider_sdk_imports.py` — runs the guardrail script; passes on the post-T04 tree; fails when a fixture file with `import vertexai` is temporarily added under `app/backend/services/`.
- `test_settings.py` — production+mock raises at startup; production+budget>5 raises at startup; defaults load correctly.

---

## §11. Static-guardrail contract

Path: `scripts/check-no-provider-sdk-imports.sh` (full script in research §8).

### Allowlist

- `app/backend/llm/_real_backend.py` — may import `google.genai`, `vertexai`, `google.cloud.aiplatform`.
- `app/backend/llm/_mock_backend.py` — reserved for future mock variants (currently imports nothing real).

### Blocked patterns

- `^import (vertexai|google\.genai|google\.cloud\.aiplatform|anthropic|openai)`
- `^from (vertexai|google\.genai|google\.cloud\.aiplatform|anthropic|openai)`

### Scope

Backend Python only — `app/backend/**/*.py`. Tests are not exempt; if a test needs to import the SDK, it must do so via `RealVertexBackend` (which is integration-tested separately; T04's tests use `MockVertexBackend`).

### Failure output

```
ERROR: model-provider SDK imported outside the canonical wrapper:
./app/backend/services/foo.py:12: from vertexai import preview
```

The pre-commit hook and the CI step both invoke the same script, exit non-zero, and surface the violation.

---

## Summary

11 surfaces, all stable across the lifetime of the wrapper. T17–T21 build on them; T05 swaps the in-memory sink and ledger implementations for Postgres-backed ones without touching any other surface. Adding a new agent is a `configs/models.yaml` PR + (eventually) a `prompts/<agent>/<version>/` PR; adding a new model is a `pricing.yaml` PR. Neither requires a wrapper code change.
