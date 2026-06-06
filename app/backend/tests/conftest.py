"""Pytest fixtures shared by every backend test.

Fixtures are declared with lazy imports so this file loads cleanly even
before ``app/backend/main.py`` exists — convention every later backend
task builds on.
"""

from __future__ import annotations

import subprocess
from collections.abc import AsyncGenerator, AsyncIterator, Generator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import structlog
from sqlalchemy import text
from structlog.typing import EventDict, WrappedLogger

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

    from app.backend.llm._mock_backend import MockVertexBackend
    from app.backend.llm.cost_ledger import InMemoryCostLedger
    from app.backend.llm.models_config import ModelsConfig
    from app.backend.llm.pricing import PricingTable
    from app.backend.llm.trace import InMemoryTraceSink
    from app.backend.settings import Settings


_FIXTURES_DIR: Path = Path(__file__).resolve().parent / "fixtures" / "llm_responses"
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Request-level test client wrapping the real FastAPI app."""
    from fastapi.testclient import TestClient

    from app.backend.main import app

    return TestClient(app)


@pytest.fixture
def captured_logs() -> Generator[list[EventDict], None, None]:
    """Install ``configure_logging`` and capture each emitted record.

    Runs the real production pipeline (including the PII redactor, once
    US3 lands) but replaces the terminal renderer with a list-appending
    sink. The captured list holds the post-redaction ``EventDict`` so
    tests can assert on the structured shape **and** the stringified
    content in a single place.
    """
    from app.backend.logging import configure_logging

    configure_logging()
    original_config = structlog.get_config()
    original_processors: list[Any] = list(original_config["processors"])
    captured: list[EventDict] = []

    def _sink(logger: WrappedLogger, method_name: str, event_dict: EventDict) -> str:
        del logger, method_name
        captured.append(dict(event_dict))
        return ""

    structlog.configure(
        processors=[*original_processors[:-1], _sink],
        wrapper_class=original_config["wrapper_class"],
        context_class=original_config["context_class"],
        logger_factory=original_config["logger_factory"],
        cache_logger_on_first_use=False,
    )

    try:
        yield captured
    finally:
        structlog.configure(
            processors=original_processors,
            wrapper_class=original_config["wrapper_class"],
            context_class=original_config["context_class"],
            logger_factory=original_config["logger_factory"],
            cache_logger_on_first_use=original_config["cache_logger_on_first_use"],
        )


# ---------------------------------------------------------------------------
# T04 — Vertex wrapper test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_trace_sink() -> InMemoryTraceSink:
    """Fresh in-memory trace sink per test (defensive default capacity)."""
    from app.backend.llm.trace import InMemoryTraceSink

    return InMemoryTraceSink()


@pytest.fixture
def in_memory_cost_ledger() -> InMemoryCostLedger:
    """Fresh in-memory per-session cost ledger per test."""
    from app.backend.llm.cost_ledger import InMemoryCostLedger

    return InMemoryCostLedger()


@pytest.fixture
def sample_pricing() -> PricingTable:
    """Pricing table loaded from the committed ``app/backend/llm/pricing.yaml``."""
    from app.backend.llm.pricing import PRICING_YAML_PATH, PricingTable

    return PricingTable.from_yaml(PRICING_YAML_PATH)


@pytest.fixture
def sample_models_config() -> ModelsConfig:
    """Models config loaded from the committed ``configs/models.yaml``."""
    from app.backend.llm.models_config import MODELS_YAML_PATH, ModelsConfig

    return ModelsConfig.from_yaml(MODELS_YAML_PATH)


@pytest.fixture
def test_settings() -> Settings:
    """``Settings`` instance pinned to mock backend + the test fixtures dir.

    Independent of the developer's ``.env`` (we set the fields explicitly
    rather than reading the env so a stray ``LLM_BACKEND=vertex`` in the
    shell environment doesn't make tests reach for real credentials).
    """
    from app.backend.settings import Settings

    return Settings(
        llm_backend="mock",
        app_env="dev",
        llm_budget_per_session_usd=Decimal("5.00"),
        llm_fixtures_dir=_FIXTURES_DIR,
    )


@pytest.fixture
def mock_backend() -> MockVertexBackend:
    """Default :class:`MockVertexBackend` pointed at the committed fixtures.

    Defaults to the ``assessor`` agent because the schema-INVALID fixture
    used by the schema-miss tests lives there; tests that need a different
    agent construct their own ``MockVertexBackend`` from the same
    ``_FIXTURES_DIR``.
    """
    from app.backend.llm._mock_backend import MockVertexBackend

    return MockVertexBackend(agent="assessor", fixtures_dir=_FIXTURES_DIR)


# ---------------------------------------------------------------------------
# T05 — Database integration test fixtures
# ---------------------------------------------------------------------------
#
# These fixtures gate the `tests/db/` suite: when no database is reachable they
# `pytest.skip` so the existing no-DB unit run stays green (research §9). When a
# DB is present, the schema is materialised by the REAL `alembic upgrade head`
# (never `Base.metadata.create_all`) because the §3 guarantee — triggers, roles,
# grants — lives only in the migration, not in the model metadata.


def _resolve_database_url() -> str | None:
    """Return the configured async DSN, or ``None`` when unset/blank.

    An empty or whitespace-only ``DATABASE_URL`` (e.g. ``DATABASE_URL=`` in the
    environment) is treated as unset so the DB suite skips rather than trying to
    parse an invalid URL.
    """
    from app.backend.settings import Settings

    url = Settings().database_url
    if url is None or not url.strip():
        return None
    return url


async def _can_connect(database_url: str) -> bool:
    """Best-effort connectivity probe; ``False`` on any failure.

    Catches both URL-parse errors (engine creation) and connection failures, so
    a malformed or unreachable DSN cleanly skips the suite instead of erroring.
    """
    from sqlalchemy.ext.asyncio import create_async_engine

    try:
        engine = create_async_engine(database_url)
    except Exception:  # noqa: BLE001 — bad URL → "not reachable" → skip
        return False
    try:
        async with engine.connect():
            return True
    except Exception:  # noqa: BLE001 — any failure means "DB not reachable" → skip
        return False
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
async def db_available() -> str:
    """Skip the DB suite unless a reachable ``DATABASE_URL`` is configured.

    Returns the DSN string when present and connectable; otherwise calls
    :func:`pytest.skip` so the no-DB unit run is unaffected.
    """
    database_url = _resolve_database_url()
    if database_url is None:
        pytest.skip("DATABASE_URL is not set; skipping DB integration tests")
    if not await _can_connect(database_url):
        pytest.skip(f"database at {database_url!r} is not reachable; skipping DB tests")
    return database_url


@pytest.fixture(scope="session")
def migrated_schema(db_available: str) -> str:
    """Run the real ``alembic upgrade head`` once for the DB test session.

    Uses the committed ``alembic.ini`` + async ``env.py`` so the materialised
    schema includes the triggers, roles, and grants that ``create_all`` would
    never produce. Idempotent — re-running against an already-migrated DB is a
    no-op (the migration guards roles/extensions).
    """
    result = subprocess.run(  # noqa: S603 — fixed argv, no shell, trusted input
        ["alembic", "upgrade", "head"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            "alembic upgrade head failed in the migrated_schema fixture:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return db_available


@pytest.fixture
async def db_engine(migrated_schema: str) -> AsyncGenerator[AsyncEngine, None]:
    """A per-test async engine bound to the migrated test database."""
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(migrated_schema)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_conn(db_engine: AsyncEngine) -> AsyncGenerator[AsyncConnection, None]:
    """A per-test async connection on the migrated schema.

    Each test gets a fresh connection so ``SET ROLE`` / ``RESET ROLE`` state
    never leaks between tests.
    """
    async with db_engine.connect() as conn:
        yield conn


@asynccontextmanager
async def set_role(conn: AsyncConnection, role: str) -> AsyncIterator[None]:
    """Run a block as ``role`` via ``SET ROLE`` / ``RESET ROLE``.

    ``SET ROLE`` from the superuser to a ``NOLOGIN`` role makes privilege checks
    apply *as that role* (``is_superuser`` becomes false), so the §3 ``REVOKE``
    is genuinely enforced under test without provisioning a LOGIN password
    (research §3). ``RESET ROLE`` always runs on exit, even on error.
    """
    await conn.execute(text(f'SET ROLE "{role}"'))
    try:
        yield
    finally:
        await conn.execute(text("RESET ROLE"))
