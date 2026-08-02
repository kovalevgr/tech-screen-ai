"""Transport-translation tests for the real Vertex backend (030).

Fully offline: no network, no ADC, no real ``genai.Client`` construction.
The SDK exception type is consumed via the ``GenAiAPIError`` re-export on
``app.backend.llm._real_backend``, so this module never imports a
provider SDK directly and stays outside the
``scripts/check-no-provider-sdk-imports.sh`` allowlist.

Covers the 030 error-taxonomy contract:

- HTTP 429 / 5xx (except 504) → ``BackendTransientError`` (retried);
- HTTP 504 + transport timeouts → ``BackendDeadlineExceededError``
  (NOT retried, per Clarifications 2026-04-26);
- HTTP 400 / 403 → ``BackendCallerError`` (→ ``ModelCallConfigError``);
- any other upstream code → ``BackendUpstreamError``;
- connection-level ``httpx.TransportError`` → ``BackendTransientError``.

Plus the schema-transport contract of ``generate()``: a ``json_schema``
is forwarded as ``response_json_schema`` (verbatim) + JSON mime type —
never through the legacy ``response_schema`` translator.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from app.backend.llm._backend_protocol import (
    BackendCallerError,
    BackendDeadlineExceededError,
    BackendError,
    BackendTransientError,
    BackendUpstreamError,
)
from app.backend.llm._real_backend import (
    GenAiAPIError,
    RealVertexBackend,
    classify_http_status,
    translate_transport_error,
)

# ---------------------------------------------------------------------------
# classify_http_status — the pure status-code taxonomy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (429, BackendTransientError),  # quota — legacy ResourceExhausted
        (500, BackendTransientError),  # legacy InternalServerError
        (502, BackendTransientError),  # 5xx blanket per documented policy
        (503, BackendTransientError),  # legacy ServiceUnavailable
        (504, BackendDeadlineExceededError),  # legacy DeadlineExceeded — NOT retried
        (400, BackendCallerError),  # legacy InvalidArgument
        (403, BackendCallerError),  # legacy PermissionDenied
        (401, BackendUpstreamError),  # unclassified — upstream-unavailable
        (404, BackendUpstreamError),
        (408, BackendUpstreamError),
        (0, BackendUpstreamError),  # defensive: SDK could not extract a code
    ],
)
def test_classify_http_status_maps_code_to_expected_class(
    code: int,
    expected: type[BackendError],
) -> None:
    assert classify_http_status(code) is expected


# ---------------------------------------------------------------------------
# translate_transport_error — SDK / httpx exception instances
# ---------------------------------------------------------------------------


def _api_error(code: int, status: str) -> GenAiAPIError:
    """Build a genai APIError the way the SDK does from an error body."""
    return GenAiAPIError(code, {"error": {"message": "synthetic", "status": status}})


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_api_error(503, "UNAVAILABLE"), BackendTransientError),
        (_api_error(429, "RESOURCE_EXHAUSTED"), BackendTransientError),
        (_api_error(504, "DEADLINE_EXCEEDED"), BackendDeadlineExceededError),
        (_api_error(400, "INVALID_ARGUMENT"), BackendCallerError),
        (_api_error(403, "PERMISSION_DENIED"), BackendCallerError),
        (_api_error(404, "NOT_FOUND"), BackendUpstreamError),
        (httpx.ReadTimeout("read deadline"), BackendDeadlineExceededError),
        (httpx.ConnectTimeout("connect deadline"), BackendDeadlineExceededError),
        (httpx.ConnectError("connection refused"), BackendTransientError),
        (httpx.RemoteProtocolError("server disconnected"), BackendTransientError),
        (RuntimeError("unexpected"), BackendUpstreamError),  # defensive branch
    ],
)
def test_translate_transport_error_classifies_exception(
    exc: BaseException,
    expected: type[BackendError],
) -> None:
    translated = translate_transport_error(exc)
    assert type(translated) is expected


def test_translate_transport_error_carries_status_code_in_message() -> None:
    translated = translate_transport_error(_api_error(503, "UNAVAILABLE"))
    assert "503" in str(translated)


# ---------------------------------------------------------------------------
# generate() — schema transport + envelope mapping + error path, all offline
# ---------------------------------------------------------------------------


class _StubAioModels:
    """Captures generate_content kwargs; returns a canned response or raises."""

    def __init__(self, response: Any = None, exc: BaseException | None = None) -> None:
        self._response = response
        self._exc = exc
        self.kwargs: dict[str, Any] = {}

    async def generate_content(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        if self._exc is not None:
            raise self._exc
        return self._response


def _backend_with_stub(stub: _StubAioModels) -> RealVertexBackend:
    """Build a RealVertexBackend around the stub WITHOUT constructing genai.Client.

    ``__new__`` skips ``__init__`` (which would resolve project/ADC);
    the stub replaces the private client attribute so ``generate()`` runs
    its real code path with zero network and zero credentials.
    """
    backend = RealVertexBackend.__new__(RealVertexBackend)
    stub_client = SimpleNamespace(aio=SimpleNamespace(models=stub))
    backend._client = cast(Any, stub_client)
    return backend


_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["verdict"],
    "properties": {"verdict": {"type": ["string", "null"], "const": "ok"}},
}


def _ok_response() -> Any:
    return SimpleNamespace(
        text='{"verdict": "ok"}',
        usage_metadata=SimpleNamespace(prompt_token_count=7, candidates_token_count=11),
        model_version="gemini-2.5-flash-002",
    )


async def test_generate_forwards_schema_as_response_json_schema_verbatim() -> None:
    """json_schema rides `response_json_schema` untouched + JSON mime type."""
    stub = _StubAioModels(response=_ok_response())
    backend = _backend_with_stub(stub)

    result = await backend.generate(
        system_prompt="system",
        user_payload="payload",
        json_schema=_SCHEMA,
        model="gemini-2.5-flash",
        temperature=0.2,
        max_output_tokens=2048,
        timeout_s=30.0,
    )

    config = stub.kwargs["config"]
    assert config.response_json_schema == _SCHEMA
    assert config.response_mime_type == "application/json"
    assert config.response_schema is None, (
        "legacy response_schema must never be used — its t_schema translator "
        "rejects the committed JSON-Schema documents"
    )
    assert config.max_output_tokens == 2048
    assert stub.kwargs["model"] == "gemini-2.5-flash"

    assert result.text == '{"verdict": "ok"}'
    assert result.input_tokens == 7
    assert result.output_tokens == 11
    assert result.model == "gemini-2.5-flash"
    assert result.model_version == "gemini-2.5-flash-002"


async def test_generate_without_schema_omits_json_mode() -> None:
    stub = _StubAioModels(response=_ok_response())
    backend = _backend_with_stub(stub)

    await backend.generate(
        system_prompt="system",
        user_payload="payload",
        json_schema=None,
        model="gemini-2.5-flash",
        temperature=0.2,
        max_output_tokens=1024,
        timeout_s=30.0,
    )

    config = stub.kwargs["config"]
    assert config.response_json_schema is None
    assert config.response_mime_type is None


async def test_generate_translates_api_error_to_backend_classification() -> None:
    """A 503 from the SDK escapes generate() as BackendTransientError."""
    stub = _StubAioModels(exc=_api_error(503, "UNAVAILABLE"))
    backend = _backend_with_stub(stub)

    with pytest.raises(BackendTransientError) as excinfo:
        await backend.generate(
            system_prompt="system",
            user_payload="payload",
            json_schema=None,
            model="gemini-2.5-flash",
            temperature=0.2,
            max_output_tokens=1024,
            timeout_s=30.0,
        )
    assert isinstance(excinfo.value.__cause__, GenAiAPIError)


async def test_generate_translates_httpx_connect_error_to_transient() -> None:
    stub = _StubAioModels(exc=httpx.ConnectError("connection refused"))
    backend = _backend_with_stub(stub)

    with pytest.raises(BackendTransientError):
        await backend.generate(
            system_prompt="system",
            user_payload="payload",
            json_schema=None,
            model="gemini-2.5-flash",
            temperature=0.2,
            max_output_tokens=1024,
            timeout_s=30.0,
        )
