"""Integration tests for GET /rubric/active.

Same isolation pattern as test_position_templates.py: a savepoint-joined session
in one rolled-back outer transaction, driven in-process via httpx ASGITransport.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.backend.api import deps
from app.backend.main import app

pytestmark = pytest.mark.asyncio


def _recruiter() -> deps.Principal:
    return deps.Principal(user_id=None, role="recruiter")


def _candidate() -> deps.Principal:
    return deps.Principal(user_id=uuid.uuid4(), role="candidate")


@dataclass
class _Ctx:
    client: AsyncClient
    conn: AsyncConnection


@pytest.fixture
async def ctx(db_engine: AsyncEngine) -> AsyncIterator[_Ctx]:
    conn = await db_engine.connect()
    outer = await conn.begin()
    session_factory = async_sessionmaker(
        bind=conn,
        expire_on_commit=False,
        class_=AsyncSession,
        join_transaction_mode="create_savepoint",
    )

    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        session = session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    app.dependency_overrides[deps.get_db] = _override_get_db
    app.dependency_overrides[deps.get_current_user] = _recruiter

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        yield _Ctx(client=client, conn=conn)
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        await outer.rollback()
        await conn.close()


async def _seed_active_version(conn: AsyncConnection) -> uuid.UUID:
    rtv = (
        await conn.execute(
            text(
                "INSERT INTO rubric_tree_version (label, payload_hash, is_active) "
                "VALUES (:l, :h, true) RETURNING id"
            ),
            {"l": "active", "h": uuid.uuid4().hex + uuid.uuid4().hex},
        )
    ).scalar_one()
    stack = (
        await conn.execute(
            text("INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n) RETURNING id"),
            {"v": rtv, "n": "Backend Python"},
        )
    ).scalar_one()
    block = (
        await conn.execute(
            text(
                "INSERT INTO competency_block (rubric_tree_version_id, stack_id, name, position) "
                "VALUES (:v, :s, :n, :p) RETURNING id"
            ),
            {"v": rtv, "s": stack, "n": "Core", "p": 1},
        )
    ).scalar_one()
    await conn.execute(
        text(
            "INSERT INTO competency (rubric_tree_version_id, competency_block_id, name) "
            "VALUES (:v, :b, :n)"
        ),
        {"v": rtv, "b": block, "n": "Concurrency"},
    )
    return rtv  # type: ignore[no-any-return]


async def test_active_rubric_returns_full_tree(ctx: _Ctx) -> None:
    rtv = await _seed_active_version(ctx.conn)
    resp = await ctx.client.get("/rubric/active")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rubric_tree_version_id"] == str(rtv)
    assert body["stacks"][0]["name"] == "Backend Python"
    competency = body["stacks"][0]["competency_blocks"][0]["competencies"][0]
    assert competency["name"] == "Concurrency"


async def test_no_active_version_returns_404(ctx: _Ctx) -> None:
    resp = await ctx.client.get("/rubric/active")
    assert resp.status_code == 404


async def test_forbidden_for_non_manager_role(ctx: _Ctx) -> None:
    await _seed_active_version(ctx.conn)
    app.dependency_overrides[deps.get_current_user] = _candidate
    resp = await ctx.client.get("/rubric/active")
    assert resp.status_code == 403


async def test_unauthenticated_401(ctx: _Ctx) -> None:
    await _seed_active_version(ctx.conn)
    app.dependency_overrides.pop(deps.get_current_user, None)
    resp = await ctx.client.get("/rubric/active")
    assert resp.status_code == 401
