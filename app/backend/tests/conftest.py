"""Pytest fixtures shared by every backend test.

Fixtures are declared with lazy imports so this file loads cleanly even
before ``app/backend/main.py`` exists — convention every later backend
task builds on.
"""

from __future__ import annotations

from collections.abc import Generator
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import structlog
from structlog.typing import EventDict, WrappedLogger

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

    from app.backend.llm._mock_backend import MockVertexBackend
    from app.backend.llm.cost_ledger import InMemoryCostLedger
    from app.backend.llm.models_config import ModelsConfig
    from app.backend.llm.pricing import PricingTable
    from app.backend.llm.trace import InMemoryTraceSink
    from app.backend.settings import Settings


_FIXTURES_DIR: Path = Path(__file__).resolve().parent / "fixtures" / "llm_responses"


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
