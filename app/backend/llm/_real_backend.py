"""Real Vertex AI backend using the ``google-genai`` async client.

This module is the **only** non-test backend module allowed to import a
model-provider SDK; the static guardrail at
``scripts/check-no-provider-sdk-imports.sh`` enforces the rule across the
backend tree.

Authentication uses Application Default Credentials exclusively
(constitution §6, ADR-013). The class constructor accepts NO credential
parameter — never a JSON service-account key, an inline private key, or
any opaque secret. Region is pinned at construction time per ADR-015
(``europe-west1`` for the MVP single-region deployment).

Structured output uses ``response_json_schema`` (google-genai ≥ 1.22):
the committed ``prompts/<agent>/<version>/schema.json`` documents are
transported to the API **verbatim** — no client-side ``t_schema``
translation, no mutation of ``$schema`` / ``$id`` / union types /
``const``. The offline regression test
``app/backend/tests/llm/test_prompt_schema_transport.py`` pins this.

Error taxonomy (030): every provider-SDK exception is translated here
into an SDK-free :class:`BackendError` subclass before it escapes
:meth:`RealVertexBackend.generate`, so the wrapper's retry loop in
``vertex.py`` never imports a provider SDK. ``google.genai`` raises
:class:`google.genai.errors.APIError` (``ClientError`` for 4xx,
``ServerError`` for 5xx — classified by ``.code``, not by subclass,
because 429 arrives as a *ClientError*); connection-level failures
surface as raw ``httpx`` transport exceptions (the SDK's built-in retry
is OFF unless ``HttpOptions.retry_options`` is set — we never set it, so
the wrapper keeps sole ownership of the 3-attempt budget).
"""

from __future__ import annotations

from typing import Any, Final

import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.backend.llm._backend_protocol import (
    BackendCallerError,
    BackendDeadlineExceededError,
    BackendError,
    BackendTransientError,
    BackendUpstreamError,
    RawBackendResult,
)

_DEFAULT_LOCATION: Final[str] = "europe-west1"

GenAiAPIError = genai_errors.APIError
"""Re-export for tests ONLY (`app/backend/tests/llm/test_real_backend.py`).

Production code must never import provider-SDK exception types — it
consumes the :class:`BackendError` classification instead. The re-export
exists so the taxonomy tests can construct SDK errors without tripping
``scripts/check-no-provider-sdk-imports.sh``.
"""


def classify_http_status(code: int) -> type[BackendError]:
    """Map an upstream HTTP status code to its transport classification.

    Mapping per `docs/engineering/vertex-integration.md` § Retry policy.
    NOTE: 030 deliberately WIDENS the transient set — pre-030 only
    429/500/503 were retried and 501/502/505 got a single attempt via
    the catch-all; blanket 5xx-except-504 resolves the old
    docstring-vs-table contradiction in the docstring's favor.

    - 429 + 5xx (except 504) → :class:`BackendTransientError` (retried);
    - 504 → :class:`BackendDeadlineExceededError` (deadline already
      fired — NOT retried, per Clarifications 2026-04-26);
    - 400 / 403 → :class:`BackendCallerError` (caller-side — NOT retried);
    - everything else → :class:`BackendUpstreamError` (NOT retried).
    """
    if code == 504:
        return BackendDeadlineExceededError
    if code in (400, 403):
        return BackendCallerError
    if code == 429 or 500 <= code < 600:
        return BackendTransientError
    return BackendUpstreamError


def translate_transport_error(exc: BaseException) -> BackendError:
    """Translate a provider-SDK / transport exception into a :class:`BackendError`.

    - :class:`google.genai.errors.APIError` → classified by ``.code``
      via :func:`classify_http_status`;
    - ``httpx.TimeoutException`` → :class:`BackendDeadlineExceededError`
      (the transport deadline already burned wall clock — same no-retry
      rationale as HTTP 504);
    - any other ``httpx.TransportError`` (connect refused/reset, broken
      stream, protocol error) → :class:`BackendTransientError`;
    - anything else → :class:`BackendUpstreamError` (defensive).
    """
    if isinstance(exc, genai_errors.APIError):
        code = exc.code or 0
        return classify_http_status(code)(f"vertex api error {code}: {exc}")
    if isinstance(exc, httpx.TimeoutException):
        return BackendDeadlineExceededError(f"vertex transport deadline: {exc!r}")
    if isinstance(exc, httpx.TransportError):
        return BackendTransientError(f"vertex transport failure: {exc!r}")
    return BackendUpstreamError(f"vertex backend raised {type(exc).__name__}: {exc}")


class RealVertexBackend:
    """Async wrapper over ``google.genai.Client.aio.models.generate_content``.

    Application Default Credentials only — no credential parameter is
    exposed. The Cloud Run revision in production injects the Workload
    Identity Federation principal via ADC; locally ADC resolves to the
    developer's ``gcloud auth application-default login`` identity.
    """

    def __init__(
        self,
        *,
        project: str | None = None,
        location: str = _DEFAULT_LOCATION,
    ) -> None:
        # NOTE: NO `credentials` / `api_key` parameter. ADC only — see
        # ADR-013 and constitution §5/§6. The google-genai SDK resolves
        # ADC internally when `vertexai=True` and no explicit credentials
        # are passed.
        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )

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
        """Issue one ``generate_content`` call and return the envelope.

        ``timeout_s`` is documented for protocol parity but the wall-clock
        timeout is enforced by the wrapper via :func:`asyncio.wait_for`;
        we deliberately leave ``HttpOptions.timeout`` unset so the SDK's
        httpx client runs without its own deadline (and without the SDK's
        opt-in retry layer — the wrapper owns the retry budget).
        """
        del timeout_s
        config_kwargs: dict[str, Any] = {
            "system_instruction": system_prompt,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if json_schema is not None:
            # `response_json_schema` transports the committed JSON-Schema
            # document verbatim (`responseJsonSchema` on the wire). The
            # legacy `response_schema` field runs the SDK's `t_schema`
            # translator, which rejects standard JSON-Schema keywords
            # (`$schema`, `$id`, `additionalProperties`, type unions,
            # `const`) — never use it for the committed prompt contracts.
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_json_schema"] = json_schema
        config = types.GenerateContentConfig(**config_kwargs)

        try:
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=user_payload,
                config=config,
            )
        except (genai_errors.APIError, httpx.TransportError) as exc:
            raise translate_transport_error(exc) from exc
        text = response.text or ""
        usage = response.usage_metadata
        input_tokens = (usage.prompt_token_count or 0) if usage is not None else 0
        output_tokens = (usage.candidates_token_count or 0) if usage is not None else 0
        return RawBackendResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=model,
            model_version=response.model_version or model,
        )
