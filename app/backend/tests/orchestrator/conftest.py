"""Fixtures for the orchestrator suite.

The committed ``configs/orchestrator.yaml`` is loaded as-is: the tests assert
against the thresholds the product actually ships (contract §8), not against
a bespoke test config. Where a test needs a different threshold it evolves a
copy explicitly, so the deviation is visible in the test body.
"""

from __future__ import annotations

import pytest

from app.backend.orchestrator.config import OrchestratorConfig, load_orchestrator_config


@pytest.fixture(scope="session")
def config() -> OrchestratorConfig:
    """The committed orchestrator thresholds (``configs/orchestrator.yaml``)."""
    return load_orchestrator_config()
