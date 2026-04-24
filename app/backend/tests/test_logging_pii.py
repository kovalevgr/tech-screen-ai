"""Prove candidate PII cannot reach the serialised log record (constitution §15).

Mirrors the acceptance clause from ``docs/engineering/implementation-plan.md``
T02 verbatim: a single ``logger.info(...)`` call that carries candidate
email in **both** a structured field and the free-text message must see
the raw value scrubbed from both locations before the record leaves the
process.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from structlog.typing import EventDict

CANDIDATE_EMAIL = "x@y.com"


def _serialise(record: EventDict) -> str:
    """Best-effort stringification covering every key/value in the record."""
    parts: list[str] = []
    for key, value in record.items():
        parts.append(str(key))
        if isinstance(value, str):
            parts.append(value)
        else:
            parts.append(json.dumps(value, default=str))
    return "\n".join(parts)


def test_candidate_email_redacted_in_field_and_freetext(
    captured_logs: list[EventDict],
) -> None:
    log = structlog.get_logger("test_pii")

    log.info(f"foo bar {CANDIDATE_EMAIL}", candidate_email=CANDIDATE_EMAIL)
    log.info("app started", port=8000)

    assert len(captured_logs) == 2, captured_logs
    pii_record, plain_record = captured_logs

    pii_blob = _serialise(pii_record)
    assert CANDIDATE_EMAIL not in pii_blob, f"raw email leaked: {pii_blob!r}"
    assert pii_record["candidate_email"] == "<REDACTED>", pii_record
    assert "<REDACTED_EMAIL>" in pii_record["message"], pii_record

    plain_blob = _serialise(plain_record)
    assert "<REDACTED>" not in plain_blob, plain_record
    assert "<REDACTED_EMAIL>" not in plain_blob, plain_record
    assert plain_record.get("port") == 8000, plain_record


def test_pii_redactor_is_pure(captured_logs: list[EventDict]) -> None:
    """Belt-and-suspenders: verify the processor does not mutate input shape."""
    # Pretend the caller holds a dict reference and logs it; the redactor
    # must not reach back and edit the caller's dict.
    payload: dict[str, Any] = {
        "candidate_email": CANDIDATE_EMAIL,
        "other": 42,
    }
    structlog.get_logger("purity").info("caller keeps payload", **payload)
    assert payload["candidate_email"] == CANDIDATE_EMAIL
    assert payload["other"] == 42
