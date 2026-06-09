"""FeatureFlagService end-to-end (T05a).

Covers two batches of acceptance criteria:

**US1 (dark by default)**
- `test_unknown_flag_raises` — FR-004: a name not declared in YAML must
  raise `UnknownFeatureFlag`, never silently return False.
- `test_declared_flag_starts_disabled` — US1#1/#2: a freshly declared flag
  with default=False returns False even when no DB row exists yet (the
  workflow may not have run).
- `test_yaml_schema_violation_refuses_startup` — FR-005/FR-006: a malformed
  YAML must fail validation at service construction, so a backend can never
  boot with a non-conforming source-of-truth file.

**US2 (operator flip without deploy)**
- `test_update_propagates_under_one_second` — FR-003/SC-003: an UPDATE on a
  flag row must propagate to is_enabled within 1 second via LISTEN/NOTIFY.
- `test_delete_invalidates_cache` — AFTER DELETE trigger path.
- `test_listener_reconnects_after_drop` — research §3: a forced disconnect
  is recovered by exponential backoff.

All DB-touching tests skip cleanly when no DATABASE_URL is reachable.
"""

from __future__ import annotations

import asyncio
import textwrap
import uuid
from collections.abc import Callable
from pathlib import Path

import asyncpg
import jsonschema
import pytest

from app.backend.services.feature_flags import (
    FeatureFlagService,
    UnknownFeatureFlag,
)

pytestmark = pytest.mark.asyncio


def _write_yaml(path: Path, flag_name: str, *, default: bool = False) -> Path:
    """Write a minimal YAML with one active flag, valid against the schema."""
    path.write_text(
        textwrap.dedent(
            f"""\
            flags:
              - name: {flag_name}
                owner: "@test"
                default: {str(default).lower()}
                description: "test fixture flag"
                state: active
            """
        ),
        encoding="utf-8",
    )
    return path


def _bare_dsn(sqlalchemy_dsn: str) -> str:
    """asyncpg.connect() does not understand the +asyncpg dialect tag."""
    return sqlalchemy_dsn.replace("+asyncpg", "")


@pytest.fixture
async def cleanup_flag() -> str:
    """Yield a unique flag name and clean it up after the test."""
    return f"svc_test_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# US1 — unit-style tests (no listener needed; tolerant of empty DB)
# ---------------------------------------------------------------------------


async def test_unknown_flag_raises(tmp_path: Path, db_available: str) -> None:
    """FR-004: unknown name → UnknownFeatureFlag (never silently false)."""
    yaml_path = _write_yaml(tmp_path / "flags.yaml", "declared")
    svc = FeatureFlagService.from_yaml(yaml_path, db_available)
    with pytest.raises(UnknownFeatureFlag):
        await svc.is_enabled("undeclared_typo")


async def test_declared_flag_starts_disabled(
    tmp_path: Path, db_available: str, migrated_schema: str, cleanup_flag: str
) -> None:
    """A declared flag with no DB row falls back to YAML default=False."""
    yaml_path = _write_yaml(tmp_path / "flags.yaml", cleanup_flag, default=False)
    svc = FeatureFlagService.from_yaml(yaml_path, db_available)
    # No row created — service must fall back to the YAML default.
    assert await svc.is_enabled(cleanup_flag) is False


async def test_yaml_schema_violation_refuses_startup(tmp_path: Path) -> None:
    """FR-005/FR-006: malformed YAML must fail at service construction."""
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        textwrap.dedent(
            """\
            flags:
              - name: incomplete
                description: "missing required fields"
            """
        ),
        encoding="utf-8",
    )
    with pytest.raises(jsonschema.ValidationError):
        FeatureFlagService.from_yaml(bad_yaml, "postgresql+asyncpg://fake/fake")


# ---------------------------------------------------------------------------
# US2 — propagation tests (need a live DB + listener; use raw asyncpg for
# the test-side writes so NOTIFY actually fires on COMMIT).
# ---------------------------------------------------------------------------


async def _wait_until(
    predicate: Callable[[], object],
    *,
    timeout: float = 1.0,
    interval: float = 0.01,
) -> None:
    """Poll ``predicate`` (sync or async) until truthy or until ``timeout`` elapses."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        result: object = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return
        if loop.time() >= deadline:
            raise AssertionError("predicate never became truthy within the timeout")
        await asyncio.sleep(interval)


async def test_update_propagates_under_one_second(
    tmp_path: Path, db_available: str, migrated_schema: str, cleanup_flag: str
) -> None:
    """FR-003 / SC-003: a DB UPDATE propagates to is_enabled in < 1 s."""
    yaml_path = _write_yaml(tmp_path / "flags.yaml", cleanup_flag)
    svc = FeatureFlagService.from_yaml(yaml_path, db_available)
    await svc.start()
    raw = await asyncpg.connect(_bare_dsn(db_available))
    try:
        # Seed the row (autocommit per statement).
        await raw.execute(
            "INSERT INTO feature_flag (name, owner) VALUES ($1, $2)",
            cleanup_flag,
            "@svc-test",
        )
        # Give the listener a moment to receive the INSERT NOTIFY so the
        # subsequent read returns the freshly-written False value.
        await asyncio.sleep(0.05)
        assert await svc.is_enabled(cleanup_flag) is False
        # Flip it.
        await raw.execute(
            "UPDATE feature_flag SET enabled = TRUE WHERE name = $1",
            cleanup_flag,
        )
        await _wait_until(lambda: svc.is_enabled(cleanup_flag), timeout=1.0)
        assert await svc.is_enabled(cleanup_flag) is True
    finally:
        await raw.execute("DELETE FROM feature_flag WHERE name = $1", cleanup_flag)
        await raw.close()
        await svc.stop()


async def test_delete_invalidates_cache(
    tmp_path: Path, db_available: str, migrated_schema: str, cleanup_flag: str
) -> None:
    """AFTER DELETE trigger path: post-delete read falls back to YAML default."""
    yaml_path = _write_yaml(tmp_path / "flags.yaml", cleanup_flag, default=False)
    svc = FeatureFlagService.from_yaml(yaml_path, db_available)
    await svc.start()
    raw = await asyncpg.connect(_bare_dsn(db_available))
    try:
        await raw.execute(
            "INSERT INTO feature_flag (name, owner, enabled) VALUES ($1, $2, TRUE)",
            cleanup_flag,
            "@svc-test",
        )

        # Prime the cache with the post-insert value.
        async def reflects_true() -> bool:
            return await svc.is_enabled(cleanup_flag) is True

        await _wait_until(reflects_true, timeout=1.0)
        # Delete — NOTIFY must invalidate the cached True, next read returns
        # the YAML default (False) because no row exists anymore.
        await raw.execute("DELETE FROM feature_flag WHERE name = $1", cleanup_flag)

        async def reflects_false() -> bool:
            return await svc.is_enabled(cleanup_flag) is False

        await _wait_until(reflects_false, timeout=1.0)
    finally:
        await raw.execute("DELETE FROM feature_flag WHERE name = $1", cleanup_flag)
        await raw.close()
        await svc.stop()


async def test_listener_reconnects_after_drop(
    tmp_path: Path, db_available: str, migrated_schema: str, cleanup_flag: str
) -> None:
    """Research §3: a forced listener disconnect is recovered by backoff."""
    yaml_path = _write_yaml(tmp_path / "flags.yaml", cleanup_flag)
    svc = FeatureFlagService.from_yaml(yaml_path, db_available)
    await svc.start()
    raw = await asyncpg.connect(_bare_dsn(db_available))
    try:
        # Wait for the initial listener connection.
        await _wait_until(
            lambda: svc._listen_conn is not None and not svc._listen_conn.is_closed(),
            timeout=2.0,
        )
        # Force-close the listener connection.
        listen_conn = svc._listen_conn
        assert listen_conn is not None
        await listen_conn.close()
        # The reconnect loop should re-establish.
        await _wait_until(
            lambda: (
                svc._listen_conn is not None
                and not svc._listen_conn.is_closed()
                and svc._listen_conn is not listen_conn
            ),
            timeout=5.0,
        )
        # Sanity: invalidation still works after reconnect.
        await raw.execute(
            "INSERT INTO feature_flag (name, owner, enabled) VALUES ($1, $2, TRUE)",
            cleanup_flag,
            "@svc-test",
        )

        async def reflects_true() -> bool:
            return await svc.is_enabled(cleanup_flag) is True

        await _wait_until(reflects_true, timeout=1.5)
    finally:
        await raw.execute("DELETE FROM feature_flag WHERE name = $1", cleanup_flag)
        await raw.close()
        await svc.stop()
