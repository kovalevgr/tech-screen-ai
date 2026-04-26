"""Loader for ``configs/models.yaml`` — the per-agent model registry.

Maps agent name to the active ``ModelConfig`` (model identifier, prompt
version, temperature, max output tokens). T04 ships entries for the three
agents committed in this PR (``interviewer``, ``assessor``, ``planner``)
per Clarifications 2026-04-26 (Q5).

Caps from constitution §12 (``max_output_tokens <= 4096``) and pydantic's
range validation on ``temperature`` are applied at load time. An unknown
agent at runtime is a configuration error (spec FR-019).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.backend.llm.errors import ModelCallConfigError

_REQUIRED_AGENTS: Final[frozenset[str]] = frozenset({"interviewer", "assessor", "planner"})


class ModelConfig(BaseModel):
    """Per-agent model selection + generation parameters."""

    model_config = ConfigDict(frozen=True)

    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    max_output_tokens: int = Field(ge=1, le=4096)


class ModelsConfig(BaseModel):
    """The full ``configs/models.yaml`` content — three agents required."""

    model_config = ConfigDict(frozen=True)

    interviewer: ModelConfig
    assessor: ModelConfig
    planner: ModelConfig

    @classmethod
    def from_yaml(cls, path: Path) -> ModelsConfig:
        """Load the per-agent registry from a YAML file.

        Raises :class:`ModelCallConfigError` on missing agents, unknown
        keys at the top level, or any field validation failure.
        """
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ModelCallConfigError(
                f"{path}: expected a mapping at the top level, got {type(raw).__name__}"
            )
        missing = _REQUIRED_AGENTS - set(raw.keys())
        if missing:
            raise ModelCallConfigError(f"{path}: missing required agent entries: {sorted(missing)}")
        try:
            return cls.model_validate(raw)
        except Exception as exc:
            raise ModelCallConfigError(f"{path}: invalid models.yaml content: {exc}") from exc

    def for_agent(self, agent: str) -> ModelConfig:
        """Resolve the :class:`ModelConfig` for a known agent name.

        Raises :class:`ModelCallConfigError` for any name outside the
        committed agent set (T04 ships exactly three; new agents arrive
        via a `configs/models.yaml` PR + a downstream task).
        """
        if agent not in _REQUIRED_AGENTS:
            raise ModelCallConfigError(
                f"unknown agent {agent!r} — known: {sorted(_REQUIRED_AGENTS)}"
            )
        # Frozen pydantic model; explicit branching keeps mypy --strict happy
        # without leaking `Any` from `getattr`.
        if agent == "interviewer":
            return self.interviewer
        if agent == "assessor":
            return self.assessor
        return self.planner


MODELS_YAML_PATH: Path = Path(__file__).resolve().parents[3] / "configs" / "models.yaml"
"""Canonical path to the committed per-agent registry (repo-root/configs/models.yaml)."""
