"""End-to-end tests for the Vertex AI client wrapper (T04).

Covers the FR-017 matrix from `contracts/wrapper-contract.md` §10. Tests
exercise the full :func:`call_model` surface against the in-memory sink,
in-memory cost ledger, and the deterministic mock backend (or, where the
test needs to simulate an upstream failure, a small in-test
`FailingBackend` that implements the :class:`VertexBackend` protocol
structurally).

Constitution §15: every prompt / payload string used here is synthetic
(see ``_test_prompts.py``). The PII test (T038) uses a fake
``candidate@example.com`` marker that the test asserts NEVER appears in
any captured log entry.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from google.api_core import exceptions as gae
from pydantic import ValidationError

from app.backend.llm import (
    ModelCallConfigError,
    ModelCallRequest,
    ModelCallResult,
    SessionBudgetExceeded,
    TraceWriteError,
    VertexSchemaError,
    VertexTimeoutError,
    VertexUpstreamUnavailableError,
    call_model,
)
from app.backend.llm._backend_protocol import RawBackendResult, VertexBackend
from app.backend.llm._mock_backend import MockVertexBackend
from app.backend.llm.cost_ledger import CostLedger, InMemoryCostLedger
from app.backend.llm.pricing import PricingTable
from app.backend.llm.trace import (
    InMemoryTraceSink,
    TraceOutcome,
    TraceRecord,
    TraceSink,
)
from app.backend.settings import Settings
from app.backend.tests.llm._test_prompts import (
    ASSESSOR_BROKEN_USER_PAYLOAD,
    ASSESSOR_SCHEMA,
    ASSESSOR_SYSTEM_PROMPT,
    ASSESSOR_USER_PAYLOAD,
    INTERVIEWER_SCHEMA,
    INTERVIEWER_SYSTEM_PROMPT,
    INTERVIEWER_USER_PAYLOAD,
)

_FIXTURES_DIR: Path = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"


def _make_gae(exc_type: type[gae.GoogleAPIError], message: str) -> gae.GoogleAPIError:
    """Typed shim around google-api-core untyped exception constructors.

    ``google-api-core`` ships without ``py.typed`` so direct calls like
    ``gae.ServiceUnavailable("msg")`` are flagged ``no-untyped-call``
    under ``mypy --strict`` in some setups. Wrapping the construction in
    a single typed helper confines any suppression to one location and
    clarifies intent at every call site.
    """
    return exc_type(message)


# ---------------------------------------------------------------------------
# Helpers — small in-test backends and request builders
# ---------------------------------------------------------------------------


class _ScriptedBackend:
    """Backend that returns a pre-scripted sequence of outcomes per call.

    Each entry in ``script`` is either an exception **type** + args (the
    backend raises a fresh instance) or a :class:`RawBackendResult` (the
    backend returns it). Implements :class:`VertexBackend` structurally.
    """

    def __init__(
        self,
        script: list[BaseException | RawBackendResult],
    ) -> None:
        self._script = list(script)
        self.calls: int = 0

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
    ) -> RawBackendResult:
        del (
            system_prompt,
            user_payload,
            json_schema,
            model,
            temperature,
            max_output_tokens,
            timeout_s,
        )
        if not self._script:
            raise AssertionError("scripted backend exhausted; tests must script every call")
        self.calls += 1
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


class _SentinelBackend:
    """Backend whose :meth:`generate` is a hard test failure if invoked.

    Used by tests that assert the wrapper short-circuits before any
    backend call (budget exceeded, config error, etc.).
    """

    def __init__(self) -> None:
        self.calls: int = 0

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
    ) -> RawBackendResult:
        del (
            system_prompt,
            user_payload,
            json_schema,
            model,
            temperature,
            max_output_tokens,
            timeout_s,
        )
        self.calls += 1
        raise AssertionError("sentinel backend was invoked — wrapper should have short-circuited")


class _FailingSink:
    """Sink whose :meth:`write` always raises — for the trace-failure path."""

    def __init__(self, exc: BaseException | None = None) -> None:
        self._exc = exc or RuntimeError("simulated sink failure")
        self.attempts: int = 0

    async def write(self, record: TraceRecord) -> None:
        del record
        self.attempts += 1
        raise self._exc


def _interviewer_request(
    *,
    session_id: UUID | None = None,
    json_schema: dict[str, Any] | None = INTERVIEWER_SCHEMA,
    user_payload: str = INTERVIEWER_USER_PAYLOAD,
    system_prompt: str = INTERVIEWER_SYSTEM_PROMPT,
    timeout_s: int = 30,
    max_output_tokens: int = 2048,
    model_override: str | None = None,
) -> ModelCallRequest:
    """Build an interviewer request keyed against the committed fixture."""
    return ModelCallRequest(
        agent="interviewer",
        system_prompt=system_prompt,
        user_payload=user_payload,
        json_schema=json_schema,
        session_id=session_id or uuid4(),
        timeout_s=timeout_s,
        max_output_tokens=max_output_tokens,
        model_override=model_override,
    )


def _assessor_request(
    *,
    session_id: UUID | None = None,
    json_schema: dict[str, Any] | None = ASSESSOR_SCHEMA,
    user_payload: str = ASSESSOR_USER_PAYLOAD,
) -> ModelCallRequest:
    """Build an assessor request keyed against the committed fixture."""
    return ModelCallRequest(
        agent="assessor",
        system_prompt=ASSESSOR_SYSTEM_PROMPT,
        user_payload=user_payload,
        json_schema=json_schema,
        session_id=session_id or uuid4(),
    )


def _force_backend(
    monkeypatch: pytest.MonkeyPatch,
    backend: VertexBackend,
) -> None:
    """Make ``call_model`` use a specific backend regardless of settings."""
    monkeypatch.setattr(
        "app.backend.llm.vertex._select_backend",
        lambda *, agent, settings: backend,
    )


# ---------------------------------------------------------------------------
# T022 — pydantic enforces the 30-s timeout cap at construction
# ---------------------------------------------------------------------------


def test_timeout_above_30s_rejected_at_construction() -> None:
    """Constitution §12: ``timeout_s <= 30``. Caught before any I/O.

    Maps to FR-002, FR-017b, SC-002.
    """
    with pytest.raises(ValidationError) as excinfo:
        ModelCallRequest(
            agent="interviewer",
            system_prompt=INTERVIEWER_SYSTEM_PROMPT,
            user_payload=INTERVIEWER_USER_PAYLOAD,
            json_schema=INTERVIEWER_SCHEMA,
            session_id=uuid4(),
            timeout_s=31,
        )
    # The validation error must mention the offending field.
    assert "timeout_s" in str(excinfo.value)


# ---------------------------------------------------------------------------
# T023 — pydantic enforces the 4096-tokens output cap at construction
# ---------------------------------------------------------------------------


def test_max_tokens_above_4096_rejected_at_construction() -> None:
    """Constitution §12: ``max_output_tokens <= 4096``. Caught before any I/O.

    Maps to FR-002, FR-017b, SC-002.
    """
    with pytest.raises(ValidationError) as excinfo:
        ModelCallRequest(
            agent="interviewer",
            system_prompt=INTERVIEWER_SYSTEM_PROMPT,
            user_payload=INTERVIEWER_USER_PAYLOAD,
            json_schema=INTERVIEWER_SCHEMA,
            session_id=uuid4(),
            max_output_tokens=4097,
        )
    assert "max_output_tokens" in str(excinfo.value)


# ---------------------------------------------------------------------------
# T024 — unknown agent raises ModelCallConfigError + leaves a trace
# ---------------------------------------------------------------------------


async def test_unknown_agent_raises_config_error(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """Unknown agent name → ``ModelCallConfigError`` at the wrapper layer.

    The agent string is ``min_length=1`` at pydantic level so the request
    constructs OK; the wrapper catches the unknown agent at the
    ``ModelsConfig.for_agent`` lookup and emits a ``config_error`` trace.

    Maps to FR-019.
    """
    request = ModelCallRequest(
        agent="unknown_agent",
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        session_id=uuid4(),
    )
    with pytest.raises(ModelCallConfigError) as excinfo:
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert "unknown_agent" in str(excinfo.value)

    # Trace was still written — every terminal state leaves a record.
    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "config_error"


# ---------------------------------------------------------------------------
# T025 — unknown model_override raises ModelCallConfigError; no backend call
# ---------------------------------------------------------------------------


async def test_unknown_model_override_raises_config_error(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown model identifier → ``ModelCallConfigError`` from pricing lookup.

    Maps to FR-010.
    """
    sentinel = _SentinelBackend()
    _force_backend(monkeypatch, sentinel)

    request = _interviewer_request(model_override="gemini-no-such")
    with pytest.raises(ModelCallConfigError) as excinfo:
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert "gemini-no-such" in str(excinfo.value)
    assert sentinel.calls == 0, "wrapper must not invoke backend on unknown model"

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "config_error"
    assert records[0].cost_usd == Decimal("0")


# ---------------------------------------------------------------------------
# T026 — transient failure followed by success: wrapper retries
# ---------------------------------------------------------------------------


async def test_retry_on_transient_then_succeeds(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One transient failure → wrapper retries; second attempt succeeds.

    Maps to FR-004.
    """
    success = RawBackendResult(
        text='{"message_uk": "Привіт", "intent": "greet", "end_of_phase": false}',
        input_tokens=10,
        output_tokens=15,
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
    )
    backend = _ScriptedBackend(
        [
            _make_gae(gae.ServiceUnavailable, "upstream temporarily unavailable"),
            success,
        ]
    )
    _force_backend(monkeypatch, backend)

    # Suppress retry backoff so the test is fast.
    monkeypatch.setattr(
        "app.backend.llm.vertex.wait_exponential_jitter",
        lambda **_: __import__("tenacity").wait_none(),
    )

    request = _interviewer_request()
    result = await call_model(
        request,
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )
    assert isinstance(result, ModelCallResult)
    assert result.attempts == 2
    assert backend.calls == 2

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "ok"
    assert records[0].attempts == 2


# ---------------------------------------------------------------------------
# T027 — three transient failures: budget exhausted → upstream_unavailable
# ---------------------------------------------------------------------------


async def test_retry_budget_exhausted_raises_upstream_unavailable(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """3-attempt budget exhausted on transient failures.

    Maps to FR-004.
    """
    backend = _ScriptedBackend(
        [
            _make_gae(gae.ServiceUnavailable, "attempt 1"),
            _make_gae(gae.ServiceUnavailable, "attempt 2"),
            _make_gae(gae.ServiceUnavailable, "attempt 3"),
        ]
    )
    _force_backend(monkeypatch, backend)
    monkeypatch.setattr(
        "app.backend.llm.vertex.wait_exponential_jitter",
        lambda **_: __import__("tenacity").wait_none(),
    )

    request = _interviewer_request()
    with pytest.raises(VertexUpstreamUnavailableError):
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert backend.calls == 3

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "upstream_unavailable"
    assert records[0].attempts == 3


# ---------------------------------------------------------------------------
# T028 — DeadlineExceeded is NOT retried (per Clarifications 2026-04-26)
# ---------------------------------------------------------------------------


async def test_deadline_exceeded_not_retried(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``DeadlineExceeded`` short-circuits the retry loop — attempts == 1.

    Maps to FR-004 + Clarifications 2026-04-26.
    """
    backend = _ScriptedBackend([_make_gae(gae.DeadlineExceeded, "vertex deadline")])
    _force_backend(monkeypatch, backend)

    request = _interviewer_request()
    with pytest.raises(VertexTimeoutError):
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert backend.calls == 1, "DeadlineExceeded must not be retried"

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "timeout"
    assert records[0].attempts == 1


# ---------------------------------------------------------------------------
# T029 — InvalidArgument → ModelCallConfigError; no retry
# ---------------------------------------------------------------------------


async def test_invalid_argument_not_retried(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``InvalidArgument`` re-classified as ``ModelCallConfigError``.

    Maps to FR-004.
    """
    backend = _ScriptedBackend([_make_gae(gae.InvalidArgument, "bad payload")])
    _force_backend(monkeypatch, backend)

    request = _interviewer_request()
    with pytest.raises(ModelCallConfigError):
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert backend.calls == 1, "caller-side errors must not be retried"

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "config_error"
    assert records[0].attempts == 1


# ---------------------------------------------------------------------------
# T033 — full happy path: schema-valid mock + parsed dict + one ok trace
# ---------------------------------------------------------------------------


async def test_successful_call_with_schema_returns_parsed_json(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """End-to-end mock-mode call: parsed JSON, tokens > 0, one ok trace.

    Maps to FR-002, FR-005, FR-011, FR-017a.
    """
    from structlog.testing import capture_logs

    request = _interviewer_request()
    with capture_logs() as captured:
        result = await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert isinstance(result, ModelCallResult)
    assert result.parsed is not None
    assert result.parsed["message_uk"].startswith("Доброго дня")
    assert result.input_tokens > 0
    assert result.output_tokens > 0
    assert result.cost_usd > 0
    assert result.attempts == 1
    assert result.model == "gemini-2.5-flash"

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "ok"
    assert records[0].id == result.trace_id

    # Exactly one llm_call log event for the terminal state.
    # `structlog.testing.capture_logs` bypasses the EventRenamer so the
    # event name remains on the ``event`` key.
    llm_events = [e for e in captured if e.get("event") == "llm_call"]
    assert len(llm_events) == 1


# ---------------------------------------------------------------------------
# T036 — sink failure on otherwise-OK call → TraceWriteError
# ---------------------------------------------------------------------------


async def test_trace_sink_failure_raises_trace_write_error(
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """Sink failure trumps backend success — auditability is non-negotiable.

    Maps to FR-009 + Clarifications 2026-04-26.
    """
    failing_sink = _FailingSink()
    request = _interviewer_request()
    with pytest.raises(TraceWriteError):
        await call_model(
            request,
            sink=failing_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert failing_sink.attempts >= 1


# ---------------------------------------------------------------------------
# T037 — exactly one trace per invocation across the seven outcomes
# ---------------------------------------------------------------------------


_OutcomeSetup = Callable[
    [InMemoryTraceSink, InMemoryCostLedger, Settings, pytest.MonkeyPatch],
    "tuple[ModelCallRequest, type[BaseException], TraceSink, CostLedger]",
]


def _setup_ok(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    del monkeypatch
    return _interviewer_request(), None, sink, ledger


def _setup_schema_error(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    del monkeypatch
    return (
        _assessor_request(user_payload=ASSESSOR_BROKEN_USER_PAYLOAD),
        VertexSchemaError,
        sink,
        ledger,
    )


def _setup_timeout(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    backend = _ScriptedBackend([_make_gae(gae.DeadlineExceeded, "deadline")])
    _force_backend(monkeypatch, backend)
    return _interviewer_request(), VertexTimeoutError, sink, ledger


def _setup_upstream_unavailable(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    backend = _ScriptedBackend(
        [
            _make_gae(gae.ServiceUnavailable, "a"),
            _make_gae(gae.ServiceUnavailable, "b"),
            _make_gae(gae.ServiceUnavailable, "c"),
        ]
    )
    _force_backend(monkeypatch, backend)
    monkeypatch.setattr(
        "app.backend.llm.vertex.wait_exponential_jitter",
        lambda **_: __import__("tenacity").wait_none(),
    )
    return _interviewer_request(), VertexUpstreamUnavailableError, sink, ledger


def _setup_budget_exceeded(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    sentinel = _SentinelBackend()
    _force_backend(monkeypatch, sentinel)
    session_id = uuid4()
    # Pre-seed the ledger at the ceiling. We poke the private `_totals`
    # dict directly because this setup helper is sync but the ledger's
    # public `add` is a coroutine; the wrapper test that exercises the
    # async path is `test_session_at_budget_raises_before_backend_call`
    # below.
    ledger._totals[session_id] = settings.llm_budget_per_session_usd
    return (
        _interviewer_request(session_id=session_id),
        SessionBudgetExceeded,
        sink,
        ledger,
    )


def _setup_config_error(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    del monkeypatch, settings
    request = ModelCallRequest(
        agent="not_an_agent",
        system_prompt=INTERVIEWER_SYSTEM_PROMPT,
        user_payload=INTERVIEWER_USER_PAYLOAD,
        json_schema=INTERVIEWER_SCHEMA,
        session_id=uuid4(),
    )
    return request, ModelCallConfigError, sink, ledger


def _setup_trace_write_error(
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelCallRequest, type[BaseException] | None, TraceSink, CostLedger]:
    del sink, monkeypatch, settings
    return _interviewer_request(), TraceWriteError, _FailingSink(), ledger


@pytest.mark.parametrize(
    ("outcome", "setup"),
    [
        ("ok", _setup_ok),
        ("schema_error", _setup_schema_error),
        ("timeout", _setup_timeout),
        ("upstream_unavailable", _setup_upstream_unavailable),
        ("budget_exceeded", _setup_budget_exceeded),
        ("config_error", _setup_config_error),
        ("trace_write_error", _setup_trace_write_error),
    ],
)
async def test_one_trace_per_invocation_in_every_scenario(
    outcome: TraceOutcome,
    setup: _OutcomeSetup,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every wrapper invocation leaves exactly one trace.

    For ``trace_write_error`` the test uses a :class:`_FailingSink` and
    verifies that the wrapper at least *attempted* to persist a record;
    no in-memory trace is captured (because the sink is the failure
    point), but the contract is "one persistence attempt per call".

    Maps to FR-008, SC-004, SC-007.
    """
    request, expected_exc, sink, ledger = setup(
        in_memory_trace_sink, in_memory_cost_ledger, test_settings, monkeypatch
    )

    if expected_exc is None:
        # Happy path — exercise the call, trace should be a single "ok".
        await call_model(request, sink=sink, ledger=ledger, settings=test_settings)
    else:
        with pytest.raises(expected_exc):
            await call_model(request, sink=sink, ledger=ledger, settings=test_settings)

    if outcome == "trace_write_error":
        # The failing sink IS the trace point of failure; the contract is
        # that exactly one persistence attempt was made.
        assert isinstance(sink, _FailingSink)
        assert sink.attempts == 1
    else:
        assert isinstance(sink, InMemoryTraceSink)
        records = sink.records
        assert len(records) == 1, f"expected 1 trace for {outcome}, got {len(records)}"
        assert records[0].outcome == outcome


# ---------------------------------------------------------------------------
# T038 — log event carries no prompt text, no PII
# ---------------------------------------------------------------------------


async def test_log_event_carries_no_prompt_text_no_pii(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``llm_call`` event MUST NOT echo prompt text or candidate identity.

    Constitution §15 + FR-013. We deliberately stuff a recognisable
    marker into both system_prompt and user_payload, plus an email into
    user_payload, then assert that NEITHER appears in any captured log
    record.

    Uses :func:`structlog.testing.capture_logs` which intercepts every
    structlog event regardless of the configured pipeline (works around
    the ``cache_logger_on_first_use=True`` setting that otherwise binds
    the wrapper's module-level ``_LOGGER`` to the production processors
    at import time).
    """
    marker = "secret_marker_string_xyz_42"
    pii_email = "candidate@example.com"

    success = RawBackendResult(
        text='{"message_uk": "ok", "intent": "noop", "end_of_phase": false}',
        input_tokens=5,
        output_tokens=8,
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
    )
    backend = _ScriptedBackend([success])
    _force_backend(monkeypatch, backend)

    request = ModelCallRequest(
        agent="interviewer",
        system_prompt=marker,
        user_payload=f"{pii_email} asked: {marker}",
        json_schema=INTERVIEWER_SCHEMA,
        session_id=uuid4(),
    )

    from structlog.testing import capture_logs

    with capture_logs() as captured:
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )

    # Exactly one llm_call event per terminal state. `capture_logs`
    # bypasses the `EventRenamer` processor so the event name is on the
    # ``event`` key (not ``message``).
    llm_events = [e for e in captured if e.get("event") == "llm_call"]
    assert len(llm_events) == 1, captured

    # No captured event may carry the marker or the raw email.
    import json

    for event in captured:
        blob = json.dumps(event, sort_keys=True, default=str, ensure_ascii=False)
        assert marker not in blob, f"prompt marker leaked into log: {event!r}"
        assert pii_email not in blob, f"raw email leaked into log: {event!r}"


# ---------------------------------------------------------------------------
# T040 — schema miss raises immediately with raw_payload (no retry)
# ---------------------------------------------------------------------------


async def test_schema_miss_raises_immediately_with_raw_payload(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """Schema-INVALID fixture → ``VertexSchemaError`` on attempt 1, no retry.

    Per Clarifications 2026-04-26 — wrapper does NOT retry on schema
    miss; the agent module owns that policy. ``e.raw_payload`` must
    equal the broken JSON the mock returned.

    Maps to FR-011, FR-017c.
    """
    request = _assessor_request(user_payload=ASSESSOR_BROKEN_USER_PAYLOAD)
    with pytest.raises(VertexSchemaError) as excinfo:
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    # The fixture's text field is the broken JSON.
    expected_raw = (
        '{"concepts_covered": ["tcp_basic"], '
        '"concepts_missing": ["three_way_handshake"], "red_flags": []}'
    )
    assert excinfo.value.raw_payload == expected_raw

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "schema_error"
    assert records[0].attempts == 1


# ---------------------------------------------------------------------------
# T041 — no schema → text passes through unparsed
# ---------------------------------------------------------------------------


async def test_no_schema_passes_text_through_unparsed(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``json_schema=None`` → ``result.parsed is None``; raw text intact.

    Maps to FR-011.
    """
    raw_text = "Free-form text response, not JSON."
    success = RawBackendResult(
        text=raw_text,
        input_tokens=20,
        output_tokens=12,
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
    )
    backend = _ScriptedBackend([success])
    _force_backend(monkeypatch, backend)

    request = _interviewer_request(json_schema=None)
    result = await call_model(
        request,
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )
    assert result.parsed is None
    assert result.text == raw_text


# ---------------------------------------------------------------------------
# T043 — session at budget raises before backend call
# ---------------------------------------------------------------------------


async def test_session_at_budget_raises_before_backend_call(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ledger at $5.00 → ``SessionBudgetExceeded`` before backend call.

    Maps to FR-012, FR-017d, SC-006.
    """
    sentinel = _SentinelBackend()
    _force_backend(monkeypatch, sentinel)

    session_id = uuid4()
    await in_memory_cost_ledger.add(session_id, Decimal("5.00"))
    assert await in_memory_cost_ledger.session_total(session_id) == Decimal("5.00")

    request = _interviewer_request(session_id=session_id)
    with pytest.raises(SessionBudgetExceeded):
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )
    assert sentinel.calls == 0

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "budget_exceeded"
    assert records[0].cost_usd == Decimal("0")
    assert records[0].input_tokens == 0
    assert records[0].output_tokens == 0


# ---------------------------------------------------------------------------
# T044 — successful call increments ledger by actual cost
# ---------------------------------------------------------------------------


async def test_successful_call_increments_ledger_by_actual_cost(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
    sample_pricing: PricingTable,
) -> None:
    """Empty ledger → after call total equals pricing.cost_for(...).

    Maps to FR-010, FR-012.
    """
    session_id = uuid4()
    assert await in_memory_cost_ledger.session_total(session_id) == Decimal("0")

    request = _interviewer_request(session_id=session_id)
    result = await call_model(
        request,
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )

    expected_cost = sample_pricing.cost_for(result.model, result.input_tokens, result.output_tokens)
    actual_total = await in_memory_cost_ledger.session_total(session_id)
    assert actual_total == expected_cost
    assert actual_total > 0

    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].cost_usd == expected_cost


# ---------------------------------------------------------------------------
# T045 — failed call does NOT increment ledger, but trace records cost
# ---------------------------------------------------------------------------


async def test_failed_call_does_not_increment_ledger(
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """Schema-error path: ledger stays at 0; trace records the billed cost.

    The wrapper passes ``Decimal("0")`` to ``ledger.add`` on failure
    (per ``contracts/wrapper-contract.md`` §8 — "failures don't burn
    budget"). The trace record DOES carry ``cost_usd > 0`` because
    Vertex still billed for the call.

    Maps to FR-008, FR-012.
    """
    session_id = uuid4()
    request = _assessor_request(session_id=session_id, user_payload=ASSESSOR_BROKEN_USER_PAYLOAD)
    with pytest.raises(VertexSchemaError):
        await call_model(
            request,
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )

    # Ledger NOT incremented.
    assert await in_memory_cost_ledger.session_total(session_id) == Decimal("0")

    # Trace records the billed cost so the cost is auditable even though
    # the ledger does not penalise the session for the failed call.
    records = in_memory_trace_sink.records
    assert len(records) == 1
    assert records[0].outcome == "schema_error"
    assert records[0].cost_usd > Decimal("0"), (
        "trace must record the cost Vertex billed, even on a failed call"
    )


# ---------------------------------------------------------------------------
# Sanity: the patched module-level symbols above must actually exist
# ---------------------------------------------------------------------------


def test_module_symbols_for_patching_exist() -> None:
    """Assert the module names patched above exist; protects against rename drift."""
    import app.backend.llm.vertex as vertex_module

    assert hasattr(vertex_module, "_select_backend")
    assert hasattr(vertex_module, "wait_exponential_jitter")
    # mock_backend default agent contract — used by other tests.
    backend = MockVertexBackend(agent="assessor", fixtures_dir=_FIXTURES_DIR)
    assert backend.agent == "assessor"
