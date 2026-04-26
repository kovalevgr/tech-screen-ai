"""Structural protocol for the Vertex backend implementations.

Both :class:`~app.backend.llm._real_backend.RealVertexBackend` and
:class:`~app.backend.llm._mock_backend.MockVertexBackend` satisfy
:class:`VertexBackend` structurally — neither inherits from the protocol.
This keeps the runtime cost at zero (Protocol is a `mypy --strict`
artefact only) and lets a future test backend or a T05 DB-backed sink
implementation slot in without touching the wrapper.

See `specs/007-t04-vertex-client-wrapper/data-model.md` §7 and
`contracts/wrapper-contract.md` §2.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


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

        Implementations MUST raise the wrapper's typed errors (or, for the
        real backend, ``google.api_core.exceptions.*`` which the wrapper
        translates) — never a bare ``Exception``.
        """
        ...
