"""Loader for ``configs/llm-limits.yaml`` — the per-session cost ceiling (§12).

Mirrors :mod:`app.backend.llm.models_config` and
:mod:`app.backend.orchestrator.config`: a frozen pydantic document, load-time
validation, one typed error, and a module-level path constant. Constitution §16
— the ceiling is reviewable config, not a literal buried in code.

Money is :class:`~decimal.Decimal` end to end. The YAML value is quoted so
PyYAML hands us a string and the float representation never exists, not even
transiently.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class LlmLimitsConfigError(Exception):
    """``configs/llm-limits.yaml`` is missing, malformed, or out of range."""


class LlmLimitsConfig(BaseModel):
    """The whole ``configs/llm-limits.yaml`` document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_cost_ceiling_usd: Decimal = Field(gt=0)
    """Per-session USD ceiling (constitution §12, default $5.00). Enforcement is
    gated by the ``enforce_session_cost_ceiling`` feature flag (§9); the value
    itself is always used for the observability warning."""

    @classmethod
    def from_yaml(cls, path: Path) -> LlmLimitsConfig:
        """Load and validate the limits document.

        Args:
            path: Path to the ``llm-limits.yaml`` document.

        Returns:
            The frozen, validated :class:`LlmLimitsConfig`.

        Raises:
            LlmLimitsConfigError: The file is not a mapping, holds unknown
                keys, or the ceiling is missing / non-positive.
        """
        try:
            raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise LlmLimitsConfigError(f"{path}: cannot be read: {exc}") from exc
        if not isinstance(raw, dict):
            raise LlmLimitsConfigError(
                f"{path}: expected a mapping at the top level, got {type(raw).__name__}"
            )
        try:
            return cls.model_validate(raw)
        except Exception as exc:
            raise LlmLimitsConfigError(f"{path}: invalid llm-limits.yaml content: {exc}") from exc


LLM_LIMITS_YAML_PATH: Path = Path(__file__).resolve().parents[3] / "configs" / "llm-limits.yaml"
"""Canonical path to the committed limits (repo-root/configs/llm-limits.yaml)."""


def load_llm_limits(path: Path | None = None) -> LlmLimitsConfig:
    """Load the committed limits document (or an explicit override).

    Args:
        path: Optional override, used by tests. Defaults to
            :data:`LLM_LIMITS_YAML_PATH`.

    Returns:
        The frozen, validated :class:`LlmLimitsConfig`.

    Raises:
        LlmLimitsConfigError: See :meth:`LlmLimitsConfig.from_yaml`.
    """
    return LlmLimitsConfig.from_yaml(path or LLM_LIMITS_YAML_PATH)
