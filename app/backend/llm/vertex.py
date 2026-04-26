"""The Vertex AI client wrapper — the single sanctioned LLM doorway.

Implements the 10-step behaviour contract in
`specs/007-t04-vertex-client-wrapper/contracts/wrapper-contract.md` §1.

Every model token that leaves a TechScreen process MUST traverse
:func:`call_model`. The wrapper enforces:

- Constitution §12 hard caps (timeout ≤ 30 s, max output tokens ≤ 4096)
  via Pydantic validation on :class:`ModelCallRequest` — rejected before
  any network I/O.
- A uniform 3-attempt retry budget on transient upstream failures
  (HTTP 5xx, HTTP 429, connection-level errors); ``DeadlineExceeded`` is
  excluded from retry per Clarifications 2026-04-26.
- A 30-second wall-clock cap across all retries via
  :func:`asyncio.wait_for`.
- Two-stage JSON-schema validation (SDK-side ``response_schema`` +
  wrapper-side :class:`pydantic.TypeAdapter`); schema miss raises
  :class:`VertexSchemaError` immediately with the raw payload — wrapper
  does NOT retry (per-agent retry policies live in agent modules).
- Per-session cost ceiling (constitution §12, default $5 USD) consulted
  before every backend call.
- Synchronous trace-record write before returning (constitution §1 —
  auditability is non-negotiable). Sink failure raises
  :class:`TraceWriteError`.
- One ``llm_call`` structlog event per terminal state, carrying only
  trace-id + non-PII metadata (constitution §15). Zero prompt text, zero
  output text, zero candidate identity.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Final
from uuid import UUID, uuid4

import structlog
from google.api_core import exceptions as gae
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from app.backend.llm._backend_protocol import RawBackendResult, VertexBackend
from app.backend.llm._mock_backend import MockVertexBackend, canonical_prompt_sha
from app.backend.llm._real_backend import RealVertexBackend
from app.backend.llm.cost_ledger import CostLedger
from app.backend.llm.errors import (
    ModelCallConfigError,
    SessionBudgetExceeded,
    TraceWriteError,
    VertexSchemaError,
    VertexTimeoutError,
    VertexUpstreamUnavailableError,
    WrapperError,
)
from app.backend.llm.models_config import MODELS_YAML_PATH, ModelsConfig
from app.backend.llm.pricing import PRICING_YAML_PATH, PricingTable
from app.backend.llm.trace import TraceOutcome, TraceRecord, TraceSink
from app.backend.settings import Settings

_LOGGER = structlog.get_logger("app.backend.llm.vertex")


# ---------------------------------------------------------------------------
# Public typed call surface
# ---------------------------------------------------------------------------


class ModelCallRequest(BaseModel):
    """Typed input to :func:`call_model`. Frozen — hashable for SHA recipes."""

    model_config = ConfigDict(frozen=True)

    agent: str = Field(min_length=1)
    """One of ``"interviewer" | "assessor" | "planner"`` (validated against
    ``configs/models.yaml`` at call time)."""

    system_prompt: str = Field(min_length=1, max_length=64_000)
    user_payload: str = Field(min_length=1, max_length=200_000)
    json_schema: dict[str, Any] | None = None

    session_id: UUID
    """Drives cost-ledger attribution and trace correlation. No default."""

    timeout_s: int = Field(default=30, ge=1, le=30)
    """Per-call wall-clock cap. Hard ceiling 30 s per constitution §12."""

    max_output_tokens: int = Field(default=4096, ge=1, le=4096)
    """Hard ceiling 4096 per constitution §12."""

    model_override: str | None = None
    """Test/script-only escape hatch; production callers leave this ``None``."""


class ModelCallResult(BaseModel):
    """Typed output of :func:`call_model`. Returned only on ``outcome == "ok"``."""

    model_config = ConfigDict(frozen=True)

    text: str
    parsed: dict[str, Any] | None
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cost_usd: Decimal
    latency_ms: int = Field(ge=0)
    model: str
    model_version: str
    attempts: int = Field(ge=1, le=3)
    trace_id: UUID


# ---------------------------------------------------------------------------
# Retry policy (constitution §12 + spec FR-003)
#
# 3 attempts × max ~4 s backoff ≈ 12 s worst case; the hard 30-s wall-clock
# cap is enforced by `asyncio.wait_for(...)`. Changing backoff parameters
# requires re-verifying the math vs the 30-s cap and FR-003.
#
# `DeadlineExceeded` is deliberately EXCLUDED from the retried set per
# Clarifications 2026-04-26 — the timeout already fired, retrying just
# burns the remaining wall-clock budget.
# `InvalidArgument` and `PermissionDenied` are caller-side errors; they
# are NOT retried and the wrapper translates them to `ModelCallConfigError`.
# ---------------------------------------------------------------------------

_RETRYABLE_EXCEPTIONS: Final[tuple[type[BaseException], ...]] = (
    gae.ServiceUnavailable,
    gae.InternalServerError,
    gae.ResourceExhausted,
    ConnectionError,
)
"""Exception types for which the wrapper retries up to the 3-attempt budget."""


def _build_retry_loop() -> AsyncRetrying:
    """Construct a fresh :class:`AsyncRetrying` instance per call.

    Per-call instantiation keeps tenacity's internal attempt counter scoped
    to one call (sharing one instance across calls would let unrelated
    invocations consume each other's retry budget).
    """
    return AsyncRetrying(
        retry=retry_if_exception_type(_RETRYABLE_EXCEPTIONS),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=0.5, max=4.0),
        reraise=True,
    )


# ---------------------------------------------------------------------------
# Outcome → log mapping helpers
# ---------------------------------------------------------------------------


def _select_backend(
    *,
    agent: str,
    settings: Settings,
) -> VertexBackend:
    """Choose between the real and mock backend per ``settings.llm_backend``."""
    if settings.llm_backend == "mock":
        return MockVertexBackend(
            agent=agent,
            fixtures_dir=settings.llm_fixtures_dir,
        )
    return RealVertexBackend()


_PRICING_TABLE: PricingTable | None = None
_MODELS_CONFIG: ModelsConfig | None = None


def _pricing_table() -> PricingTable:
    """Lazy-load the pricing table at first call (process-lifetime cache)."""
    global _PRICING_TABLE
    if _PRICING_TABLE is None:
        _PRICING_TABLE = PricingTable.from_yaml(PRICING_YAML_PATH)
    return _PRICING_TABLE


def _models_config() -> ModelsConfig:
    """Lazy-load ``configs/models.yaml`` at first call (process-lifetime cache)."""
    global _MODELS_CONFIG
    if _MODELS_CONFIG is None:
        _MODELS_CONFIG = ModelsConfig.from_yaml(MODELS_YAML_PATH)
    return _MODELS_CONFIG


def _classify_provider_error(exc: BaseException) -> WrapperError:
    """Translate a known google.api_core exception into a wrapper error.

    Raised after the retry loop has either returned the underlying
    exception (transient set exhausted) or surfaced a non-retried error.
    """
    if isinstance(exc, gae.DeadlineExceeded):
        return VertexTimeoutError(f"vertex deadline exceeded: {exc}")
    if isinstance(exc, _RETRYABLE_EXCEPTIONS):
        return VertexUpstreamUnavailableError(f"vertex upstream unavailable after retries: {exc}")
    if isinstance(exc, gae.InvalidArgument | gae.PermissionDenied):
        return ModelCallConfigError(f"vertex caller-side error: {exc}")
    if isinstance(exc, gae.GoogleAPIError):
        return VertexUpstreamUnavailableError(f"vertex API error: {exc}")
    # Unknown exception type — surface as upstream unavailable so the caller
    # at least knows the call was attempted; the trace record carries the
    # short error message so operators can correlate.
    return VertexUpstreamUnavailableError(f"vertex backend raised {type(exc).__name__}: {exc}")


# ---------------------------------------------------------------------------
# Trace + log helpers (constitution §15 — no PII / no prompt text / no output)
# ---------------------------------------------------------------------------


def _build_trace_record(
    *,
    request: ModelCallRequest,
    resolved_model: str,
    prompt_sha: str,
    outcome: TraceOutcome,
    attempts: int,
    latency_ms: int,
    raw: RawBackendResult | None,
    cost_usd: Decimal,
    error_message: str | None,
) -> TraceRecord:
    return TraceRecord(
        id=uuid4(),
        created_at=datetime.now(UTC),
        agent=request.agent,
        session_id=request.session_id,
        model=resolved_model,
        model_version=raw.model_version if raw is not None else None,
        prompt_sha256=prompt_sha,
        outcome=outcome,
        attempts=attempts,
        latency_ms=latency_ms,
        input_tokens=raw.input_tokens if raw is not None else 0,
        output_tokens=raw.output_tokens if raw is not None else 0,
        cost_usd=cost_usd,
        error_message=error_message,
    )


def _emit_log(
    *,
    record: TraceRecord,
) -> None:
    """Emit a single ``llm_call`` event for the terminal state.

    NEVER carries prompt text, output text, or candidate identity
    (constitution §15). The structlog pipeline configured in T02 also
    runs the PII redactor as a defence-in-depth, but the wrapper's
    contract is to not put sensitive content on the wire in the first
    place.
    """
    _LOGGER.info(
        "llm_call",
        trace_id=str(record.id),
        agent=record.agent,
        model=record.model,
        model_version=record.model_version,
        session_id=str(record.session_id),
        outcome=record.outcome,
        attempts=record.attempts,
        latency_ms=record.latency_ms,
        cost_usd=str(record.cost_usd),
        input_tokens=record.input_tokens,
        output_tokens=record.output_tokens,
    )


async def _persist_trace(
    *,
    sink: TraceSink,
    record: TraceRecord,
) -> None:
    """Synchronously persist the trace record. Sink failure → :class:`TraceWriteError`."""
    try:
        await sink.write(record)
    except TraceWriteError:
        raise
    except Exception as exc:
        raise TraceWriteError(f"trace sink raised {type(exc).__name__}: {exc}") from exc


# ---------------------------------------------------------------------------
# The wrapper
# ---------------------------------------------------------------------------


async def call_model(
    request: ModelCallRequest,
    *,
    sink: TraceSink,
    ledger: CostLedger,
    settings: Settings,
) -> ModelCallResult:
    """Issue one model call. The single sanctioned LLM doorway.

    Implements the 10-step contract in
    ``contracts/wrapper-contract.md`` §1. Returns :class:`ModelCallResult`
    on success; raises a typed :class:`WrapperError` subclass on every
    failure mode. Exactly one trace record is written per invocation,
    synchronously before this function returns or raises.
    """
    started = time.perf_counter()

    # Step 1 — resolve agent config (`unknown agent` is a config error).
    # We do this BEFORE the SHA computation so we have a resolved model
    # for the canonical SHA recipe.
    try:
        models_config = _models_config()
        agent_cfg = models_config.for_agent(request.agent)
    except ModelCallConfigError as exc:
        await _emit_failure_trace(
            request=request,
            resolved_model=request.model_override or "unknown",
            outcome="config_error",
            attempts=1,
            started=started,
            sink=sink,
            error_message=str(exc),
        )
        raise

    resolved_model = request.model_override or agent_cfg.model

    prompt_sha = canonical_prompt_sha(
        system_prompt=request.system_prompt,
        user_payload=request.user_payload,
        json_schema=request.json_schema,
        agent=request.agent,
        model=resolved_model,
    )

    # Step 2 — pricing lookup (also catches unknown `model_override`).
    try:
        pricing = _pricing_table()
        # Probe pricing existence early via a zero-token cost lookup; the
        # actual cost is computed after the call when token counts are known.
        pricing.cost_for(resolved_model, 0, 0)
    except ModelCallConfigError as exc:
        await _emit_failure_trace(
            request=request,
            resolved_model=resolved_model,
            outcome="config_error",
            attempts=1,
            started=started,
            sink=sink,
            error_message=str(exc),
            prompt_sha=prompt_sha,
        )
        raise

    # Step 3 — budget short-circuit BEFORE any backend call.
    current_total = await ledger.session_total(request.session_id)
    if current_total >= settings.llm_budget_per_session_usd:
        message = (
            f"session {request.session_id} at {current_total} ≥ ceiling "
            f"{settings.llm_budget_per_session_usd}"
        )
        await _emit_failure_trace(
            request=request,
            resolved_model=resolved_model,
            outcome="budget_exceeded",
            attempts=1,
            started=started,
            sink=sink,
            error_message=message,
            prompt_sha=prompt_sha,
        )
        raise SessionBudgetExceeded(message)

    # Step 4 — choose backend (mock vs real per env).
    backend = _select_backend(agent=request.agent, settings=settings)

    # Step 5 — wrap the backend call in retry + wall-clock timeout.
    raw: RawBackendResult | None = None
    attempts = 0
    last_error: BaseException | None = None
    try:
        raw, attempts = await asyncio.wait_for(
            _call_with_retries(
                backend=backend,
                request=request,
                resolved_model=resolved_model,
                temperature=agent_cfg.temperature,
                max_output_tokens=request.max_output_tokens,
            ),
            timeout=request.timeout_s,
        )
    except TimeoutError as exc:
        last_error = exc
        await _emit_failure_trace(
            request=request,
            resolved_model=resolved_model,
            outcome="timeout",
            attempts=max(attempts, 1),
            started=started,
            sink=sink,
            error_message=f"wall-clock timeout after {request.timeout_s}s",
            prompt_sha=prompt_sha,
        )
        raise VertexTimeoutError(f"wrapper wall-clock timeout after {request.timeout_s}s") from exc
    except WrapperError as exc:
        # Attempt count is propagated as `exc.attempts` from
        # `_call_with_retries`. Fall back to `max(attempts, 1)` only if the
        # error originated outside the retry helper (defensive — should
        # not happen in practice).
        attempt_count = max(getattr(exc, "attempts", 0) or attempts, 1)
        outcome: TraceOutcome
        if isinstance(exc, VertexTimeoutError):
            outcome = "timeout"
        elif isinstance(exc, VertexUpstreamUnavailableError):
            outcome = "upstream_unavailable"
        elif isinstance(exc, ModelCallConfigError):
            outcome = "config_error"
        else:
            outcome = "upstream_unavailable"
        await _emit_failure_trace(
            request=request,
            resolved_model=resolved_model,
            outcome=outcome,
            attempts=attempt_count,
            started=started,
            sink=sink,
            error_message=str(exc),
            prompt_sha=prompt_sha,
        )
        raise
    except Exception as exc:
        last_error = exc
        await _emit_failure_trace(
            request=request,
            resolved_model=resolved_model,
            outcome="upstream_unavailable",
            attempts=max(attempts, 1),
            started=started,
            sink=sink,
            error_message=f"{type(exc).__name__}: {exc}",
            prompt_sha=prompt_sha,
        )
        raise VertexUpstreamUnavailableError(
            f"vertex backend raised {type(exc).__name__}: {exc}"
        ) from exc

    assert raw is not None  # narrowing for mypy

    # Step 6 — Stage-2 schema validation (no retry on miss).
    parsed: dict[str, Any] | None = None
    if request.json_schema is not None:
        try:
            parsed_obj = _parse_and_validate(raw.text, request.json_schema)
        except VertexSchemaError as schema_err:
            cost_for_schema_err = pricing.cost_for(
                resolved_model, raw.input_tokens, raw.output_tokens
            )
            # Vertex billed for the call even though the payload was bad;
            # the trace records the cost but the ledger is NOT incremented
            # (failures don't burn budget per `contracts/wrapper-contract.md` §8).
            await _emit_failure_trace(
                request=request,
                resolved_model=resolved_model,
                outcome="schema_error",
                attempts=attempts,
                started=started,
                sink=sink,
                error_message=str(schema_err),
                prompt_sha=prompt_sha,
                raw=raw,
                cost_usd=cost_for_schema_err,
            )
            raise
        parsed = parsed_obj

    # Step 7 — cost arithmetic + ledger increment.
    cost_usd = pricing.cost_for(resolved_model, raw.input_tokens, raw.output_tokens)
    await ledger.add(request.session_id, cost_usd)

    # Step 8 — build the trace record (outcome="ok").
    latency_ms = int((time.perf_counter() - started) * 1000)
    record = _build_trace_record(
        request=request,
        resolved_model=resolved_model,
        prompt_sha=prompt_sha,
        outcome="ok",
        attempts=attempts,
        latency_ms=latency_ms,
        raw=raw,
        cost_usd=cost_usd,
        error_message=None,
    )

    # Step 9 — sync trace write BEFORE returning. Sink failure halts.
    await _persist_trace(sink=sink, record=record)
    _emit_log(record=record)

    # Step 10 — return.
    del last_error  # silence lint: only retained for debugger inspection
    return ModelCallResult(
        text=raw.text,
        parsed=parsed,
        input_tokens=raw.input_tokens,
        output_tokens=raw.output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        model=resolved_model,
        model_version=raw.model_version,
        attempts=attempts,
        trace_id=record.id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _call_with_retries(
    *,
    backend: VertexBackend,
    request: ModelCallRequest,
    resolved_model: str,
    temperature: float,
    max_output_tokens: int,
) -> tuple[RawBackendResult, int]:
    """Run the backend call inside the tenacity retry loop.

    Returns ``(raw, attempts)`` on success. Translates known
    :mod:`google.api_core.exceptions` into wrapper errors after the retry
    budget has been exhausted (or for non-retried error types like
    ``DeadlineExceeded``).
    """
    attempt_count = 0
    last_exc: BaseException | None = None
    retry_loop = _build_retry_loop()
    try:
        async for attempt in retry_loop:
            with attempt:
                attempt_count = attempt.retry_state.attempt_number
                try:
                    raw = await backend.generate(
                        system_prompt=request.system_prompt,
                        user_payload=request.user_payload,
                        json_schema=request.json_schema,
                        model=resolved_model,
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        timeout_s=float(request.timeout_s),
                    )
                except gae.DeadlineExceeded as exc:
                    # NOT retried — convert immediately.
                    raise VertexTimeoutError(f"vertex deadline exceeded: {exc}") from exc
                except (gae.InvalidArgument, gae.PermissionDenied) as exc:
                    raise ModelCallConfigError(f"vertex caller-side error: {exc}") from exc
                else:
                    return raw, attempt_count
    except RetryError as retry_exc:
        last_exc = retry_exc.last_attempt.exception()
        if last_exc is None:
            wrapper_err: WrapperError = VertexUpstreamUnavailableError(
                "vertex retry budget exhausted with no captured error"
            )
            wrapper_err.attempts = attempt_count  # type: ignore[attr-defined]
            raise wrapper_err from retry_exc
        wrapper_err = _classify_provider_error(last_exc)
        wrapper_err.attempts = attempt_count  # type: ignore[attr-defined]
        raise wrapper_err from last_exc
    except WrapperError as wrapped:
        # Wrapper error raised from inside the `with attempt:` block (e.g.,
        # the DeadlineExceeded or InvalidArgument early-conversion above).
        # Attach the attempt count so the outer call_model can build an
        # accurate trace record.
        wrapped.attempts = attempt_count  # type: ignore[attr-defined]
        raise
    except gae.GoogleAPIError as exc:
        wrapper_err = _classify_provider_error(exc)
        wrapper_err.attempts = attempt_count  # type: ignore[attr-defined]
        raise wrapper_err from exc
    # Unreachable: AsyncRetrying always either yields → returns, or raises.
    raise VertexUpstreamUnavailableError(  # pragma: no cover
        "vertex retry loop exited without a result"
    )


def _parse_and_validate(
    text: str,
    json_schema: dict[str, Any],
) -> dict[str, Any]:
    """Parse ``text`` as JSON and Stage-2 validate against ``json_schema``.

    Per Clarifications 2026-04-26 the wrapper does NOT retry on schema
    miss — :class:`VertexSchemaError` is raised immediately with the raw
    payload attached so the agent module can apply its per-agent policy.
    """
    import json

    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VertexSchemaError(
            f"backend returned non-JSON payload: {exc}",
            raw_payload=text,
        ) from exc
    if not isinstance(parsed, dict):
        raise VertexSchemaError(
            f"backend returned JSON of type {type(parsed).__name__}, expected object",
            raw_payload=text,
        )
    # Stage-2 dict-shape validation. Pydantic's TypeAdapter handles the
    # primitive-type / required-field checks the SDK's structured-output
    # mode requested but does not guarantee.
    try:
        TypeAdapter(dict).validate_python(parsed)
    except ValidationError as exc:
        raise VertexSchemaError(
            f"backend payload failed Stage-2 validation: {exc}",
            raw_payload=text,
        ) from exc
    _validate_against_schema(parsed, json_schema, path="$", raw_text=text)
    return parsed


def _validate_against_schema(
    payload: Any,
    schema: dict[str, Any],
    *,
    path: str,
    raw_text: str,
) -> None:
    """Minimal recursive JSON-schema validator covering object / array / scalar.

    The ``raw_text`` parameter is the ORIGINAL backend response string and
    is attached to every :class:`VertexSchemaError` raised here. This
    preserves byte-for-byte fidelity with what the backend returned —
    callers that need to debug a schema miss see the actual JSON, not the
    Python repr of the deserialised dict (which round-trips through
    single quotes, loses key ordering, etc.).

    Sufficient for the agent contracts T17 will land (object schemas with
    ``required`` lists and ``additionalProperties: false``); does not aim
    to be a complete JSON Schema implementation. A future PR may swap in
    a proper library if the agent schemas grow features (oneOf, $ref,
    pattern, etc.).
    """
    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(payload, dict):
            raise VertexSchemaError(
                f"{path}: expected object, got {type(payload).__name__}",
                raw_payload=raw_text,
            )
        required = schema.get("required") or []
        for key in required:
            if key not in payload:
                raise VertexSchemaError(
                    f"{path}: missing required property {key!r}",
                    raw_payload=raw_text,
                )
        properties = schema.get("properties") or {}
        if schema.get("additionalProperties") is False:
            extras = set(payload.keys()) - set(properties.keys())
            if extras:
                raise VertexSchemaError(
                    f"{path}: additional properties not allowed: {sorted(extras)}",
                    raw_payload=raw_text,
                )
        for key, sub_schema in properties.items():
            if key in payload and isinstance(sub_schema, dict):
                _validate_against_schema(
                    payload[key], sub_schema, path=f"{path}.{key}", raw_text=raw_text
                )
    elif schema_type == "array":
        if not isinstance(payload, list):
            raise VertexSchemaError(
                f"{path}: expected array, got {type(payload).__name__}",
                raw_payload=raw_text,
            )
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for idx, element in enumerate(payload):
                _validate_against_schema(
                    element, items_schema, path=f"{path}[{idx}]", raw_text=raw_text
                )
    elif schema_type == "string":
        if not isinstance(payload, str):
            raise VertexSchemaError(
                f"{path}: expected string, got {type(payload).__name__}",
                raw_payload=raw_text,
            )
    elif schema_type == "boolean":
        if not isinstance(payload, bool):
            raise VertexSchemaError(
                f"{path}: expected boolean, got {type(payload).__name__}",
                raw_payload=raw_text,
            )
    elif schema_type == "integer":
        if not isinstance(payload, int) or isinstance(payload, bool):
            raise VertexSchemaError(
                f"{path}: expected integer, got {type(payload).__name__}",
                raw_payload=raw_text,
            )
    elif schema_type == "number":
        if isinstance(payload, bool) or not isinstance(payload, int | float):
            raise VertexSchemaError(
                f"{path}: expected number, got {type(payload).__name__}",
                raw_payload=raw_text,
            )
    # Unknown / missing type: skip silently (caller may pass a partial schema).


async def _emit_failure_trace(
    *,
    request: ModelCallRequest,
    resolved_model: str,
    outcome: TraceOutcome,
    attempts: int,
    started: float,
    sink: TraceSink,
    error_message: str,
    prompt_sha: str | None = None,
    raw: RawBackendResult | None = None,
    cost_usd: Decimal = Decimal("0"),
) -> None:
    """Persist a trace for a failed call, then emit the log event."""
    if prompt_sha is None:
        prompt_sha = canonical_prompt_sha(
            system_prompt=request.system_prompt,
            user_payload=request.user_payload,
            json_schema=request.json_schema,
            agent=request.agent,
            model=resolved_model,
        )
    latency_ms = int((time.perf_counter() - started) * 1000)
    record = _build_trace_record(
        request=request,
        resolved_model=resolved_model,
        prompt_sha=prompt_sha,
        outcome=outcome,
        attempts=attempts,
        latency_ms=latency_ms,
        raw=raw,
        cost_usd=cost_usd,
        error_message=error_message,
    )
    await _persist_trace(sink=sink, record=record)
    _emit_log(record=record)
