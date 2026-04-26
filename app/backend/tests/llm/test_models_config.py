"""Tests for the per-agent ``configs/models.yaml`` loader (T047).

Maps to FR-019 (per-agent model registry; unknown agent is a config error).

Asserts:

- The committed ``configs/models.yaml`` loads cleanly and exposes all
  three required agents (``interviewer``, ``assessor``, ``planner``).
- ``for_agent("interviewer")`` returns a ``ModelConfig`` with the
  expected model id (``gemini-2.5-flash``) and the placeholder prompt
  version (``v0001``) per Clarifications 2026-04-26 (Q5).
- ``for_agent("unknown")`` raises ``ModelCallConfigError``.
- A YAML missing one of the three required agents fails *at load time*,
  not on first ``for_agent`` call.
- An out-of-range temperature (pydantic ``Field(ge=0.0, le=2.0)``)
  fails at load time as well.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.backend.llm.errors import ModelCallConfigError
from app.backend.llm.models_config import MODELS_YAML_PATH, ModelsConfig


def test_committed_models_yaml_loads_all_three_agents() -> None:
    """All three required agents (per Clarifications 2026-04-26 Q5) ship today."""
    cfg = ModelsConfig.from_yaml(MODELS_YAML_PATH)
    assert cfg.interviewer is not None
    assert cfg.assessor is not None
    assert cfg.planner is not None


def test_for_agent_interviewer_returns_expected_model_and_prompt_version() -> None:
    """Interviewer ships Gemini 2.5 Flash + the v0001 prompt-version placeholder.

    Model choice per ADR-003. Prompt version is the placeholder string T17
    swaps for the real ``prompts/interviewer/v0001/`` content.
    """
    cfg = ModelsConfig.from_yaml(MODELS_YAML_PATH)
    interviewer = cfg.for_agent("interviewer")
    assert interviewer.model == "gemini-2.5-flash"
    assert interviewer.prompt_version == "v0001"


def test_for_agent_unknown_raises_config_error() -> None:
    """FR-019: ``for_agent("unknown")`` is a configuration error, not a None."""
    cfg = ModelsConfig.from_yaml(MODELS_YAML_PATH)
    with pytest.raises(ModelCallConfigError) as excinfo:
        cfg.for_agent("unknown")
    assert "unknown" in str(excinfo.value)


def test_yaml_missing_one_agent_fails_at_load(tmp_path: Path) -> None:
    """Missing ``planner`` (or any required agent) is rejected at load time."""
    incomplete = tmp_path / "models.yaml"
    incomplete.write_text(
        "interviewer:\n"
        "  model: gemini-2.5-flash\n"
        '  prompt_version: "v0001"\n'
        "  temperature: 0.4\n"
        "  max_output_tokens: 2048\n"
        "assessor:\n"
        "  model: gemini-2.5-flash\n"
        '  prompt_version: "v0001"\n'
        "  temperature: 0.1\n"
        "  max_output_tokens: 2048\n",
        encoding="utf-8",
    )
    with pytest.raises(ModelCallConfigError) as excinfo:
        ModelsConfig.from_yaml(incomplete)
    assert "planner" in str(excinfo.value)


def test_yaml_with_out_of_range_temperature_fails_at_load(tmp_path: Path) -> None:
    """``temperature`` is bounded ``[0.0, 2.0]``; > 2.0 is rejected at load."""
    bad_temp = tmp_path / "models.yaml"
    bad_temp.write_text(
        "interviewer:\n"
        "  model: gemini-2.5-flash\n"
        '  prompt_version: "v0001"\n'
        "  temperature: 5.0\n"
        "  max_output_tokens: 2048\n"
        "assessor:\n"
        "  model: gemini-2.5-flash\n"
        '  prompt_version: "v0001"\n'
        "  temperature: 0.1\n"
        "  max_output_tokens: 2048\n"
        "planner:\n"
        "  model: gemini-2.5-pro\n"
        '  prompt_version: "v0001"\n'
        "  temperature: 0.3\n"
        "  max_output_tokens: 4096\n",
        encoding="utf-8",
    )
    with pytest.raises(ModelCallConfigError):
        ModelsConfig.from_yaml(bad_temp)
