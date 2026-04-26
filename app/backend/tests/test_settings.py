"""Tests for the backend Settings loader and the production-mode startup checks (T032).

Maps to FR-005, FR-007, SC-010 + constitution §12 (per-session budget ceiling).

The production-mode invariants enforced here:

- ``APP_ENV=prod`` with ``LLM_BACKEND=mock`` → ``RuntimeError``
  (FR-007 — production must never serve mocked LLM responses).
- ``APP_ENV=prod`` with ``LLM_BUDGET_PER_SESSION_USD > 5`` →
  ``RuntimeError`` (constitution §12).
- All non-production combinations are accepted, including
  ``LLM_BACKEND=mock`` (the dev/CI default).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.backend.settings import Settings


def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Strip any developer-shell env that would otherwise leak into Settings()."""
    for key in (
        "LLM_BACKEND",
        "APP_ENV",
        "LLM_BUDGET_PER_SESSION_USD",
        "LLM_FIXTURES_DIR",
    ):
        monkeypatch.delenv(key, raising=False)


def test_defaults_load_when_environment_is_clean(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No env, no .env → ship-defaults from ADR-022."""
    _clear_env(monkeypatch)
    monkeypatch.chdir(tmp_path)  # ensure no .env is picked up
    settings = Settings()
    assert settings.llm_backend == "mock"
    assert settings.app_env == "dev"
    assert settings.llm_budget_per_session_usd == Decimal("5.00")
    assert isinstance(settings.llm_fixtures_dir, Path)


def test_assert_safe_for_environment_passes_in_dev_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dev + mock is the developer default and must be accepted."""
    _clear_env(monkeypatch)
    settings = Settings(
        llm_backend="mock",
        app_env="dev",
        llm_budget_per_session_usd=Decimal("5.00"),
    )
    settings.assert_safe_for_environment()  # must not raise


def test_assert_safe_for_environment_passes_in_test_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test (CI) + mock is also accepted (FR-005)."""
    _clear_env(monkeypatch)
    settings = Settings(
        llm_backend="mock",
        app_env="test",
        llm_budget_per_session_usd=Decimal("5.00"),
    )
    settings.assert_safe_for_environment()  # must not raise


def test_production_with_mock_backend_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """FR-007: production never serves mocked LLM output."""
    _clear_env(monkeypatch)
    settings = Settings(
        llm_backend="mock",
        app_env="prod",
        llm_budget_per_session_usd=Decimal("5.00"),
    )
    with pytest.raises(RuntimeError) as excinfo:
        settings.assert_safe_for_environment()
    assert "FR-007" in str(excinfo.value)
    assert "mock" in str(excinfo.value).lower()


def test_production_with_budget_above_5usd_raises_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constitution §12: per-session ceiling is $5.00 in production."""
    _clear_env(monkeypatch)
    settings = Settings(
        llm_backend="vertex",
        app_env="prod",
        llm_budget_per_session_usd=Decimal("10.00"),
    )
    with pytest.raises(RuntimeError) as excinfo:
        settings.assert_safe_for_environment()
    assert "§12" in str(excinfo.value) or "constitution" in str(excinfo.value).lower()
    assert "5" in str(excinfo.value)


def test_production_with_vertex_backend_and_budget_at_ceiling_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production + vertex + exactly $5.00 — the canonical safe config."""
    _clear_env(monkeypatch)
    settings = Settings(
        llm_backend="vertex",
        app_env="prod",
        llm_budget_per_session_usd=Decimal("5.00"),
    )
    settings.assert_safe_for_environment()  # must not raise
