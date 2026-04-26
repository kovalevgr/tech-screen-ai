"""Structured logging configuration for the backend.

The processor pipeline defined here is the single place where candidate PII
is scrubbed from log records before they leave the process (constitution
§15). The PII redactor itself is installed by :mod:`app.backend.logging`'s
:func:`configure_logging`.
"""

from __future__ import annotations

import logging
import os
import re
import sys
from typing import Any, Final

import structlog
from structlog.typing import EventDict, WrappedLogger

_VALID_FORMATS: Final[frozenset[str]] = frozenset({"json", "console"})
_VALID_LEVELS: Final[frozenset[str]] = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})

PII_FIELDS: Final[frozenset[str]] = frozenset({"candidate_email"})
"""Keys whose values must be redacted before serialisation.

Extension-only: new tasks add fields here AND extend ``test_logging_pii``
with matching assertions in the same PR. Removal requires an ADR that
supersedes constitution §15.
"""

_EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(r"[\w.+%-]+@[\w.-]+\.[\w-]{2,}")
"""Permissive Unicode-aware email regex — false-positives over false-negatives.

``\\w`` matches Latin, Cyrillic, Greek, etc. word characters in Python 3
(the default ``re.UNICODE`` mode for ``str`` patterns), so IDN-style
addresses such as ``студент@приклад.укр`` are redacted alongside ASCII
emails. Punycode-encoded variants (``student@xn--p1ai``) are matched by
the same pattern because the TLD class allows hyphens.
"""

_REDACTED: Final[str] = "<REDACTED>"
_REDACTED_EMAIL: Final[str] = "<REDACTED_EMAIL>"


def pii_redaction_processor(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Redact :data:`PII_FIELDS` values and email patterns in ``event``.

    Pure transform: never logs, never raises, never mutates the input
    dict. Runs before ``EventRenamer`` so the message key is still
    ``event``.
    """
    del logger, method_name
    redacted: EventDict = dict(event_dict)
    for key in PII_FIELDS & redacted.keys():
        redacted[key] = _REDACTED
    event = redacted.get("event")
    if isinstance(event, str):
        redacted["event"] = _EMAIL_PATTERN.sub(_REDACTED_EMAIL, event)
    return redacted


def _resolve_log_format(log_format: str | None) -> str:
    candidate = (log_format or os.environ.get("LOG_FORMAT") or "json").lower()
    if candidate in _VALID_FORMATS:
        return candidate
    sys.stderr.write(f"logging: unknown LOG_FORMAT={candidate!r}, falling back to 'json'\n")
    return "json"


def _resolve_log_level(log_level: str | None) -> int:
    candidate = (log_level or os.environ.get("LOG_LEVEL") or "INFO").upper()
    if candidate in _VALID_LEVELS:
        return logging.getLevelNamesMapping()[candidate]
    sys.stderr.write(f"logging: unknown LOG_LEVEL={candidate!r}, falling back to 'INFO'\n")
    return logging.INFO


def configure_logging(
    *,
    log_format: str | None = None,
    log_level: str | None = None,
) -> None:
    """Install the structlog processor pipeline.

    Idempotent — safe to call multiple times. Arguments default to the
    ``LOG_FORMAT`` / ``LOG_LEVEL`` env vars with ``"json"`` / ``"INFO"``
    fallbacks and warn-and-fallback on unknown values.
    """
    resolved_format = _resolve_log_format(log_format)
    resolved_level = _resolve_log_level(log_level)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=resolved_level,
        force=True,
    )

    renderer: Any
    if resolved_format == "console":
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        renderer = structlog.processors.JSONRenderer()

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        pii_redaction_processor,
        structlog.processors.EventRenamer("message"),
        renderer,
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(resolved_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
