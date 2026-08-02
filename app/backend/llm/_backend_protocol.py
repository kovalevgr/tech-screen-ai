"""Structural protocol for the Vertex backend implementations.

Both :class:`~app.backend.llm._real_backend.RealVertexBackend` and
:class:`~app.backend.llm._mock_backend.MockVertexBackend` satisfy
:class:`VertexBackend` structurally — neither inherits from the protocol.
This keeps the runtime cost at zero (Protocol is a `mypy --strict`
artefact only) and lets a future test backend or a T05 DB-backed sink
implementation slot in without touching the wrapper.

This module also defines the **transport-classification errors**
(:class:`BackendError` and its children). They are the SDK-free contract
between a backend and the wrapper's retry loop: the real backend
translates every provider-SDK exception (``google.genai.errors.*``,
``httpx.*``) into one of these before it escapes ``generate()``, so
``vertex.py`` never has to import a provider SDK to classify failures
(guardrail: ``scripts/check-no-provider-sdk-imports.sh``).

See `specs/007-t04-vertex-client-wrapper/data-model.md` §7,
`contracts/wrapper-contract.md` §2, and
`specs/030-schema-transport-real-vertex/plan.md` (taxonomy rework).
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class BackendError(Exception):
    """Base for transport-level classification errors raised by backends.

    Never surfaced to wrapper callers — ``vertex.py`` translates every
    :class:`BackendError` into the public typed hierarchy in
    ``errors.py`` (`VertexTimeoutError`, `ModelCallConfigError`,
    `VertexUpstreamUnavailableError`).
    """


class BackendTransientError(BackendError):
    """Transient upstream failure — retryable under the 3-attempt budget.

    Real backend raises this for HTTP 429 and HTTP 5xx (except 504) and
    for connection-level transport failures (refused / reset / broken
    stream).
    """


class BackendDeadlineExceededError(BackendError):
    """Upstream/transport deadline fired — NOT retried.

    Equivalent of the legacy ``google.api_core.exceptions.DeadlineExceeded``
    (HTTP 504) per Clarifications 2026-04-26: the timeout already burned
    wall clock; retrying only eats the remaining 30-s budget.
    """


class BackendCallerError(BackendError):
    """Caller-side rejection (HTTP 400 / 403) — NOT retried.

    The wrapper translates this to :class:`ModelCallConfigError`.
    """


class BackendUpstreamError(BackendError):
    """Any other upstream API failure (401, 404, 408, …) — NOT retried.

    The wrapper translates this to :class:`VertexUpstreamUnavailableError`,
    preserving the pre-030 catch-all semantics for unclassified provider
    errors.
    """


class RawBackendResult(BaseModel):
    """The minimum envelope a backend returns to the wrapper.

    Frozen — once a backend builds a result, neither the wrapper nor the
    caller may mutate it. The wrapper computes cost and trace metadata
    from these fields and discards the rest of any provider-specific
    response (safety ratings, usage breakdowns, etc. are out of T04 scope).
    """

    model_config = ConfigDict(frozen=True)

    text: str
    """Raw response text. For JSON-mode calls this is the JSON-encoded payload."""

    input_tokens: int = Field(ge=0)
    """Token count Vertex billed for the input portion of the call."""

    output_tokens: int = Field(ge=0)
    """Token count Vertex billed for the output portion of the call."""

    model: str = Field(min_length=1)
    """Resolved model identifier (e.g., ``"gemini-2.5-flash"``)."""

    model_version: str = Field(min_length=1)
    """Specific model revision (e.g., ``"gemini-2.5-flash-001"``)."""


class VertexBackend(Protocol):
    """Structural shape both real and mock backends implement."""

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
        """Issue a single backend call and return the raw envelope.

        Implementations MUST raise either the wrapper's typed errors or a
        :class:`BackendError` subclass (the real backend translates every
        provider-SDK exception into one before it escapes). Anything else
        is classified as upstream-unavailable by the wrapper's defensive
        catch-all.
        """
        ...
