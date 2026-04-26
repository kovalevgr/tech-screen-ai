"""Vertex AI client wrapper — public surface.

Importable symbols (every other LLM-touching module imports from here):

- :func:`call_model`               — the single sanctioned async entry point.
- :class:`ModelCallRequest`        — typed input.
- :class:`ModelCallResult`         — typed output.
- :class:`WrapperError` and the six typed children — error envelope.

Internal modules (`_real_backend`, `_mock_backend`, `_backend_protocol`,
`pricing`, `models_config`, `trace`, `cost_ledger`) are accessible by name
but not re-exported here — callers either depend on the public surface or
inject one of the protocol-shaped collaborators (`TraceSink`, `CostLedger`).
"""

from __future__ import annotations

from app.backend.llm.errors import (
    ModelCallConfigError,
    SessionBudgetExceeded,
    TraceWriteError,
    VertexSchemaError,
    VertexTimeoutError,
    VertexUpstreamUnavailableError,
    WrapperError,
)
from app.backend.llm.vertex import ModelCallRequest, ModelCallResult, call_model

__all__ = [
    "ModelCallConfigError",
    "ModelCallRequest",
    "ModelCallResult",
    "SessionBudgetExceeded",
    "TraceWriteError",
    "VertexSchemaError",
    "VertexTimeoutError",
    "VertexUpstreamUnavailableError",
    "WrapperError",
    "call_model",
]
