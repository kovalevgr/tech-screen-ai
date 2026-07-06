"""Unit tests for the Assessor agent wrapper (T19).

``call_model`` is monkeypatched at the assessor module boundary (the only
sanctioned mock seam per coding-conventions — the LLM boundary); prompt
files and ``schema.json`` are the REAL committed artefacts from
``prompts/assessor/v0001/``.

Constitution §15: every payload string here is synthetic non-PII content.
The T19 acceptance criterion (async, non-blocking scoring — ADR-007) is
covered by ``test_run_assessor_turn_does_not_block_event_loop_while_scoring``:
a stand-in "Interviewer produces turn N+1" coroutine completes while the
Assessor task is still pending. T18 code is deliberately NOT imported —
it lands on a sibling branch.
"""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.backend.agents import assessor
from app.backend.agents.assessor import (
    PROMPT_VERSION,
    AssessorEchoMismatch,
    AssessorOutput,
    AssessorOutputInvalid,
    AssessorTurnInput,
    load_output_schema,
    load_system_prompt,
    run_assessor_turn,
)
from app.backend.llm import (
    ModelCallRequest,
    ModelCallResult,
    SessionBudgetExceeded,
    TraceWriteError,
    VertexSchemaError,
    VertexTimeoutError,
    VertexUpstreamUnavailableError,
    WrapperError,
)
from app.backend.llm.cost_ledger import InMemoryCostLedger
from app.backend.llm.trace import InMemoryTraceSink
from app.backend.settings import Settings

_PROMPT_DIR: Path = Path(__file__).resolve().parents[4] / "prompts" / "assessor" / PROMPT_VERSION

_EXPECTED_PAYLOAD_KEYS: frozenset[str] = frozenset(
    {
        "rubric_snapshot_subset",
        "turn",
        "prior_turns",
        "competency_focus",
        "turn_metadata",
    }
)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def _make_inputs() -> AssessorTurnInput:
    """Synthetic, PII-free turn inputs (constitution §15)."""
    return AssessorTurnInput(
        session_id=uuid4(),
        turn_id=uuid4(),
        competency_focus="python.async",
        rubric_snapshot_subset=[
            {
                "id": "python.async",
                "label": "Asynchronous Python",
                "definition": "Understanding of the asyncio execution model.",
                "levels": {
                    "L1": "Names the event loop.",
                    "L2": "Explains cooperative scheduling with an example.",
                    "L3": "Reasons about blocking hazards and mitigation.",
                    "L4": "Questions whether async is the right tool at all.",
                },
            }
        ],
        turn={
            "interviewer_question": "Що таке event loop у Python?",
            "candidate_answer": "Це цикл подій, який по черзі виконує корутини.",
        },
        prior_turns=[],
    )


def _valid_parsed(inputs: AssessorTurnInput) -> dict[str, Any]:
    """A payload conforming to prompts/assessor/v0001/schema.json."""
    return {
        "turn_id": str(inputs.turn_id),
        "session_id": str(inputs.session_id),
        "competency_focus": inputs.competency_focus,
        "assessments": [
            {
                "rubric_node_id": "python.async",
                "level": 2,
                "confidence": 0.7,
                "rationale_en": (
                    "Candidate describes cooperative coroutine scheduling with a "
                    "concrete mechanism; matches the L2 descriptor."
                ),
                "evidence_spans": ["по черзі виконує корутини"],
            }
        ],
        "red_flags": [],
        "needs_manual_review": False,
        "manual_review_reason_en": None,
    }


def _ok_result(parsed: dict[str, Any]) -> ModelCallResult:
    return ModelCallResult(
        text=json.dumps(parsed, ensure_ascii=False),
        parsed=parsed,
        input_tokens=1200,
        output_tokens=280,
        cost_usd=Decimal("0.0031"),
        latency_ms=850,
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
        attempts=1,
        trace_id=uuid4(),
    )


def _schema_error() -> VertexSchemaError:
    return VertexSchemaError(
        "$.assessments[0]: missing required property 'level'",
        raw_payload='{"assessments": [{}]}',
    )


class _CallModelRecorder:
    """Scripted stand-in for ``call_model``, patched at the module boundary.

    Each script entry is either an exception instance (raised) or a
    :class:`ModelCallResult` (returned). Records every request so tests
    can assert invocation counts and request shape.
    """

    def __init__(self, script: list[BaseException | ModelCallResult]) -> None:
        self._script = list(script)
        self.requests: list[ModelCallRequest] = []

    async def __call__(
        self,
        request: ModelCallRequest,
        *,
        sink: InMemoryTraceSink,
        ledger: InMemoryCostLedger,
        settings: Settings,
    ) -> ModelCallResult:
        del sink, ledger, settings
        self.requests.append(request)
        if not self._script:
            raise AssertionError("recorder exhausted; script every expected call")
        item = self._script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sink() -> InMemoryTraceSink:
    return InMemoryTraceSink()


@pytest.fixture
def ledger() -> InMemoryCostLedger:
    return InMemoryCostLedger()


@pytest.fixture
def settings() -> Settings:
    return Settings()


# ---------------------------------------------------------------------------
# Prompt assembly — real files
# ---------------------------------------------------------------------------


def test_prompt_version_pinned_to_v0001() -> None:
    assert PROMPT_VERSION == "v0001"


def test_system_prompt_assembled_from_real_files_contains_expected_parts() -> None:
    prompt = load_system_prompt()
    system_text = (_PROMPT_DIR / "system.md").read_text(encoding="utf-8")
    guide_text = (_PROMPT_DIR / "level-guide.md").read_text(encoding="utf-8")
    notes_text = (_PROMPT_DIR / "notes.md").read_text(encoding="utf-8")

    # Full system.md first, full level-guide.md appended after it.
    assert system_text in prompt
    assert guide_text in prompt
    assert prompt.index(system_text) < prompt.index(guide_text)
    # Spot-check load-bearing sections survived assembly.
    assert "You are the Assessor" in prompt
    assert "## Confidence calibration" in prompt
    # notes.md is design history, not runtime prompt content.
    assert notes_text not in prompt
    # Cached: same object on repeat call — no per-call file I/O.
    assert load_system_prompt() is prompt


def test_output_schema_matches_committed_contract_file() -> None:
    committed = json.loads((_PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))
    assert load_output_schema() == committed
    # Fresh dict per call — caller mutation cannot poison the cache.
    first = load_output_schema()
    second = load_output_schema()
    assert first is not second


# ---------------------------------------------------------------------------
# Happy path + request shape
# ---------------------------------------------------------------------------


async def test_run_assessor_turn_happy_path_returns_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    inputs = _make_inputs()
    recorder = _CallModelRecorder([_ok_result(_valid_parsed(inputs))])
    monkeypatch.setattr(assessor, "call_model", recorder)

    output = await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert isinstance(output, AssessorOutput)
    assert output.turn_id == inputs.turn_id
    assert output.session_id == inputs.session_id
    assert output.competency_focus == "python.async"
    assert output.assessments[0].level == 2
    assert output.assessments[0].confidence == pytest.approx(0.7)
    assert output.red_flags == []
    assert output.needs_manual_review is False
    assert len(recorder.requests) == 1


async def test_run_assessor_turn_request_uses_default_caps_and_contract_payload(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    inputs = _make_inputs()
    recorder = _CallModelRecorder([_ok_result(_valid_parsed(inputs))])
    monkeypatch.setattr(assessor, "call_model", recorder)

    await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    request = recorder.requests[0]
    assert request.agent == "assessor"
    assert request.session_id == inputs.session_id
    # §12: defaults, never raised by the agent module.
    assert request.timeout_s == 30
    assert request.max_output_tokens == 4096
    assert request.model_override is None
    # The committed schema.json travels as json_schema.
    committed = json.loads((_PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))
    assert request.json_schema == committed
    # System prompt is the assembled two-file prompt.
    assert request.system_prompt == load_system_prompt()
    # user_payload mirrors system.md §3 INPUTS key-for-key; ids re-nested.
    payload = json.loads(request.user_payload)
    assert set(payload) == _EXPECTED_PAYLOAD_KEYS
    assert payload["turn_metadata"]["turn_id"] == str(inputs.turn_id)
    assert payload["turn_metadata"]["session_id"] == str(inputs.session_id)
    assert payload["competency_focus"] == inputs.competency_focus
    assert payload["turn"] == inputs.turn


def test_to_user_payload_typed_ids_win_over_conflicting_metadata() -> None:
    """Caller-supplied turn_metadata ids must never override the typed ids
    in the wire payload — trace/ledger attribution uses the typed ones."""
    base = _make_inputs()
    inputs = base.model_copy(
        update={
            "turn_metadata": {
                "turn_id": "0f0f0f0f-0f0f-0f0f-0f0f-0f0f0f0f0f0f",
                "session_id": "1e1e1e1e-1e1e-1e1e-1e1e-1e1e1e1e1e1e",
                "asked_at": "2026-07-06T10:00:00Z",
            }
        }
    )

    payload = json.loads(inputs.to_user_payload())

    assert payload["turn_metadata"]["turn_id"] == str(inputs.turn_id)
    assert payload["turn_metadata"]["session_id"] == str(inputs.session_id)
    # Non-conflicting caller metadata is preserved.
    assert payload["turn_metadata"]["asked_at"] == "2026-07-06T10:00:00Z"


# ---------------------------------------------------------------------------
# Retry policy — schema misses
# ---------------------------------------------------------------------------


async def test_run_assessor_turn_schema_miss_then_success_retries_once(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    inputs = _make_inputs()
    recorder = _CallModelRecorder([_schema_error(), _ok_result(_valid_parsed(inputs))])
    monkeypatch.setattr(assessor, "call_model", recorder)

    output = await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert isinstance(output, AssessorOutput)
    assert output.turn_id == inputs.turn_id
    assert len(recorder.requests) == 2


async def test_run_assessor_turn_schema_miss_twice_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    inputs = _make_inputs()
    second_miss = _schema_error()
    recorder = _CallModelRecorder([_schema_error(), second_miss])
    monkeypatch.setattr(assessor, "call_model", recorder)

    with pytest.raises(AssessorOutputInvalid) as excinfo:
        await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert len(recorder.requests) == 2
    assert excinfo.value.__cause__ is second_miss


@pytest.mark.parametrize(
    ("field_mutation", "expected_fragment"),
    [
        pytest.param({"confidence": 1.0}, "confidence", id="confidence-1.0-forbidden"),
        pytest.param({"level": 5}, "level", id="level-5-out-of-enum"),
        pytest.param({"evidence_spans": []}, "evidence_spans", id="empty-evidence-spans"),
    ],
)
async def test_run_assessor_turn_contract_violating_payload_retries_then_raises(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    field_mutation: dict[str, Any],
    expected_fragment: str,
) -> None:
    """Payloads that pass the wrapper's structural check but violate the
    tighter AssessorOutput bounds follow the same retry-once-then-raise path."""
    inputs = _make_inputs()
    bad = _valid_parsed(inputs)
    bad["assessments"][0].update(field_mutation)
    recorder = _CallModelRecorder([_ok_result(bad), _ok_result(bad)])
    monkeypatch.setattr(assessor, "call_model", recorder)

    with pytest.raises(AssessorOutputInvalid) as excinfo:
        await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert len(recorder.requests) == 2
    cause = excinfo.value.__cause__
    assert isinstance(cause, ValidationError)
    assert expected_fragment in str(cause)


async def test_run_assessor_turn_contract_violation_then_valid_retry_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    inputs = _make_inputs()
    bad = _valid_parsed(inputs)
    bad["assessments"][0]["confidence"] = 1.0
    recorder = _CallModelRecorder([_ok_result(bad), _ok_result(_valid_parsed(inputs))])
    monkeypatch.setattr(assessor, "call_model", recorder)

    output = await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert output.assessments[0].confidence == pytest.approx(0.7)
    assert len(recorder.requests) == 2


async def test_run_assessor_turn_echoed_id_mismatch_then_success_retries_once(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    """A hallucinated-but-well-formed echoed turn_id is a contract miss —
    same retry-once path as a schema miss."""
    inputs = _make_inputs()
    hallucinated = _valid_parsed(inputs)
    hallucinated["turn_id"] = str(uuid4())  # UUID-shaped, but not OUR turn
    recorder = _CallModelRecorder([_ok_result(hallucinated), _ok_result(_valid_parsed(inputs))])
    monkeypatch.setattr(assessor, "call_model", recorder)

    output = await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert output.turn_id == inputs.turn_id
    assert len(recorder.requests) == 2


async def test_run_assessor_turn_echoed_id_mismatch_twice_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    inputs = _make_inputs()
    wrong_session = str(uuid4())
    hallucinated = _valid_parsed(inputs)
    hallucinated["session_id"] = wrong_session
    recorder = _CallModelRecorder([_ok_result(hallucinated), _ok_result(dict(hallucinated))])
    monkeypatch.setattr(assessor, "call_model", recorder)

    with pytest.raises(AssessorOutputInvalid) as excinfo:
        await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert len(recorder.requests) == 2
    cause = excinfo.value.__cause__
    assert isinstance(cause, AssessorEchoMismatch)
    # Diagnosable: names the mismatched field, expected vs got.
    assert "session_id mismatch" in str(cause)
    assert str(inputs.session_id) in str(cause)
    assert wrong_session in str(cause)


# ---------------------------------------------------------------------------
# Non-schema wrapper errors — propagate untouched, no retry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wrapper_error",
    [
        pytest.param(VertexTimeoutError("wall-clock timeout after 30s"), id="timeout"),
        pytest.param(
            VertexUpstreamUnavailableError("retries exhausted"), id="upstream-unavailable"
        ),
        pytest.param(SessionBudgetExceeded("session at ceiling"), id="budget-exceeded"),
        pytest.param(TraceWriteError("sink write failed"), id="trace-write-error"),
    ],
)
async def test_run_assessor_turn_non_schema_wrapper_error_propagates_without_retry(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
    wrapper_error: WrapperError,
) -> None:
    inputs = _make_inputs()
    recorder = _CallModelRecorder([wrapper_error])
    monkeypatch.setattr(assessor, "call_model", recorder)

    with pytest.raises(type(wrapper_error)) as excinfo:
        await run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)

    assert excinfo.value is wrapper_error
    assert len(recorder.requests) == 1


# ---------------------------------------------------------------------------
# T19 acceptance — async, non-blocking scoring (ADR-007 voice-readiness)
# ---------------------------------------------------------------------------


async def test_run_assessor_turn_does_not_block_event_loop_while_scoring(
    monkeypatch: pytest.MonkeyPatch,
    sink: InMemoryTraceSink,
    ledger: InMemoryCostLedger,
    settings: Settings,
) -> None:
    """The Interviewer stand-in produces turn N+1 while the Assessor is
    still scoring turn N. Deterministic: gated on asyncio events, no real
    sleeps beyond wait_for safety timeouts."""
    inputs = _make_inputs()
    parsed = _valid_parsed(inputs)
    assessor_entered_llm = asyncio.Event()
    release_assessor = asyncio.Event()

    async def slow_call_model(
        request: ModelCallRequest,
        *,
        sink: InMemoryTraceSink,
        ledger: InMemoryCostLedger,
        settings: Settings,
    ) -> ModelCallResult:
        del request, sink, ledger, settings
        assessor_entered_llm.set()
        await asyncio.wait_for(release_assessor.wait(), timeout=1.0)
        return _ok_result(parsed)

    monkeypatch.setattr(assessor, "call_model", slow_call_model)

    async def interviewer_stub() -> str:
        # Stand-in for "the Interviewer produces turn N+1". T18 lands on a
        # sibling branch and is deliberately NOT imported here.
        await asyncio.sleep(0)
        return "turn-n-plus-1"

    scoring_task = asyncio.create_task(
        run_assessor_turn(inputs, sink=sink, ledger=ledger, settings=settings)
    )

    # The Assessor coroutine reaches the (slow) LLM boundary without
    # blocking the event loop...
    await asyncio.wait_for(assessor_entered_llm.wait(), timeout=0.1)
    # ...and the Interviewer stand-in completes while scoring is pending.
    produced = await asyncio.wait_for(interviewer_stub(), timeout=0.1)
    assert produced == "turn-n-plus-1"
    assert not scoring_task.done()

    release_assessor.set()
    output = await asyncio.wait_for(scoring_task, timeout=1.0)
    assert isinstance(output, AssessorOutput)
    assert output.turn_id == inputs.turn_id
