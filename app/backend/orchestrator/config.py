"""Loader for ``configs/orchestrator.yaml`` — the routing thresholds (contract §8).

Mirrors :mod:`app.backend.llm.models_config`: frozen pydantic models,
load-time validation, one typed error. Every threshold the state machine
branches on lives in this file — constitution §2 (no LLM-driven flow
control) is only credible if the numbers are reviewable config, and §16
(configs as code) is what makes them reviewable.

Unknown keys are rejected at every level: a typo'd threshold must fail the
load, not silently fall back to a default that nobody chose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class OrchestratorConfigError(Exception):
    """``configs/orchestrator.yaml`` is missing keys, malformed, or out of range."""


class AdjudicationConfig(BaseModel):
    """Thresholds for the owner's 2/1/0 turn-adjudication table (contract §5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    confidence_min: float = Field(ge=0.0, le=0.99)
    """ANSWERED requires the best assessment's ``confidence >= confidence_min``
    (boundary inclusive). Capped at 0.99 because that is the assessor
    contract's own confidence ceiling (v0003 ``schema.json``): a higher
    threshold would make ANSWERED unreachable, and a config that can never
    fire should fail at load, not in an interview."""

    max_probes_per_competency: int = Field(ge=0)
    """CLARIFY is available while ``probes_used < max_probes_per_competency``.
    Zero is legal and means "never probe"."""

    min_probe_seconds: int = Field(ge=0)
    """CLARIFY also requires strictly more than this many seconds left in the
    competency budget — there is no point starting a probe we cannot hear the
    answer to."""


class FlagsConfig(BaseModel):
    """Review-flag thresholds (contract §5 bullet 3, §6.4)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cheat_flags_to_review: int = Field(ge=1)
    """``LIKELY_CHEATING`` red flags needed to set ``flagged_for_review``. The
    session continues and the candidate is never confronted (contract §5)."""

    drift_to_review: int = Field(ge=1)
    """Interviewer move-drift events needed to set ``flagged_for_review``."""


class TimingConfig(BaseModel):
    """Clock-free timing budgets — evaluated against event timestamps (§6.5)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidate_timeout_minutes: int = Field(ge=1)
    """Silence longer than this aborts the session (``candidate_timeout``,
    contract §6.6). Beats every other budget on a single tick (§6.7)."""

    tick_seconds: int = Field(ge=15)
    """Expected ``TimerTick`` cadence. The core never sleeps; this documents
    the shell's obligation, and the ≥15 s floor is the contract §3 cadence."""


class OrchestratorConfig(BaseModel):
    """The whole ``configs/orchestrator.yaml`` document (contract §8)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    adjudication: AdjudicationConfig
    flags: FlagsConfig
    timing: TimingConfig
    state_schema_version: int = Field(ge=1)
    """Version stamped into every persisted ``SessionState``. A bump is a
    breaking state change: :mod:`app.backend.orchestrator.persistence` fails
    loudly on a mismatch rather than silently migrating."""

    @classmethod
    def from_yaml(cls, path: Path) -> OrchestratorConfig:
        """Load and validate the orchestrator config from a YAML file.

        Args:
            path: Path to the ``orchestrator.yaml`` document.

        Returns:
            The frozen, validated :class:`OrchestratorConfig`.

        Raises:
            OrchestratorConfigError: The file is not a mapping, holds unknown
                keys, or any value is out of range.
        """
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise OrchestratorConfigError(
                f"{path}: expected a mapping at the top level, got {type(raw).__name__}"
            )
        try:
            return cls.model_validate(raw)
        except Exception as exc:
            raise OrchestratorConfigError(
                f"{path}: invalid orchestrator.yaml content: {exc}"
            ) from exc


ORCHESTRATOR_YAML_PATH: Path = Path(__file__).resolve().parents[3] / "configs" / "orchestrator.yaml"
"""Canonical path to the committed thresholds (repo-root/configs/orchestrator.yaml)."""


def load_orchestrator_config(path: Path | None = None) -> OrchestratorConfig:
    """Load the committed orchestrator config (or an explicit override).

    Args:
        path: Optional override, used by tests and by a future admin
            promotion flow. Defaults to :data:`ORCHESTRATOR_YAML_PATH`.

    Returns:
        The frozen, validated :class:`OrchestratorConfig`.

    Raises:
        OrchestratorConfigError: See :meth:`OrchestratorConfig.from_yaml`.
    """
    return OrchestratorConfig.from_yaml(path or ORCHESTRATOR_YAML_PATH)
