"""``PostgresTraceSink`` — the durable half of constitution §1 (T21).

DB-gated: skips unless ``DATABASE_URL`` points at a reachable Postgres, like
every other suite that needs the real schema (the §3 trigger and the CHECK
constraints exist only in the migration).

Rows written here are deliberately NOT rolled back — the sink commits on its
own connection precisely so an audit row survives a rolled-back request, and
proving that is half the point of the suite. Every test uses its own session
id, and the test database is a throwaway.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.backend.llm import ModelCallRequest, call_model
from app.backend.llm._mock_backend import canonical_prompt_sha
from app.backend.llm.cost_ledger import InMemoryCostLedger
from app.backend.llm.errors import TraceWriteError, VertexUpstreamUnavailableError
from app.backend.llm.models_config import MODELS_YAML_PATH, ModelsConfig
from app.backend.llm.persistent_trace import (
    PostgresTraceSink,
    TransitionContext,
    TurnTraceContext,
    session_cost_total,
)
from app.backend.llm.trace import TraceRecord
from app.backend.settings import Settings

pytestmark = pytest.mark.asyncio

_SHA = "a" * 64


async def _new_session(engine: AsyncEngine) -> uuid.UUID:
    async with engine.begin() as conn:
        result = await conn.execute(
            text("INSERT INTO interview_session DEFAULT VALUES RETURNING id")
        )
        created: uuid.UUID = result.scalar_one()
    return created


async def _fetch_row(engine: AsyncEngine, trace_id: uuid.UUID) -> dict[str, Any]:
    async with engine.connect() as conn:
        row = (
            await conn.execute(text("SELECT * FROM turn_trace WHERE id = :id"), {"id": trace_id})
        ).mappings()
        return dict(row.one())


def _record(
    session_id: uuid.UUID,
    *,
    outcome: str = "ok",
    cost: str = "0.001200",
    agent: str = "interviewer",
) -> TraceRecord:
    return TraceRecord(
        id=uuid.uuid4(),
        created_at=datetime.now(UTC),
        agent=agent,
        session_id=session_id,
        model="gemini-2.5-flash",
        model_version="gemini-2.5-flash-001",
        prompt_sha256=_SHA,
        outcome=outcome,  # type: ignore[arg-type]  # test drives the literal set
        attempts=1,
        latency_ms=123,
        input_tokens=10,
        output_tokens=20,
        cost_usd=Decimal(cost),
        error_message=None if outcome == "ok" else "boom",
    )


# ---------------------------------------------------------------------------
# Row shape
# ---------------------------------------------------------------------------


async def test_a_bound_context_fills_every_orchestrator_column(db_engine: AsyncEngine) -> None:
    session_id = await _new_session(db_engine)
    sink = PostgresTraceSink(db_engine)
    turn_id = uuid.uuid4()
    context = TurnTraceContext(
        prompt_version="v0001",
        turn_id=turn_id,
        system_prompt="SYSTEM PROMPT",
        user_payload='{"answer": "Асинхронність"}',
        transition=TransitionContext(
            phase="tech",
            issued_move="depth_probe",
            state_before_sha="b" * 64,
            state_after_sha="c" * 64,
        ),
    )
    record = _record(session_id)

    with sink.bind(context):
        await sink.write(record)

    row = await _fetch_row(db_engine, record.id)
    assert row["interview_session_id"] == session_id
    assert row["turn_id"] == turn_id
    assert row["prompt_version"] == "v0001"
    assert row["agent"] == "interviewer"
    assert row["outcome"] == "ok"
    assert row["cost_usd"] == Decimal("0.001200")
    assert row["prompt_sha"] == _SHA
    assert row["system_prompt"] == "SYSTEM PROMPT"
    assert row["user_payload"] == '{"answer": "Асинхронність"}'
    assert row["transition"]["issued_move"] == "depth_probe"
    assert row["transition"]["state_before_sha"] == "b" * 64
    assert sink.written_trace_ids == (record.id,)


async def test_an_unbound_sink_writes_a_non_session_row(db_engine: AsyncEngine) -> None:
    """Calibration runs and smoke scripts have no orchestrator context."""
    session_id = await _new_session(db_engine)
    sink = PostgresTraceSink(db_engine)
    record = _record(session_id)

    await sink.write(record)

    row = await _fetch_row(db_engine, record.id)
    assert row["turn_id"] is None
    assert row["transition"] is None
    assert row["wrapper_outcome"] is None
    assert row["prompt_version"] == ""


async def test_bind_restores_the_previous_context(db_engine: AsyncEngine) -> None:
    sink = PostgresTraceSink(db_engine, context=TurnTraceContext(prompt_version="outer"))

    with sink.bind(TurnTraceContext(prompt_version="inner")):
        assert sink.context.prompt_version == "inner"

    assert sink.context.prompt_version == "outer"


async def test_a_caller_supplied_response_completes_the_row(db_engine: AsyncEngine) -> None:
    """The payload columns are filled from the context when the caller has them."""
    session_id = await _new_session(db_engine)
    sink = PostgresTraceSink(db_engine)
    record = _record(session_id, agent="assessor")
    context = TurnTraceContext(
        prompt_version="v0003",
        response_text='{"level": 3}',
        parsed={"level": 3},
        wrapper_outcome="accepted",
    )

    with sink.bind(context):
        await sink.write(record)

    row = await _fetch_row(db_engine, record.id)
    assert row["response_text"] == '{"level": 3}'
    assert row["parsed"] == {"level": 3}
    assert row["wrapper_outcome"] == "accepted"


# ---------------------------------------------------------------------------
# Failure semantics (T04: a lost trace is a failed call)
# ---------------------------------------------------------------------------


async def test_a_failed_insert_raises_trace_write_error(db_engine: AsyncEngine) -> None:
    """An unknown session violates the FK; §1 says the call must fail."""
    sink = PostgresTraceSink(db_engine)
    record = _record(uuid.uuid4())

    with pytest.raises(TraceWriteError) as err:
        await sink.write(record)

    assert str(record.id) in str(err.value)
    assert sink.written_trace_ids == ()


async def test_an_unreachable_database_raises_trace_write_error() -> None:
    dead = create_async_engine("postgresql+asyncpg://nobody@127.0.0.1:1/none")
    try:
        with pytest.raises(TraceWriteError):
            await PostgresTraceSink(dead).write(_record(uuid.uuid4()))
    finally:
        await dead.dispose()


async def test_a_written_row_cannot_be_updated_afterwards(db_engine: AsyncEngine) -> None:
    """§3 on a row this sink produced, not just on a seeded one."""
    session_id = await _new_session(db_engine)
    sink = PostgresTraceSink(db_engine)
    record = _record(session_id)
    await sink.write(record)

    async with db_engine.connect() as conn:
        trans = await conn.begin()
        with pytest.raises(DBAPIError) as err:
            await conn.execute(
                text("UPDATE turn_trace SET user_payload = 'tampered' WHERE id = :id"),
                {"id": record.id},
            )
        await trans.rollback()

    assert "append-only:" in str(err.value)


# ---------------------------------------------------------------------------
# Through the real wrapper (T04 semantics unchanged)
# ---------------------------------------------------------------------------


def _fixture_settings(tmp_path: Path) -> Settings:
    return Settings(
        llm_backend="mock",
        app_env="test",
        llm_budget_per_session_usd=Decimal("5.00"),
        llm_fixtures_dir=tmp_path,
    )


def _record_fixture(tmp_path: Path, request: ModelCallRequest, payload: dict[str, Any]) -> None:
    """Write the mock-backend envelope for ``request``'s canonical prompt SHA."""
    model = ModelsConfig.from_yaml(MODELS_YAML_PATH).for_agent(request.agent).model
    sha = canonical_prompt_sha(
        system_prompt=request.system_prompt,
        user_payload=request.user_payload,
        json_schema=request.json_schema,
        agent=request.agent,
        model=model,
    )
    agent_dir = tmp_path / request.agent
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / f"{sha}.json").write_text(
        json.dumps(
            {
                "text": json.dumps(payload, ensure_ascii=False),
                "input_tokens": 100,
                "output_tokens": 50,
                "model": model,
                "model_version": f"{model}-001",
            }
        ),
        encoding="utf-8",
    )


async def test_call_model_writes_the_row_before_it_returns(
    db_engine: AsyncEngine, tmp_path: Path
) -> None:
    session_id = await _new_session(db_engine)
    request = ModelCallRequest(
        agent="interviewer",
        system_prompt="be an interviewer",
        user_payload='{"move": "ask_seed"}',
        json_schema={"type": "object", "required": ["utterance"]},
        session_id=session_id,
    )
    _record_fixture(tmp_path, request, {"utterance": "Привіт"})
    sink = PostgresTraceSink(db_engine)

    with sink.bind(TurnTraceContext(prompt_version="v0001", turn_id=uuid.uuid4())):
        result = await call_model(
            request,
            sink=sink,
            ledger=InMemoryCostLedger(),
            settings=_fixture_settings(tmp_path),
        )

    row = await _fetch_row(db_engine, result.trace_id)
    assert row["outcome"] == "ok"
    assert len(row["prompt_sha"]) == 64
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50
    assert row["cost_usd"] > 0


async def test_a_failed_call_is_traced_too(db_engine: AsyncEngine, tmp_path: Path) -> None:
    """FR-008: every invocation leaves exactly one row, success or not."""
    session_id = await _new_session(db_engine)
    request = ModelCallRequest(
        agent="assessor",
        system_prompt="score the turn",
        user_payload='{"turn": "no fixture for this"}',
        json_schema=None,
        session_id=session_id,
    )
    sink = PostgresTraceSink(db_engine)

    with pytest.raises(VertexUpstreamUnavailableError):
        await call_model(
            request,
            sink=sink,
            ledger=InMemoryCostLedger(),
            settings=_fixture_settings(tmp_path),
        )

    assert len(sink.written_trace_ids) == 1
    row = await _fetch_row(db_engine, sink.written_trace_ids[0])
    assert row["outcome"] == "upstream_unavailable"
    assert row["error_message"] is not None
    assert row["cost_usd"] == Decimal("0")


# ---------------------------------------------------------------------------
# The ledger's source of truth
# ---------------------------------------------------------------------------


async def test_session_cost_total_sums_the_session_rows(db_engine: AsyncEngine) -> None:
    session_id = await _new_session(db_engine)
    other_id = await _new_session(db_engine)
    sink = PostgresTraceSink(db_engine)
    await sink.write(_record(session_id, cost="1.250000"))
    await sink.write(_record(session_id, cost="0.750000"))
    await sink.write(_record(other_id, cost="9.000000"))

    assert await session_cost_total(db_engine, session_id) == Decimal("2.000000")


async def test_session_cost_total_is_zero_for_an_untouched_session(
    db_engine: AsyncEngine,
) -> None:
    assert await session_cost_total(db_engine, uuid.uuid4()) == Decimal("0")
