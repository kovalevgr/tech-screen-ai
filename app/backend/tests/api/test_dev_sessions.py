"""HTTP surface of the dev-session API (T22) — gating and contract shapes.

DB-gated and driven in-process through httpx's ASGI transport. Unlike the
Position Template suite these tests cannot wrap themselves in one rolled-back
transaction: the shell owns its own connections precisely so an audit row
survives a rolled-back request (§1). Each test therefore purges the sessions it
created, as ``techscreen_migrator`` (the §3-exempt role).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import BackgroundTasks
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backend.api import dev_sessions
from app.backend.api.deps import Principal, get_optional_current_user
from app.backend.main import app
from app.backend.orchestrator.config import load_orchestrator_config
from app.backend.services.dev_session import DevSessionService
from app.backend.services.feature_flags import FeatureFlagService, set_service
from app.backend.tests.services.test_dev_session import PLAN, TURNS, _settings

pytestmark = pytest.mark.asyncio

_BASE = "/api/dev/sessions"
_FEATURE_FLAGS_YAML = Path(__file__).resolve().parents[4] / "configs" / "feature-flags.yaml"


def _reviewer() -> Principal:
    return Principal(user_id=None, role="reviewer", sub="sso|reviewer")


def _candidate() -> Principal:
    return Principal(user_id=uuid.uuid4(), role="candidate", sub="sso|candidate")


def _anonymous() -> Principal | None:
    """What ``get_optional_current_user`` returns under ``AUTH_MODE=disabled``."""
    return None


def _service_factory(engine: AsyncEngine) -> Any:
    """Rebind the router's service to the per-test engine.

    The production factory reaches for the process-wide ``get_engine()``, whose
    pooled asyncpg connections are pinned to whichever event loop created them
    — fine for a server, wrong for a per-test loop. Everything else about the
    wiring, including the real BackgroundTasks scheduler, is untouched.
    """

    def _build(background: BackgroundTasks) -> DevSessionService:
        return DevSessionService(
            engine=engine,
            settings=_settings(),
            config=load_orchestrator_config(),
            scheduler=dev_sessions._BackgroundTasksScheduler(background),
        )

    return _build


@pytest.fixture
async def client(db_engine: AsyncEngine, clean_sessions: None) -> AsyncIterator[AsyncClient]:
    """Flag ON, auth OFF — the default local dev posture."""
    app.dependency_overrides[dev_sessions.require_live_orchestrator] = lambda: None
    app.dependency_overrides[get_optional_current_user] = _anonymous
    app.dependency_overrides[dev_sessions.get_dev_session_service] = _service_factory(db_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        try:
            yield http
        finally:
            app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# §9 gate — the flag really is read from the database
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", _BASE),
        ("get", f"{_BASE}/{uuid.uuid4()}"),
        ("get", f"{_BASE}/{uuid.uuid4()}/traces"),
        ("post", f"{_BASE}/{uuid.uuid4()}/turns"),
    ],
)
async def test_every_route_is_404_while_the_flag_is_off(
    migrated_schema: str, method: str, path: str
) -> None:
    """No override: the real FeatureFlagService reads the seeded ``false`` row."""
    service = FeatureFlagService.from_yaml(_FEATURE_FLAGS_YAML, migrated_schema)
    set_service(service)
    app.dependency_overrides[get_optional_current_user] = _anonymous
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.request(method, path, json={"plan": PLAN, "text": "x"})
        assert response.status_code == 404
    finally:
        set_service(None)
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Role gate
# ---------------------------------------------------------------------------


async def test_a_reviewer_may_create_a_session(
    db_engine: AsyncEngine, clean_sessions: None
) -> None:
    app.dependency_overrides[dev_sessions.require_live_orchestrator] = lambda: None
    app.dependency_overrides[get_optional_current_user] = _reviewer
    app.dependency_overrides[dev_sessions.get_dev_session_service] = _service_factory(db_engine)
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(_BASE, json={"plan": PLAN})
        assert response.status_code == 201
    finally:
        app.dependency_overrides.clear()


async def test_a_candidate_role_is_forbidden() -> None:
    """Under identity_platform the dev surface is reviewer/admin only."""
    app.dependency_overrides[dev_sessions.require_live_orchestrator] = lambda: None
    app.dependency_overrides[get_optional_current_user] = _candidate
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            response = await http.post(_BASE, json={"plan": PLAN})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Contract shapes
# ---------------------------------------------------------------------------


async def test_create_returns_the_session_view(client: AsyncClient) -> None:
    response = await client.post(_BASE, json={"plan": PLAN})

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "session_id",
        "phase",
        "abort_reason",
        "awaiting",
        "competency_index",
        "coverage",
        "flagged_for_review",
        "cost_usd_total",
        "transcript",
    }
    assert body["phase"] == "INTRO"
    assert body["cost_usd_total"] == "0"
    assert body["transcript"][0]["role"] == "system"


async def test_create_rejects_an_invalid_plan_with_422(client: AsyncClient) -> None:
    response = await client.post(_BASE, json={"plan": {"plan_version": 1, "competencies": []}})

    assert response.status_code == 422


async def test_create_rejects_unknown_body_keys(client: AsyncClient) -> None:
    response = await client.post(_BASE, json={"plan": PLAN, "candidate": "someone"})

    assert response.status_code == 422


async def test_posting_a_turn_returns_the_utterance_and_the_view(client: AsyncClient) -> None:
    created = (await client.post(_BASE, json={"plan": PLAN})).json()

    response = await client.post(f"{_BASE}/{created['session_id']}/turns", json={"text": TURNS[0]})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"utterance", "session"}
    assert body["utterance"]
    assert body["session"]["phase"] == "TECH"
    assert [entry["role"] for entry in body["session"]["transcript"]] == [
        "system",
        "candidate",
        "interviewer",
    ]


async def test_posting_an_empty_turn_is_rejected(client: AsyncClient) -> None:
    created = (await client.post(_BASE, json={"plan": PLAN})).json()

    response = await client.post(f"{_BASE}/{created['session_id']}/turns", json={"text": ""})

    assert response.status_code == 422


async def test_get_returns_the_same_view(client: AsyncClient) -> None:
    created = (await client.post(_BASE, json={"plan": PLAN})).json()

    response = await client.get(f"{_BASE}/{created['session_id']}")

    assert response.status_code == 200
    assert response.json() == created


async def test_get_on_an_unknown_session_is_404(client: AsyncClient) -> None:
    response = await client.get(f"{_BASE}/{uuid.uuid4()}")

    assert response.status_code == 404


async def test_traces_start_empty_and_grow_with_the_turns(client: AsyncClient) -> None:
    created = (await client.post(_BASE, json={"plan": PLAN})).json()
    session_id = created["session_id"]

    empty = await client.get(f"{_BASE}/{session_id}/traces")
    assert empty.status_code == 200
    assert empty.json() == {"traces": []}

    await client.post(f"{_BASE}/{session_id}/turns", json={"text": TURNS[0]})
    after = await client.get(f"{_BASE}/{session_id}/traces")

    rows = after.json()["traces"]
    assert len(rows) == 1
    assert rows[0]["agent"] == "interviewer"
    assert rows[0]["prompt_version"] == "v0001"
    assert rows[0]["transition"]["issued_move"] == "ask_seed"


async def test_traces_on_an_unknown_session_is_404(client: AsyncClient) -> None:
    response = await client.get(f"{_BASE}/{uuid.uuid4()}/traces")

    assert response.status_code == 404


async def test_a_turn_on_an_unknown_session_is_404(client: AsyncClient) -> None:
    response = await client.post(f"{_BASE}/{uuid.uuid4()}/turns", json={"text": "привіт"})

    assert response.status_code == 404
