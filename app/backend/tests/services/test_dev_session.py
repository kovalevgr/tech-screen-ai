"""The imperative shell over the T20 machine (T22 backend half).

DB-gated and driven against the REAL mock backend: the fixtures under
``app/backend/tests/fixtures/llm_responses/`` are keyed by canonical prompt
SHA, so the happy path here also proves that the payloads the shell assembles
are byte-stable. Only :data:`_E2E_SESSION_ID` is fixed — the Assessor echoes
the session id, so its prompt SHA depends on it.

Every test purges its own session before and after (as ``techscreen_migrator``,
the §3-exempt role) so the suite is re-runnable against the same database.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backend.agents.interviewer import InterviewerOutput, InterviewerTurnInputs
from app.backend.llm.persistent_trace import PostgresTraceSink
from app.backend.llm.trace import TraceRecord
from app.backend.orchestrator.config import load_orchestrator_config
from app.backend.services import dev_session as shell
from app.backend.services.dev_session import (
    DevSessionNotAwaitingCandidate,
    DevSessionNotFound,
    DevSessionPlanInvalid,
    DevSessionService,
    ImmediateTaskScheduler,
    _extract_script,
)
from app.backend.settings import Settings
from app.backend.tests.conftest import purge_session, session_ids

# ``asyncio_mode = "auto"`` (pyproject) runs the coroutines; the two pure
# helpers below stay synchronous, so no module-level asyncio mark here.

_FIXTURES: Path = Path(__file__).resolve().parents[1] / "fixtures" / "llm_responses"

_E2E_SESSION_ID = uuid.UUID("33333333-3333-5333-8333-333333333333")

PLAN: dict[str, Any] = {
    "plan_version": 1,
    "competencies": [
        {
            "node_id": "py.async",
            "label_uk": "Асинхронний Python",
            "target_level": 3,
            "minutes": 12,
            "seed_questions_uk": ["Що таке event loop?"],
            "probe_branches_uk": ["Розкажіть про await", "А про таймаути?"],
        }
    ],
    "qa_minutes": 0,
    "session_max_minutes": 60,
}

TURNS: tuple[str, ...] = (
    "Так, готовий почати.",
    "Event loop керує корутинами.",
    "await віддає контроль назад до циклу.",
    "Таймаути роблю через asyncio.wait_for.",
    "У мене немає запитань, дякую.",
)


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


@dataclass
class _Harness:
    service: DevSessionService
    scheduler: ImmediateTaskScheduler
    engine: AsyncEngine

    async def turn(self, session_id: uuid.UUID, text_value: str) -> shell.TurnResult:
        """Post a turn and drain the background assessor so tests stay ordered."""
        result = await self.service.post_turn(session_id, text_value)
        await self.scheduler.drain()
        return result


def _settings() -> Settings:
    return Settings(
        llm_backend="mock",
        app_env="test",
        llm_budget_per_session_usd=Decimal("5.00"),
        llm_fixtures_dir=_FIXTURES,
    )


def _harness(
    engine: AsyncEngine,
    *,
    ceiling_usd: Decimal | None = None,
    enforcement: Callable[[], Coroutine[Any, Any, bool]] | None = None,
) -> _Harness:
    scheduler = ImmediateTaskScheduler()
    service = DevSessionService(
        engine=engine,
        settings=_settings(),
        config=load_orchestrator_config(),
        scheduler=scheduler,
        ceiling_usd=ceiling_usd,
        enforcement=enforcement,
    )
    return _Harness(service=service, scheduler=scheduler, engine=engine)


@pytest.fixture
async def e2e(db_engine: AsyncEngine, clean_sessions: None) -> _Harness:
    """Harness pinned to the deterministic e2e session id.

    The id is fixed because the Assessor echoes it, so its prompt SHA — and
    therefore its mock fixture — depends on it. A leftover row from a previous
    run would collide, hence the up-front purge.
    """
    await purge_session(db_engine, _E2E_SESSION_ID)
    return _harness(db_engine)


@pytest.fixture
async def ephemeral(db_engine: AsyncEngine, clean_sessions: None) -> _Harness:
    """Harness for tests that do not need a fixed session id."""
    return _harness(db_engine)


async def _enforced() -> bool:
    return True


async def _not_enforced() -> bool:
    return False


async def _charge(engine: AsyncEngine, session_id: uuid.UUID, amount: str) -> None:
    from datetime import UTC, datetime

    await PostgresTraceSink(engine).write(
        TraceRecord(
            id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            agent="assessor",
            session_id=session_id,
            model="gemini-2.5-flash",
            prompt_sha256="e" * 64,
            outcome="ok",
            attempts=1,
            latency_ms=1,
            input_tokens=1,
            output_tokens=1,
            cost_usd=Decimal(amount),
        )
    )


# ---------------------------------------------------------------------------
# SC-3 — the full dev-session happy path
# ---------------------------------------------------------------------------


async def test_the_happy_path_reaches_completed_with_every_turn_traced(
    e2e: _Harness,
) -> None:
    view = await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()

    assert view.phase == "INTRO"
    assert view.session_id == _E2E_SESSION_ID

    for candidate_text in TURNS:
        if view.phase in ("COMPLETED", "ABORTED"):
            break
        view = (await e2e.turn(_E2E_SESSION_ID, candidate_text)).session

    assert view.phase == "COMPLETED"
    assert view.abort_reason is None
    assert view.awaiting is None
    assert Decimal(view.cost_usd_total) > 0

    traces = await e2e.service.list_traces(_E2E_SESSION_ID)
    agents = [row.agent for row in traces.traces]
    assert agents.count("interviewer") == 4
    assert agents.count("assessor") == 3
    assert all(row.outcome == "ok" for row in traces.traces)


async def test_every_trace_row_carries_the_orchestrator_context(e2e: _Harness) -> None:
    await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()
    await e2e.turn(_E2E_SESSION_ID, TURNS[0])

    traces = await e2e.service.list_traces(_E2E_SESSION_ID)

    assert len(traces.traces) == 1
    row = traces.traces[0]
    assert row.agent == "interviewer"
    assert row.prompt_version == "v0001"
    assert row.turn_id is not None
    assert row.transition is not None
    assert row.transition["phase"] == "tech"
    assert row.transition["issued_move"] == "ask_seed"
    assert len(row.transition["state_before_sha"]) == 64
    assert row.transition["state_after_sha"] != row.transition["state_before_sha"]
    assert "INTERVIEWER" in row.system_prompt.upper()
    assert "ask_seed" in row.user_payload


async def test_the_cost_total_equals_the_sum_of_the_trace_rows(e2e: _Harness) -> None:
    """Spec Clarification 1 — one source of truth, no second table."""
    await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()
    await e2e.turn(_E2E_SESSION_ID, TURNS[0])
    await e2e.turn(_E2E_SESSION_ID, TURNS[1])

    view = await e2e.service.get_session(_E2E_SESSION_ID)
    traces = await e2e.service.list_traces(_E2E_SESSION_ID)
    expected = sum((Decimal(row.cost_usd) for row in traces.traces), Decimal("0"))

    assert len(traces.traces) == 3
    assert Decimal(view.cost_usd_total) == expected


async def test_the_assessor_runs_in_the_background_and_updates_coverage(
    e2e: _Harness,
) -> None:
    """§6.1: the interviewer's next move never waits for the assessment."""
    await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()
    await e2e.turn(_E2E_SESSION_ID, TURNS[0])

    result = await e2e.service.post_turn(_E2E_SESSION_ID, TURNS[1])

    # The turn is already answered while the assessment is still queued.
    assert result.utterance is not None
    assert e2e.scheduler.pending == 1
    assert result.session.coverage == {}

    await e2e.scheduler.drain()
    after = await e2e.service.get_session(_E2E_SESSION_ID)
    assert after.coverage["py.async"]["best_level"] == 1
    assert after.coverage["py.async"]["best_confidence"] == 0.7


# ---------------------------------------------------------------------------
# Ordering (contract §9 / spec-032 Clarification 4)
# ---------------------------------------------------------------------------


async def test_state_is_persisted_before_the_interviewer_call(
    e2e: _Harness, db_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shell's central obligation, observed from inside the wrapper call."""
    observed: list[dict[str, Any]] = []

    async def _spy(inputs: InterviewerTurnInputs, **kwargs: Any) -> InterviewerOutput:
        async with db_engine.connect() as conn:
            stored = (
                await conn.execute(
                    text("SELECT session_state FROM interview_session WHERE id = :s"),
                    {"s": inputs.session_id},
                )
            ).scalar_one()
        observed.append(stored)
        return InterviewerOutput(
            utterance="Питання.", internal_move_executed=inputs.next_planned_move
        )

    monkeypatch.setattr(shell, "run_interviewer_turn", _spy)
    await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()

    await e2e.service.post_turn(_E2E_SESSION_ID, TURNS[0])

    assert len(observed) == 1
    persisted = observed[0]
    # Already the POST-transition state: TECH, waiting on the interviewer, with
    # the very command being executed recorded as pending.
    assert persisted["phase"] == "tech"
    assert persisted["awaiting"] == "interviewer"
    assert persisted["last_issued_move"] == "ask_seed"
    assert persisted["pending_command"]["kind"] == "run_interviewer"


# ---------------------------------------------------------------------------
# SC-2 — the cost ceiling, end to end
# ---------------------------------------------------------------------------


async def test_a_ceiling_breach_with_the_flag_on_aborts_and_records_a_decision(
    db_engine: AsyncEngine, clean_sessions: None
) -> None:
    harness = _harness(db_engine, ceiling_usd=Decimal("1.00"), enforcement=_enforced)
    view = await harness.service.create_session(PLAN)
    session_id = view.session_id
    await _charge(db_engine, session_id, "1.500000")

    result = await harness.turn(session_id, TURNS[0])

    assert result.utterance is None
    assert result.session.phase == "ABORTED"
    assert result.session.abort_reason == "cost_ceiling"

    async with db_engine.connect() as conn:
        reasons = (
            await conn.execute(
                text("SELECT reason FROM session_decision WHERE interview_session_id = :s"),
                {"s": session_id},
            )
        ).scalars()
        assert list(reasons) == ["cost_ceiling"]


async def test_a_ceiling_breach_with_the_flag_off_only_warns(
    db_engine: AsyncEngine, clean_sessions: None
) -> None:
    """§9 dark launch: the default configuration never aborts a live interview."""
    harness = _harness(db_engine, ceiling_usd=Decimal("1.00"), enforcement=_not_enforced)
    view = await harness.service.create_session(PLAN)
    session_id = view.session_id
    await _charge(db_engine, session_id, "1.500000")

    result = await harness.turn(session_id, TURNS[0])

    assert result.session.phase == "TECH"
    assert result.session.abort_reason is None
    assert result.utterance is not None

    async with db_engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM session_decision WHERE interview_session_id = :s"),
                {"s": session_id},
            )
        ).scalar_one()
        assert count == 0


# ---------------------------------------------------------------------------
# Scripted strings (spec Clarification 3)
# ---------------------------------------------------------------------------


async def test_the_opening_is_the_repo_script_with_variables_substituted(
    ephemeral: _Harness,
) -> None:
    view = await ephemeral.service.create_session(PLAN)

    opening = view.transcript[0]
    assert opening.role == "system"
    assert "колего" in opening.text
    assert "Асинхронний Python" in opening.text
    assert "60" in opening.text
    assert "{FirstName}" not in opening.text


async def test_the_closing_is_the_repo_script(e2e: _Harness) -> None:
    view = await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()
    for candidate_text in TURNS:
        if view.phase in ("COMPLETED", "ABORTED"):
            break
        view = (await e2e.turn(_E2E_SESSION_ID, candidate_text)).session

    closing = view.transcript[-1]
    expected = _extract_script(
        (
            Path(__file__).resolve().parents[4] / "prompts/shared/candidate-facing/closing.md"
        ).read_text(encoding="utf-8")
    ).replace("{FirstName}", "колего")

    assert closing.role == "system"
    assert closing.text == expected


def test_extract_script_takes_only_the_ukrainian_blockquote() -> None:
    markdown = (
        "# Title\n\nprose\n\n## String (Ukrainian)\n\n"
        "> Рядок один.\n>\n> Рядок два.\n\n---\n\n## Variables\n\n| a | b |\n"
    )

    assert _extract_script(markdown) == "Рядок один.\n\nРядок два."


def test_extract_script_without_a_blockquote_fails_loudly() -> None:
    with pytest.raises(shell.DevSessionError):
        _extract_script("# Title\n\n## String (Ukrainian)\n\nno quote here\n")


# ---------------------------------------------------------------------------
# Errors and edges
# ---------------------------------------------------------------------------


async def test_an_invalid_plan_is_rejected_and_recorded_as_aborted(
    db_engine: AsyncEngine, clean_sessions: None
) -> None:
    harness = _harness(db_engine)
    before = await session_ids(db_engine)

    with pytest.raises(DevSessionPlanInvalid):
        await harness.service.create_session({"plan_version": 1, "competencies": []})

    # Edge 2 leaves an auditable ABORTED session behind, with its decision row.
    created = (await session_ids(db_engine)) - before
    assert len(created) == 1
    session_id = created.pop()
    async with db_engine.connect() as conn:
        state = (
            await conn.execute(
                text("SELECT session_state FROM interview_session WHERE id = :s"),
                {"s": session_id},
            )
        ).scalar_one()
        reason = (
            await conn.execute(
                text("SELECT reason FROM session_decision WHERE interview_session_id = :s"),
                {"s": session_id},
            )
        ).scalar_one()
    assert state["phase"] == "aborted"
    assert state["abort_reason"] == "operator_abort"
    assert reason == "plan_invalid"


async def test_a_turn_on_an_unknown_session_raises_not_found(db_engine: AsyncEngine) -> None:
    harness = _harness(db_engine)

    with pytest.raises(DevSessionNotFound):
        await harness.service.post_turn(uuid.uuid4(), "привіт")


async def test_a_turn_on_a_terminal_session_is_rejected(
    db_engine: AsyncEngine, clean_sessions: None
) -> None:
    harness = _harness(db_engine, ceiling_usd=Decimal("0.01"), enforcement=_enforced)
    view = await harness.service.create_session(PLAN)
    session_id = view.session_id
    await _charge(db_engine, session_id, "1.000000")
    await harness.turn(session_id, TURNS[0])

    with pytest.raises(DevSessionNotAwaitingCandidate, match="terminal"):
        await harness.service.post_turn(session_id, "ще одна відповідь")


async def test_candidate_turn_ids_are_derived_not_random(ephemeral: _Harness) -> None:
    """§6.9's recipe applied to the ids the SHELL owns."""
    view = await ephemeral.service.create_session(PLAN)

    result = await ephemeral.turn(view.session_id, TURNS[0])

    candidate_entry = next(e for e in result.session.transcript if e.role == "candidate")
    assert candidate_entry.turn_id == uuid.uuid5(view.session_id, "candidate-turn/0")


async def test_the_transcript_survives_a_reload(ephemeral: _Harness) -> None:
    view = await ephemeral.service.create_session(PLAN)
    posted = await ephemeral.turn(view.session_id, TURNS[0])

    reloaded = await ephemeral.service.get_session(view.session_id)

    assert reloaded.transcript == posted.session.transcript
    assert [entry.role for entry in reloaded.transcript] == [
        "system",
        "candidate",
        "interviewer",
    ]


async def test_traces_for_an_unknown_session_raise_not_found(db_engine: AsyncEngine) -> None:
    harness = _harness(db_engine)

    with pytest.raises(DevSessionNotFound):
        await harness.service.list_traces(uuid.uuid4())


async def test_traces_are_returned_oldest_first(e2e: _Harness) -> None:
    view = await e2e.service.create_session(PLAN, session_id=_E2E_SESSION_ID)
    await e2e.scheduler.drain()
    for candidate_text in TURNS[:3]:
        if view.phase in ("COMPLETED", "ABORTED"):
            break
        view = (await e2e.turn(_E2E_SESSION_ID, candidate_text)).session

    traces = await e2e.service.list_traces(_E2E_SESSION_ID)

    assert len(traces.traces) >= 3
    timestamps = [row.created_at for row in traces.traces]
    assert timestamps == sorted(timestamps)
