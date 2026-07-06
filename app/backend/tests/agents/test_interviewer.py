"""Unit tests for the Interviewer agent wrapper (T18).

``call_model`` is monkeypatched at the interviewer module boundary — the
one mock this suite uses (coding-conventions: unit tests mock only the
LLM boundary). Prompt files are the REAL committed
``prompts/interviewer/v0001/`` + ``prompts/shared/`` artefacts; they are
deterministic repo files, so prompt-assembly assertions run against the
genuine bytes.

T18 acceptance (implementation-plan):
- unit test with mocked Vertex returns parsed object;
- schema miss → single retry → failure → typed exception.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.backend.agents.interviewer import (
    PROMPT_VERSION,
    InterviewerOutput,
    InterviewerOutputInvalid,
    InterviewerTurnInputs,
    RecentTurn,
    run_interviewer_turn,
)
from app.backend.llm import (
    ModelCallRequest,
    ModelCallResult,
    SessionBudgetExceeded,
    VertexSchemaError,
    VertexTimeoutError,
    WrapperError,
)
from app.backend.llm.cost_ledger import InMemoryCostLedger
from app.backend.llm.trace import InMemoryTraceSink
from app.backend.settings import Settings

_REPO_ROOT: Path = Path(__file__).resolve().parents[4]
_PROMPT_DIR: Path = _REPO_ROOT / "prompts" / "interviewer" / PROMPT_VERSION

_VALID_PARSED: dict[str, Any] = {
    "utterance": "Дякую, зрозуміло. Розкажіть, будь ласка, як ви підходите до кешування?",
    "internal_move_executed": "ask_seed",
}


def _make_inputs(**overrides: Any) -> InterviewerTurnInputs:
    """Build a valid frozen inputs object; keyword overrides for variants."""
    fields: dict[str, Any] = {
        "session_id": uuid4(),
        "interview_plan_snapshot": {"competencies": ["databases"], "minutes": 45},
        "current_competency": {"label": "Databases", "target_level": 2},
        "recent_turns": (
            RecentTurn(role="interviewer", text="Розкажіть про індекси."),
            RecentTurn(role="candidate", text="Індекси пришвидшують запити."),
        ),
        "next_planned_move": "ask_seed",
        "move_context": {"seed_question_id": "db-caching-01"},
        "candidate_first_name": None,
    }
    fields.update(overrides)
    return InterviewerTurnInputs(**fields)


def _make_result(parsed: dict[str, Any] | None) -> ModelCallResult:
    """A frozen ``ModelCallResult`` carrying the given parsed payload."""
    return ModelCallResult(
        text=json.dumps(parsed, ensure_ascii=False) if parsed is not None else "",
        parsed=parsed,
        input_tokens=100,
        output_tokens=40,
        cost_usd=Decimal("0.0005"),
        latency_ms=250,
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
        attempts=1,
        trace_id=uuid4(),
    )


class _ScriptedCallModel:
    """Async ``call_model`` stand-in returning/raising a scripted sequence.

    Records every :class:`ModelCallRequest` it receives so tests can
    assert on invocation count and request assembly.
    """

    def __init__(self, script: list[ModelCallResult | WrapperError]) -> None:
        self._script = list(script)
        self.requests: list[ModelCallRequest] = []

    async def __call__(
        self,
        request: ModelCallRequest,
        *,
        sink: object,
        ledger: object,
        settings: object,
    ) -> ModelCallResult:
        del sink, ledger, settings
        self.requests.append(request)
        if not self._script:
            raise AssertionError("scripted call_model exhausted; script every call")
        item = self._script.pop(0)
        if isinstance(item, WrapperError):
            raise item
        return item


def _install(
    monkeypatch: pytest.MonkeyPatch,
    script: list[ModelCallResult | WrapperError],
) -> _ScriptedCallModel:
    """Patch ``call_model`` at the interviewer module boundary."""
    fake = _ScriptedCallModel(script)
    monkeypatch.setattr("app.backend.agents.interviewer.call_model", fake)
    return fake


def _schema_error() -> VertexSchemaError:
    return VertexSchemaError("simulated schema miss", raw_payload="{broken")


# ---------------------------------------------------------------------------
# Prompt assembly — real repo files, no mock involved
# ---------------------------------------------------------------------------


def test_system_prompt_assembly_contains_all_three_parts() -> None:
    """system.md + level-guide.md + shared anchors, in that order."""
    from app.backend.agents.interviewer import _load_system_prompt

    assembled = _load_system_prompt()

    system_marker = "# Interviewer — system prompt — v0001"
    guide_marker = "# Interviewer — level prompting guide — v0001"
    anchors_marker = "# Ukrainian Style Anchors"
    for marker in (system_marker, guide_marker, anchors_marker):
        assert marker in assembled, f"missing prompt part: {marker!r}"
    assert (
        assembled.index(system_marker)
        < assembled.index(guide_marker)
        < assembled.index(anchors_marker)
    ), "prompt parts out of order (system.md §5–6: appendices follow the body)"


def test_output_schema_loader_matches_committed_contract() -> None:
    """The loaded json_schema is byte-equivalent to the committed schema.json."""
    from app.backend.agents.interviewer import _load_output_schema

    committed = json.loads((_PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))
    assert _load_output_schema() == committed


def test_output_schema_loader_returns_independent_copies() -> None:
    """Callers get deep copies — a downstream mutation must not poison the cache."""
    from app.backend.agents.interviewer import _load_output_schema

    first = _load_output_schema()
    first["properties"]["utterance"]["maxLength"] = 1  # simulated downstream mutation
    second = _load_output_schema()
    assert second["properties"]["utterance"]["maxLength"] == 1200
    assert second is not first


def test_prompt_version_matches_models_yaml_pin() -> None:
    """Module pin stays in lockstep with configs/models.yaml (§16, ADR-021)."""
    from app.backend.llm.models_config import MODELS_YAML_PATH, ModelsConfig

    config = ModelsConfig.from_yaml(MODELS_YAML_PATH)
    assert config.interviewer.prompt_version == PROMPT_VERSION


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_run_interviewer_turn_happy_path_returns_parsed_output(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    fake = _install(monkeypatch, [_make_result(_VALID_PARSED)])
    inputs = _make_inputs()

    output = await run_interviewer_turn(
        inputs,
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )

    assert isinstance(output, InterviewerOutput)
    assert output.utterance == _VALID_PARSED["utterance"]
    assert output.internal_move_executed == "ask_seed"
    assert len(fake.requests) == 1


async def test_run_interviewer_turn_request_carries_contract_and_default_caps(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """agent, session_id, schema.json, and untouched §12 default caps."""
    fake = _install(monkeypatch, [_make_result(_VALID_PARSED)])
    inputs = _make_inputs()

    await run_interviewer_turn(
        inputs,
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )

    request = fake.requests[0]
    assert request.agent == "interviewer"
    assert request.session_id == inputs.session_id
    assert request.model_override is None
    assert request.timeout_s == 30, "wrapper must not touch the §12 default timeout"
    assert request.max_output_tokens == 4096, "wrapper must not raise the §12 token cap"
    committed = json.loads((_PROMPT_DIR / "schema.json").read_text(encoding="utf-8"))
    assert request.json_schema == committed


async def test_run_interviewer_turn_payload_serializes_inputs_without_session_id(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """user_payload is the §3 input set as JSON; session_id stays out of it."""
    fake = _install(monkeypatch, [_make_result(_VALID_PARSED)])
    inputs = _make_inputs(candidate_first_name="Оксана")

    await run_interviewer_turn(
        inputs,
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )

    payload = json.loads(fake.requests[0].user_payload)
    assert set(payload.keys()) == {
        "interview_plan_snapshot",
        "current_competency",
        "recent_turns",
        "next_planned_move",
        "move_context",
        "candidate_first_name",
    }
    assert payload["next_planned_move"] == "ask_seed"
    assert payload["candidate_first_name"] == "Оксана"
    assert payload["recent_turns"][1] == {
        "role": "candidate",
        "text": "Індекси пришвидшують запити.",
    }
    assert str(inputs.session_id) not in fake.requests[0].user_payload


# ---------------------------------------------------------------------------
# Retry policy — schema-class failures retry exactly once
# ---------------------------------------------------------------------------


async def test_schema_miss_then_success_returns_output_after_single_retry(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    fake = _install(monkeypatch, [_schema_error(), _make_result(_VALID_PARSED)])

    output = await run_interviewer_turn(
        _make_inputs(),
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )

    assert output.internal_move_executed == "ask_seed"
    assert len(fake.requests) == 2, "one initial call + exactly one retry"


async def test_schema_miss_twice_raises_typed_exception_after_two_calls(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """T18 acceptance: schema miss → single retry → failure → typed exception."""
    fake = _install(monkeypatch, [_schema_error(), _schema_error()])

    with pytest.raises(InterviewerOutputInvalid) as excinfo:
        await run_interviewer_turn(
            _make_inputs(),
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )

    assert len(fake.requests) == 2, "retry budget is exactly one — no third call"
    assert isinstance(excinfo.value.__cause__, VertexSchemaError)


@pytest.mark.parametrize(
    "bad_parsed",
    [
        pytest.param(
            {"utterance": "Дякую.", "internal_move_executed": "not_a_move"},
            id="enum_violation",
        ),
        pytest.param(
            {"utterance": "а" * 1201, "internal_move_executed": "ask_seed"},
            id="utterance_over_1200_chars",
        ),
        pytest.param(
            {"utterance": "", "internal_move_executed": "ask_seed"},
            id="empty_utterance",
        ),
        pytest.param(
            {
                "utterance": "Дякую.",
                "internal_move_executed": "ask_seed",
                "extra_field": True,
            },
            id="additional_property",
        ),
        pytest.param(None, id="parsed_is_none"),
    ],
)
async def test_invalid_parsed_output_twice_raises_typed_exception(
    bad_parsed: dict[str, Any] | None,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """Contract violations in ``parsed`` take the same retry-then-raise path."""
    fake = _install(monkeypatch, [_make_result(bad_parsed), _make_result(bad_parsed)])

    with pytest.raises(InterviewerOutputInvalid) as excinfo:
        await run_interviewer_turn(
            _make_inputs(),
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )

    assert len(fake.requests) == 2
    assert isinstance(excinfo.value.__cause__, ValidationError)


async def test_invalid_parsed_output_then_valid_recovers_on_retry(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    bad = {"utterance": "Дякую.", "internal_move_executed": "not_a_move"}
    fake = _install(monkeypatch, [_make_result(bad), _make_result(_VALID_PARSED)])

    output = await run_interviewer_turn(
        _make_inputs(),
        sink=in_memory_trace_sink,
        ledger=in_memory_cost_ledger,
        settings=test_settings,
    )

    assert output.utterance == _VALID_PARSED["utterance"]
    assert len(fake.requests) == 2


async def test_schema_miss_then_invalid_parsed_output_raises_with_validation_cause(
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    """Mixed sequence: wrapper-level miss, then parsed-output violation.

    Both failure classes share the one-retry budget; the typed exception
    chains whichever failure came second (here: the ValidationError).
    """
    bad = {"utterance": "Дякую.", "internal_move_executed": "not_a_move"}
    fake = _install(monkeypatch, [_schema_error(), _make_result(bad)])

    with pytest.raises(InterviewerOutputInvalid) as excinfo:
        await run_interviewer_turn(
            _make_inputs(),
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )

    assert len(fake.requests) == 2, "mixed failures share the single retry budget"
    assert isinstance(excinfo.value.__cause__, ValidationError)
    assert not isinstance(excinfo.value.__cause__, VertexSchemaError)


# ---------------------------------------------------------------------------
# Non-schema wrapper errors — propagate untouched, no retry
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "wrapper_error",
    [
        pytest.param(VertexTimeoutError("wall-clock timeout after 30s"), id="timeout"),
        pytest.param(SessionBudgetExceeded("session at ceiling"), id="budget"),
    ],
)
async def test_non_schema_wrapper_error_propagates_without_retry(
    wrapper_error: WrapperError,
    monkeypatch: pytest.MonkeyPatch,
    in_memory_trace_sink: InMemoryTraceSink,
    in_memory_cost_ledger: InMemoryCostLedger,
    test_settings: Settings,
) -> None:
    fake = _install(monkeypatch, [wrapper_error])

    with pytest.raises(type(wrapper_error)):
        await run_interviewer_turn(
            _make_inputs(),
            sink=in_memory_trace_sink,
            ledger=in_memory_cost_ledger,
            settings=test_settings,
        )

    assert len(fake.requests) == 1, "non-schema wrapper errors must not be retried"


# ---------------------------------------------------------------------------
# Input model constraints
# ---------------------------------------------------------------------------


def test_inputs_reject_more_than_eight_recent_turns() -> None:
    turns = tuple(RecentTurn(role="candidate", text=f"turn {i}") for i in range(9))
    with pytest.raises(ValidationError) as excinfo:
        _make_inputs(recent_turns=turns)
    assert "recent_turns" in str(excinfo.value)


def test_inputs_reject_unknown_planned_move() -> None:
    with pytest.raises(ValidationError) as excinfo:
        _make_inputs(next_planned_move="improvise")
    assert "next_planned_move" in str(excinfo.value)
