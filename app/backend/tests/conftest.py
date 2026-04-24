"""Pytest fixtures shared by every backend test.

Fixtures are declared with lazy imports so this file loads cleanly even
before ``app/backend/main.py`` exists — convention every later backend
task builds on.
"""

from __future__ import annotations

from collections.abc import Generator
from typing import TYPE_CHECKING, Any

import pytest
import structlog
from structlog.typing import EventDict, WrappedLogger

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


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
