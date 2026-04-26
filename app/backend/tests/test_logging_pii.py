"""Prove candidate PII cannot reach the serialised log record (constitution §15).

Mirrors the acceptance clause from ``docs/engineering/implementation-plan.md``
T02 verbatim: a single ``logger.info(...)`` call that carries candidate
email in **both** a structured field and the free-text message must see
the raw value scrubbed from both locations before the record leaves the
process.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
import structlog
from structlog.typing import EventDict

from app.backend.logging import PII_FIELDS, pii_redaction_processor

CANDIDATE_EMAIL = "x@y.com"
CYRILLIC_EMAIL = "студент@приклад.укр"


def _serialise(record: EventDict) -> str:
    """Best-effort stringification covering every key/value in the record."""
    return json.dumps(record, sort_keys=True, default=str, ensure_ascii=False)


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


def test_cyrillic_idn_email_redacted_in_freetext(
    captured_logs: list[EventDict],
) -> None:
    """Constitution §11 implies Ukrainian inputs; the redactor must follow."""
    structlog.get_logger("idn").info(f"contact {CYRILLIC_EMAIL} please")

    assert len(captured_logs) == 1
    blob = _serialise(captured_logs[0])
    assert CYRILLIC_EMAIL not in blob, f"Cyrillic email leaked: {blob!r}"
    assert "приклад.укр" not in blob, blob
    assert "<REDACTED_EMAIL>" in captured_logs[0]["message"], captured_logs[0]


def test_pii_redactor_does_not_mutate_input() -> None:
    """Pure transform: redactor returns a new dict and never edits its argument."""
    original: EventDict = cast(
        EventDict,
        {
            "event": f"hello {CANDIDATE_EMAIL}",
            "candidate_email": CANDIDATE_EMAIL,
            "other": 42,
        },
    )
    snapshot = dict(original)

    out = pii_redaction_processor(
        cast(structlog.typing.WrappedLogger, None),
        "info",
        original,
    )

    assert original == snapshot, f"input dict was mutated: {original!r}"
    assert out is not original, "redactor must return a new dict"
    assert out["candidate_email"] == "<REDACTED>"
    assert out["event"] == "hello <REDACTED_EMAIL>"
    assert out["other"] == 42, "non-PII fields preserved"


@pytest.mark.parametrize("field", sorted(PII_FIELDS))
def test_every_pii_field_in_allow_list_is_redacted(
    field: str, captured_logs: list[EventDict]
) -> None:
    """Adding a key to ``PII_FIELDS`` automatically gets coverage here.

    The allow-list extension procedure in ``backend-contract.md`` says
    new fields land alongside an explicit assertion. This parametrised
    test removes the "did the contributor remember to add a test" risk
    by enumerating ``PII_FIELDS`` at collection time.
    """
    structlog.get_logger("allow_list").info("ok", **{field: "leak@example.com"})

    assert len(captured_logs) == 1
    record = captured_logs[0]
    blob = _serialise(record)
    assert "leak@example.com" not in blob, f"{field} leaked: {blob!r}"
    assert record[field] == "<REDACTED>", f"{field} not redacted: {record!r}"
