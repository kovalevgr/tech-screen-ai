"""Backend runtime settings (env-loaded).

Slim ``pydantic-settings`` ``Settings`` class introduced by T04. Covers four
non-secret keys (per ADR-022):

- ``LLM_BACKEND``           — ``"mock"`` | ``"vertex"``; production refuses ``"mock"``.
- ``APP_ENV``               — ``"dev"`` | ``"test"`` | ``"prod"``; the canonical
  runtime selector already set by ``Dockerfile`` (line 60 / line 84) and every
  ``docker-compose*.yml`` file. ``Settings`` reads it so the production-mode
  guard fires under the existing infra wiring.
- ``LLM_BUDGET_PER_SESSION_USD`` — Decimal; production caps at $5.00 (constitution §12).
- ``LLM_FIXTURES_DIR``      — Path; mock-mode fixture root.

The :meth:`Settings.assert_safe_for_environment` method is invoked once at
``app/backend/main.py`` module init. Production startup fails fast with a
clear error when the configuration would violate spec FR-007 / SC-010 or
constitution §12.

See ``specs/007-t04-vertex-client-wrapper/data-model.md`` §10.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROD_BUDGET_CEILING_USD: Decimal = Decimal("5.00")


class Settings(BaseSettings):
    """Backend runtime settings loaded from environment / ``.env``."""

    llm_backend: Literal["mock", "vertex"] = "mock"
    app_env: Literal["dev", "test", "prod"] = "dev"
    llm_budget_per_session_usd: Decimal = Decimal("5.00")
    llm_fixtures_dir: Path = Path("app/backend/tests/fixtures/llm_responses")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    def assert_safe_for_environment(self) -> None:
        """Refuse to start when the configuration would violate hard caps.

        Two production-only checks (per spec FR-007 / SC-010 and
        constitution §12):

        1. ``APP_ENV=prod`` with ``LLM_BACKEND=mock`` → never. A
           production worker serving mocked LLM output would silently
           short-circuit candidate-facing flows.
        2. ``LLM_BUDGET_PER_SESSION_USD > $5.00`` in production →
           constitution §12 sets the per-session ceiling at $5.00.

        Raises :class:`RuntimeError` so the failure is unambiguous in
        Cloud Run logs (a non-zero exit on first import).
        """
        if self.app_env == "prod":
            if self.llm_backend == "mock":
                raise RuntimeError("FR-007: LLM_BACKEND=mock is not allowed when APP_ENV=prod")
            if self.llm_budget_per_session_usd > _PROD_BUDGET_CEILING_USD:
                raise RuntimeError(
                    "constitution §12: LLM_BUDGET_PER_SESSION_USD must not "
                    f"exceed ${_PROD_BUDGET_CEILING_USD} in production "
                    f"(got {self.llm_budget_per_session_usd})"
                )
