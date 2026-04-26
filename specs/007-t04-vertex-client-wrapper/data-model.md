# Phase 1 Data Model — Vertex AI Client Wrapper (T04)

T04 has **zero persistent rows**. Every entity below is either an in-process Pydantic model, a typed error class, a structural-typing `Protocol`, or a concrete in-memory implementation that ships with the wrapper. The "data model" exists so a reviewer can point at every typed surface that crosses module boundaries inside `app/backend/llm/`, validate its shape against the spec's FRs, and trace each invariant to its constitution principle.

Where a field is bound by a constitution principle, the principle is named in the field description column.

---

## 1. `ModelCallRequest` — input to the wrapper

**Module**: `app/backend/llm/vertex.py`  
**Type**: `pydantic.BaseModel` (immutable: `model_config = ConfigDict(frozen=True)`)  
**Lifecycle**: Constructed by the caller; passed by value to `call_model(...)`; immutable thereafter.

| Field             | Type                                          | Validation                                                                     | Spec FR / Constitution                            |
| ----------------- | --------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------- |
| `agent`           | `Literal["interviewer", "assessor", "planner"]` | Enum — only the three agents committed in `configs/models.yaml` at T04.       | FR-002, FR-019                                    |
| `system_prompt`   | `str`                                         | `min_length=1, max_length=64_000` (defensive; real prompts are ~2–8 KB).      | FR-002                                            |
| `user_payload`    | `str`                                         | `min_length=1, max_length=200_000` (covers worst-case CV + transcript).       | FR-002                                            |
| `json_schema`     | `dict[str, Any] \| None`                      | Optional. When set, structured-output mode is requested and the wrapper validates the parsed result. | FR-011                                            |
| `session_id`      | `UUID`                                        | Required (no default). Drives cost ledger attribution and trace correlation.   | FR-002, FR-012, §1 (auditability), §12             |
| `timeout_s`       | `int = 30`                                    | `Field(ge=1, le=30)` — Pydantic rejects out-of-range at construction, **before** any network I/O. | FR-002, FR-003, §12                                |
| `max_output_tokens` | `int = 4096`                                | `Field(ge=1, le=4096)` — Pydantic rejects at construction.                    | FR-002, §12                                        |
| `model_override`  | `str \| None`                                 | Optional. When set, overrides the agent's default model from `configs/models.yaml`. Used by tests and ad-hoc scripts; production callers leave it `None`. | FR-019                                            |

**Invariants**:

- Frozen instance — once constructed, fields cannot be mutated. The hash is stable, which lets the prompt-SHA computation use the request as part of its input.
- Out-of-cap values raise `pydantic.ValidationError` (which the wrapper re-raises as `ModelCallConfigError` for caller ergonomics) — the call function never executes for an invalid request.

---

## 2. `ModelCallResult` — output of the wrapper

**Module**: `app/backend/llm/vertex.py`  
**Type**: `pydantic.BaseModel` (immutable)  
**Lifecycle**: Returned from `call_model(...)` only on success; constructed by the wrapper after the trace record has been durably written.

| Field           | Type                            | Description                                                                                | Spec FR             |
| --------------- | ------------------------------- | ------------------------------------------------------------------------------------------ | ------------------- |
| `text`          | `str`                           | Raw response text (or the JSON-encoded string if structured-output mode).                  | FR-002              |
| `parsed`        | `dict[str, Any] \| None`        | Parsed and schema-validated payload. Only populated when the request had a `json_schema`.  | FR-011              |
| `input_tokens`  | `int`                           | Token count Vertex billed for input.                                                       | FR-008, FR-010      |
| `output_tokens` | `int`                           | Token count Vertex billed for output.                                                      | FR-008, FR-010      |
| `cost_usd`      | `Decimal`                       | Per-call cost computed from token counts × price-table. Always `> 0` on a successful call. | FR-010, FR-008, §12 |
| `latency_ms`    | `int`                           | Wall-clock time across all retry attempts. Always `<= 30_000`.                             | FR-003, §12         |
| `model`         | `str`                           | Resolved model identifier (e.g., `"gemini-2.5-flash"`).                                    | FR-008              |
| `model_version` | `str`                           | Specific model revision returned by Vertex (e.g., `"gemini-2.5-flash-001"`).               | FR-008              |
| `attempts`      | `int`                           | 1, 2, or 3 — how many backend calls happened. `1` on first-try success.                    | FR-004, FR-008      |
| `trace_id`      | `UUID`                          | The trace record's identifier — caller can persist this for downstream debugging.          | FR-008, FR-013      |

**Invariants**:

- Returned only on `outcome == "ok"` paths. On any wrapper-level error, the caller gets the typed exception instead of a `ModelCallResult`.
- `parsed is None` iff the request's `json_schema is None`.
- `trace_id` references a trace record that has already been written to the sink (sync write per Clarifications 2026-04-26).

---

## 3. `TraceRecord` — append-only audit row

**Module**: `app/backend/llm/trace.py`  
**Type**: `pydantic.BaseModel` (immutable; `frozen=True`)  
**Lifecycle**: Constructed by the wrapper at the end of each call attempt's terminal state; passed to `TraceSink.write(...)` synchronously; never mutated.

| Field           | Type                                                          | Description                                                                                                          | Spec FR / Constitution     |
| --------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| `id`            | `UUID`                                                        | Deterministic UUIDv4; stable identifier returned to the caller in `ModelCallResult.trace_id`.                       | FR-008                     |
| `created_at`    | `datetime` (timezone-aware, UTC)                              | Set by the wrapper at the moment of trace emission.                                                                 | FR-008                     |
| `agent`         | `Literal["interviewer", "assessor", "planner"]`              | Mirrors `ModelCallRequest.agent`.                                                                                   | FR-008                     |
| `session_id`    | `UUID`                                                        | Mirrors `ModelCallRequest.session_id`.                                                                              | FR-008, §1                 |
| `model`         | `str`                                                         | Resolved model identifier.                                                                                          | FR-008                     |
| `model_version` | `str \| None`                                                 | Specific revision returned by Vertex; `None` on a call that failed before getting a response.                       | FR-008                     |
| `prompt_sha256` | `str` (64 hex chars)                                          | Canonical prompt SHA-256 — see research §13.                                                                        | FR-008, FR-013, §15        |
| `outcome`       | `Literal["ok", "schema_error", "timeout", "upstream_unavailable", "budget_exceeded", "config_error", "trace_write_error"]` | One of the seven outcomes. `trace_write_error` is the recursive-failure outcome (the in-memory sink can't fail this way; the durable sink's failure produces this entry only via a fallback emergency log). | FR-008, FR-009              |
| `attempts`      | `int`                                                         | `1..3`.                                                                                                              | FR-004, FR-008              |
| `latency_ms`    | `int`                                                         | Wall-clock across all attempts.                                                                                     | FR-008                     |
| `input_tokens`  | `int`                                                         | `0` on `outcome != "ok"`.                                                                                           | FR-008                     |
| `output_tokens` | `int`                                                         | `0` on `outcome != "ok"`.                                                                                           | FR-008                     |
| `cost_usd`      | `Decimal`                                                     | `Decimal("0")` on `outcome in {"config_error", "budget_exceeded"}` (no upstream call); positive otherwise.          | FR-008, FR-010, §12         |
| `error_message` | `str \| None`                                                 | Short, PII-free error string for failed outcomes; `None` on `outcome == "ok"`. Never contains prompt or output text. | FR-008, FR-013, §15         |

**Invariants**:

- Frozen — once written, the record cannot be mutated. This is the type-system half of constitution §3 (the database half is enforced by `REVOKE UPDATE, DELETE` in T05).
- `cost_usd >= 0`.
- `prompt_sha256` is set even on `outcome == "config_error"` (so an operator can correlate failed attempts back to the offending caller pattern).

---

## 4. `Pricing` and `pricing.py` loader

**Module**: `app/backend/llm/pricing.py`

```python
class ModelPricing(BaseModel, frozen=True):
    input_per_1k_tokens: Decimal
    output_per_1k_tokens: Decimal

    @field_validator("input_per_1k_tokens", "output_per_1k_tokens")
    @classmethod
    def positive_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v

class PricingTable(BaseModel, frozen=True):
    models: dict[str, ModelPricing]

    def cost_for(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        if model not in self.models:
            raise ModelCallConfigError(f"unknown model {model!r} — add it to pricing.yaml")
        p = self.models[model]
        return (
            p.input_per_1k_tokens * Decimal(input_tokens) / Decimal(1000)
            + p.output_per_1k_tokens * Decimal(output_tokens) / Decimal(1000)
        )
```

**Invariants**:

- All prices are positive `Decimal`.
- Unknown model identifier raises `ModelCallConfigError` — never returns `Decimal("0")` (which would silently under-report cost — a §12 violation).
- Loaded once at process start (`PricingTable.from_yaml(path)`), then immutable for process lifetime.

---

## 5. `ModelConfig` and `ModelsConfig` (`configs/models.yaml` loader)

**Module**: `app/backend/llm/models_config.py`

```python
class ModelConfig(BaseModel, frozen=True):
    model: str
    prompt_version: str         # "v0001" placeholder until T17
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(ge=1, le=4096)

class ModelsConfig(BaseModel, frozen=True):
    interviewer: ModelConfig
    assessor: ModelConfig
    planner: ModelConfig

    def for_agent(self, agent: str) -> ModelConfig:
        if agent not in {"interviewer", "assessor", "planner"}:
            raise ModelCallConfigError(f"unknown agent {agent!r}")
        return getattr(self, agent)
```

**Invariants**:

- All three agents required at load time (T04 ships them all per Clarifications Q5).
- `temperature` in `[0.0, 2.0]`; `max_output_tokens` in `[1, 4096]` — out-of-range fails fast at YAML load.
- `prompt_version` is a non-empty string. The placeholder `"v0001"` satisfies this; T17 swaps in a real version.

---

## 6. Typed error hierarchy

**Module**: `app/backend/llm/errors.py`

```python
class WrapperError(Exception):
    """Base for every typed wrapper error. Catch this for blanket handling."""

class ModelCallConfigError(WrapperError):
    """Caller-side error: invalid request, unknown model, unknown agent."""

class VertexTimeoutError(WrapperError):
    """30-second wall-clock budget exceeded (across all retries)."""

class VertexUpstreamUnavailableError(WrapperError):
    """Retry budget exhausted on transient upstream failures."""

class VertexSchemaError(WrapperError):
    """Schema validation failed. Carries the raw payload for caller debugging.

    Per Clarifications 2026-04-26: wrapper does NOT retry on this error;
    agent modules apply their own per-agent policies (Assessor, Planner,
    Interviewer each have different policies per vertex-integration.md).
    """
    def __init__(self, message: str, *, raw_payload: str) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload

class SessionBudgetExceeded(WrapperError):
    """Per-session cost ceiling tripped before this call (constitution §12)."""

class TraceWriteError(WrapperError):
    """Trace sink failed to persist a record. Per Clarifications 2026-04-26
    the wrapper raises this rather than swallowing — auditability (§1) is
    non-negotiable. The orchestrator (T20) treats this as a session-halting
    condition.
    """
```

**Invariants**:

- Single root (`WrapperError`) makes `except WrapperError:` a complete handler for any wrapper-side failure.
- Each error class maps to exactly one `outcome` value in the trace record (see the table in §3).
- `VertexSchemaError.raw_payload` is the only error attribute carrying potentially sensitive content — it is **not** logged by the wrapper (caller is responsible).

**Mapping from error to trace `outcome`**:

| Error                            | Trace `outcome`        |
| -------------------------------- | ---------------------- |
| `ModelCallConfigError`           | `config_error`         |
| `VertexTimeoutError`             | `timeout`              |
| `VertexUpstreamUnavailableError` | `upstream_unavailable` |
| `VertexSchemaError`              | `schema_error`         |
| `SessionBudgetExceeded`          | `budget_exceeded`      |
| `TraceWriteError`                | `trace_write_error`    |
| (no error → success)             | `ok`                   |

---

## 7. `VertexBackend` protocol and concrete backends

**Module**: `app/backend/llm/_backend_protocol.py` (the protocol), `_real_backend.py`, `_mock_backend.py` (the concretions)

```python
class RawBackendResult(BaseModel, frozen=True):
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    model_version: str

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

**Concretions**:

- `RealVertexBackend` (in `_real_backend.py`): wraps `google.genai.Client(vertexai=True, location="europe-west1").aio.models.generate_content(...)`. The **only** non-test module allowed to import a model-provider SDK (per the static guardrail).
- `MockVertexBackend` (in `_mock_backend.py`): computes prompt-SHA per research §13, looks up `<fixtures_dir>/<agent>/<sha>.json`, returns the parsed envelope as `RawBackendResult`. On miss, writes the request envelope under `<fixtures_dir>/_unrecorded/<sha>.json` and raises a clear `RuntimeError("fixture missing for prompt SHA <hex>; see _unrecorded/<sha>.json")`.

**Invariants**:

- Both backends implement the protocol structurally — no inheritance from `VertexBackend`.
- The mock backend has zero network I/O; can run inside `docker-compose -f docker-compose.test.yml run` without any GCP credential.
- The real backend raises `google.api_core.exceptions.*` on upstream failures — the wrapper translates these to `VertexUpstreamUnavailableError` / `VertexTimeoutError` / `ModelCallConfigError` based on type.

---

## 8. `TraceSink` protocol and `InMemoryTraceSink`

**Module**: `app/backend/llm/trace.py`

```python
class TraceSink(Protocol):
    async def write(self, record: TraceRecord) -> None: ...

class InMemoryTraceSink:
    def __init__(self, *, capacity: int = 10_000) -> None:
        self._records: list[TraceRecord] = []
        self._capacity = capacity

    async def write(self, record: TraceRecord) -> None:
        if len(self._records) >= self._capacity:
            raise TraceWriteError(
                f"in-memory trace sink at capacity ({self._capacity})"
            )
        self._records.append(record)

    @property
    def records(self) -> list[TraceRecord]:
        return list(self._records)  # defensive copy
```

**Invariants**:

- `write` is async (uniform with the future durable Postgres sink); the in-memory body is sync internally.
- `records` returns a defensive copy — caller can't mutate the internal list.
- `TraceWriteError` is raised on capacity exhaustion (a programmer-error condition for in-memory; the durable T05 sink raises it on DB failure).

---

## 9. `CostLedger` protocol and `InMemoryCostLedger`

**Module**: `app/backend/llm/cost_ledger.py`

```python
class CostLedger(Protocol):
    async def session_total(self, session_id: UUID) -> Decimal: ...
    async def add(self, session_id: UUID, cost_usd: Decimal) -> None: ...

class InMemoryCostLedger:
    def __init__(self) -> None:
        self._totals: dict[UUID, Decimal] = {}
        self._lock = asyncio.Lock()

    async def session_total(self, session_id: UUID) -> Decimal:
        return self._totals.get(session_id, Decimal("0"))

    async def add(self, session_id: UUID, cost_usd: Decimal) -> None:
        if cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")
        async with self._lock:
            self._totals[session_id] = self._totals.get(session_id, Decimal("0")) + cost_usd
```

**Invariants**:

- `session_total` is `Decimal("0")` for an unknown session (safe default — first call for a session sees zero, then `add()` records its cost).
- `add` is guarded by an `asyncio.Lock` so concurrent calls within one event loop sum correctly. (Multi-process safety is a T05 concern — the durable sink uses Postgres atomic increments.)
- Non-negative cost only; the wrapper passes `Decimal("0")` for trace records of failed calls (which means the wrapper does NOT increment the ledger on failures — so a failing session can't burn budget).

---

## 10. `Settings` (pydantic-settings env loader)

**Module**: `app/backend/settings.py`

```python
class Settings(BaseSettings):
    llm_backend: Literal["mock", "vertex"] = "mock"
    app_env: Literal["dev", "test", "prod"] = "dev"
    llm_budget_per_session_usd: Decimal = Decimal("5.00")
    llm_fixtures_dir: Path = Path("app/backend/tests/fixtures/llm_responses")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def assert_safe_for_environment(self) -> None:
        if self.app_env == "prod":
            if self.llm_backend == "mock":
                raise RuntimeError(
                    "FR-007: LLM_BACKEND=mock is not allowed when APP_ENV=prod"
                )
            if self.llm_budget_per_session_usd > Decimal("5.00"):
                raise RuntimeError(
                    "constitution §12: LLM_BUDGET_PER_SESSION_USD must not exceed $5.00 in production"
                )
```

**Invariants**:

- Defaults are non-secret per ADR-022 and shipped in `.env.example`.
- `assert_safe_for_environment()` is called once from `app/backend/main.py` module init — production startup fails fast (FR-007, SC-010).
- The `Path` is relative to repo root; the in-process `MockVertexBackend` resolves it via the `Settings` instance the caller passes in.

---

## Summary

| Surface                        | Type                | Lifecycle  | Spec anchor               |
| ------------------------------ | ------------------- | ---------- | ------------------------- |
| `ModelCallRequest`             | `BaseModel` (frozen) | per-call   | FR-002, FR-019            |
| `ModelCallResult`              | `BaseModel` (frozen) | per-call   | FR-002, FR-008            |
| `TraceRecord`                  | `BaseModel` (frozen) | per-call   | FR-008, §1, §3            |
| `ModelPricing`, `PricingTable` | `BaseModel` (frozen) | process    | FR-010, §16               |
| `ModelConfig`, `ModelsConfig`  | `BaseModel` (frozen) | process    | FR-019, §16               |
| `WrapperError` and 6 children  | `Exception`         | per-failure | FR-002–FR-014, §12, §15  |
| `VertexBackend` (Protocol)     | structural type     | n/a        | FR-005                    |
| `RawBackendResult`             | `BaseModel` (frozen) | per-call   | FR-005, FR-006            |
| `RealVertexBackend`            | concrete class      | process    | FR-005, FR-014, FR-015    |
| `MockVertexBackend`            | concrete class      | process    | FR-005, FR-006, FR-007    |
| `TraceSink` (Protocol)         | structural type     | n/a        | FR-009, §1                |
| `InMemoryTraceSink`            | concrete class      | process    | FR-009                    |
| `CostLedger` (Protocol)        | structural type     | n/a        | FR-012                    |
| `InMemoryCostLedger`           | concrete class      | process    | FR-012                    |
| `Settings`                     | `BaseSettings`      | process    | FR-007, FR-019, ADR-022   |

No persistent rows. No migration. No DB models. T05 will replace the in-memory `TraceSink` and `CostLedger` implementations with Postgres-backed ones, leaving every other surface in this document unchanged.
