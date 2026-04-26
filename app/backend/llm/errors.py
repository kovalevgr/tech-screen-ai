"""Typed error hierarchy for the Vertex AI client wrapper.

Every wrapper-side failure raises a subclass of :class:`WrapperError`.
A blanket `except WrapperError:` catches everything the wrapper can raise;
specific subclasses let callers (agent modules, the orchestrator) apply
per-error policy. See `specs/007-t04-vertex-client-wrapper/data-model.md`
§6 for the full table mapping each error to its trace `outcome` value.

Per Clarifications 2026-04-26 (spec.md):
- The wrapper does NOT retry on schema validation failures —
  `VertexSchemaError` is raised immediately with `raw_payload` attached
  so the agent module can apply its own per-agent retry / fallback /
  escalation policy.
- Trace-sink failure raises :class:`TraceWriteError` and the call is
  treated as failed (constitution §1 — auditability is non-negotiable).
"""

from __future__ import annotations


class WrapperError(Exception):
    """Base for every typed wrapper error. Catch this for blanket handling."""


class ModelCallConfigError(WrapperError):
    """Caller-side error: invalid request, unknown model, unknown agent.

    Trace `outcome` = "config_error". No backend call is performed.
    """


class VertexTimeoutError(WrapperError):
    """30-second wall-clock budget exceeded across all retries.

    Trace `outcome` = "timeout". Per Clarifications 2026-04-26 the underlying
    `google.api_core.exceptions.DeadlineExceeded` is excluded from retry —
    the timeout already fired, repeating it only burns the 30-s budget.
    """


class VertexUpstreamUnavailableError(WrapperError):
    """Retry budget exhausted on transient upstream failures.

    Trace `outcome` = "upstream_unavailable". Raised after the uniform
    3-attempt budget (1 initial + 2 retries) has been exhausted on the
    set: HTTP 5xx (`ServiceUnavailable`, `InternalServerError`),
    HTTP 429 (`ResourceExhausted`), and connection-level errors.
    """


class VertexSchemaError(WrapperError):
    """Schema validation failed. Carries the raw payload for debugging.

    Per Clarifications 2026-04-26: wrapper does NOT retry on this error;
    agent modules apply their own per-agent policies. The raw payload is
    NEVER logged by the wrapper — the caller is responsible for any
    payload-aware diagnostics.

    Trace `outcome` = "schema_error".
    """

    def __init__(self, message: str, *, raw_payload: str) -> None:
        super().__init__(message)
        self.raw_payload = raw_payload


class SessionBudgetExceeded(WrapperError):
    """Per-session cost ceiling tripped before this call (constitution §12).

    Trace `outcome` = "budget_exceeded". No backend call is performed; the
    trace record is still emitted with `cost_usd=0` and zero token counts.
    """


class TraceWriteError(WrapperError):
    """Trace sink failed to persist a record.

    Per Clarifications 2026-04-26 the wrapper raises this rather than
    swallowing — auditability (constitution §1) is non-negotiable. The
    orchestrator (T20) treats this as a session-halting condition because
    the call escaped audit.

    Trace `outcome` = "trace_write_error". (For the in-memory sink the
    record was never written; for the durable sink in T05+ the record may
    be unwritten or partially written — operators reconcile via a
    fallback emergency log.)
    """
