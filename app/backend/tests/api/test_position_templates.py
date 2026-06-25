"""Integration tests for the Position Template CRUD API (T13).

Run against the `docker-compose.test.yml` db profile. Each test runs inside one
outer transaction rolled back at teardown (savepoint-joined sessions), so
nothing persists. The app is driven in-process via httpx ASGITransport (same
event loop as the DB connection). The auth seam and the §9 flag gate are
overridden per scenario.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from fastapi import HTTPException, status
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from app.backend.api import deps
from app.backend.main import app

pytestmark = pytest.mark.asyncio


def _recruiter() -> deps.Principal:
    # user_id=None → created_by is NULL (no `user` row is seeded; the FK only
    # bites on a non-null value). Ownership wiring is exercised when T07 lands.
    return deps.Principal(user_id=None, role="recruiter")


def _candidate() -> deps.Principal:
    return deps.Principal(user_id=uuid.uuid4(), role="candidate")


def _flag_off() -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)


@dataclass
class _Ctx:
    client: AsyncClient
    conn: AsyncConnection


@pytest.fixture
async def ctx(db_engine: AsyncEngine) -> AsyncIterator[_Ctx]:
    """A client + connection sharing one rolled-back outer transaction."""
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
    app.dependency_overrides[deps.require_crud_enabled] = lambda: None
    app.dependency_overrides[deps.get_current_user] = _recruiter

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        yield _Ctx(client=client, conn=conn)
    finally:
        await client.aclose()
        app.dependency_overrides.clear()
        await outer.rollback()
        await conn.close()


async def _seed_stack_with_competency(
    conn: AsyncConnection, stack_name: str = "Backend Python", comp_name: str = "Concurrency"
) -> tuple[uuid.UUID, uuid.UUID]:
    rtv = (
        await conn.execute(
            text(
                "INSERT INTO rubric_tree_version (label, payload_hash) VALUES (:l, :h) RETURNING id"
            ),
            {"l": f"t13-{uuid.uuid4()}", "h": uuid.uuid4().hex + uuid.uuid4().hex},
        )
    ).scalar_one()
    stack = (
        await conn.execute(
            text("INSERT INTO stack (rubric_tree_version_id, name) VALUES (:v, :n) RETURNING id"),
            {"v": rtv, "n": stack_name},
        )
    ).scalar_one()
    block = (
        await conn.execute(
            text(
                "INSERT INTO competency_block (rubric_tree_version_id, stack_id, name) "
                "VALUES (:v, :s, :n) RETURNING id"
            ),
            {"v": rtv, "s": stack, "n": "Core"},
        )
    ).scalar_one()
    comp = (
        await conn.execute(
            text(
                "INSERT INTO competency (rubric_tree_version_id, competency_block_id, name) "
                "VALUES (:v, :b, :n) RETURNING id"
            ),
            {"v": rtv, "b": block, "n": comp_name},
        )
    ).scalar_one()
    return stack, comp


def _body(
    stack_id: uuid.UUID, comp_id: uuid.UUID, *, title: str = "Senior Backend", level: str = "Senior"
) -> dict[str, object]:
    return {
        "title": title,
        "level": level,
        "jd_text": None,
        "stack_ids": [str(stack_id)],
        "competency_ids": [str(comp_id)],
        "must_have_competency_ids": [str(comp_id)],
    }


# --- US1: create + read --------------------------------------------------------


async def test_create_and_read_round_trip(ctx: _Ctx) -> None:
    stack, comp = await _seed_stack_with_competency(ctx.conn)
    resp = await ctx.client.post("/position-templates", json=_body(stack, comp))
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["title"] == "Senior Backend"
    assert created["level"] == "Senior"
    assert created["stack_ids"] == [str(stack)]
    assert created["competencies"] == [{"competency_id": str(comp), "must_have": True}]

    got = await ctx.client.get(f"/position-templates/{created['id']}")
    assert got.status_code == 200
    assert got.json()["id"] == created["id"]


async def test_create_invalid_level_422(ctx: _Ctx) -> None:
    stack, comp = await _seed_stack_with_competency(ctx.conn)
    body = _body(stack, comp, level="Architect")
    resp = await ctx.client.post("/position-templates", json=body)
    assert resp.status_code == 422


async def test_create_unknown_stack_422(ctx: _Ctx) -> None:
    _stack, comp = await _seed_stack_with_competency(ctx.conn)
    body = _body(uuid.uuid4(), comp)
    resp = await ctx.client.post("/position-templates", json=body)
    assert resp.status_code == 422
    assert "stack" in resp.text


async def test_create_competency_not_in_stack_422(ctx: _Ctx) -> None:
    stack_a, _comp_a = await _seed_stack_with_competency(ctx.conn, "Backend", "Async")
    _stack_b, comp_b = await _seed_stack_with_competency(ctx.conn, "Frontend", "Hooks")
    body = _body(stack_a, comp_b)
    resp = await ctx.client.post("/position-templates", json=body)
    assert resp.status_code == 422
    assert "selected stack" in resp.text


async def test_get_unknown_404(ctx: _Ctx) -> None:
    resp = await ctx.client.get(f"/position-templates/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- US2: list + edit + archive -----------------------------------------------


async def test_list_excludes_archived_by_default(ctx: _Ctx) -> None:
    stack, comp = await _seed_stack_with_competency(ctx.conn)
    a = (await ctx.client.post("/position-templates", json=_body(stack, comp))).json()
    (await ctx.client.post("/position-templates", json=_body(stack, comp, title="Second"))).json()
    await ctx.client.delete(f"/position-templates/{a['id']}")

    default = await ctx.client.get("/position-templates")
    assert default.status_code == 200
    titles = {t["title"] for t in default.json()}
    assert titles == {"Second"}

    full = await ctx.client.get("/position-templates", params={"include_archived": "true"})
    assert {t["title"] for t in full.json()} == {"Senior Backend", "Second"}


async def test_patch_updates_and_revalidates(ctx: _Ctx) -> None:
    stack, comp = await _seed_stack_with_competency(ctx.conn)
    created = (await ctx.client.post("/position-templates", json=_body(stack, comp))).json()

    ok = await ctx.client.patch(
        f"/position-templates/{created['id']}", json={"title": "Renamed", "level": "Middle"}
    )
    assert ok.status_code == 200
    assert ok.json()["title"] == "Renamed"
    assert ok.json()["level"] == "Middle"

    # must_have_competency_ids without competency_ids → 422, row unchanged.
    bad = await ctx.client.patch(
        f"/position-templates/{created['id']}",
        json={"must_have_competency_ids": [str(uuid.uuid4())]},
    )
    assert bad.status_code == 422
    still = await ctx.client.get(f"/position-templates/{created['id']}")
    assert still.json()["title"] == "Renamed"


async def test_delete_soft_archives(ctx: _Ctx) -> None:
    stack, comp = await _seed_stack_with_competency(ctx.conn)
    created = (await ctx.client.post("/position-templates", json=_body(stack, comp))).json()

    deleted = await ctx.client.delete(f"/position-templates/{created['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["archived_at"] is not None

    # Still retrievable directly (row preserved), absent from the default list.
    assert (await ctx.client.get(f"/position-templates/{created['id']}")).status_code == 200
    assert (await ctx.client.get("/position-templates")).json() == []


async def test_delete_unknown_404(ctx: _Ctx) -> None:
    resp = await ctx.client.delete(f"/position-templates/{uuid.uuid4()}")
    assert resp.status_code == 404


# --- US3: authorization + flag gate -------------------------------------------


async def test_forbidden_for_non_manager_role(ctx: _Ctx) -> None:
    app.dependency_overrides[deps.get_current_user] = _candidate
    resp = await ctx.client.get("/position-templates")
    assert resp.status_code == 403


async def test_unauthenticated_401(ctx: _Ctx) -> None:
    # Drop the override so the real seam (401) runs.
    app.dependency_overrides.pop(deps.get_current_user, None)
    resp = await ctx.client.get("/position-templates")
    assert resp.status_code == 401


async def test_flag_off_returns_404_before_auth(ctx: _Ctx) -> None:
    app.dependency_overrides[deps.require_crud_enabled] = _flag_off
    # Even unauthenticated, a disabled feature is 404 (not 401).
    app.dependency_overrides.pop(deps.get_current_user, None)
    resp = await ctx.client.get("/position-templates")
    assert resp.status_code == 404
