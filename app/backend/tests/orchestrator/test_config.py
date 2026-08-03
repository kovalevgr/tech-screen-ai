"""``configs/orchestrator.yaml`` loader (contract §8, constitution §16).

The committed file is the source of truth for every routing threshold; the
loader must accept it exactly, and must reject anything a reviewer would not
recognise as a valid thresholds document.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.backend.orchestrator.config import (
    ORCHESTRATOR_YAML_PATH,
    OrchestratorConfig,
    OrchestratorConfigError,
    load_orchestrator_config,
)

_VALID_YAML = """
adjudication:
  confidence_min: 0.6
  max_probes_per_competency: 2
  min_probe_seconds: 60
flags:
  cheat_flags_to_review: 1
  drift_to_review: 3
timing:
  candidate_timeout_minutes: 10
  tick_seconds: 15
state_schema_version: 1
"""


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "orchestrator.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_the_committed_config_matches_the_contract_defaults() -> None:
    config = load_orchestrator_config()

    assert config.adjudication.confidence_min == 0.6
    assert config.adjudication.max_probes_per_competency == 2
    assert config.adjudication.min_probe_seconds == 60
    assert config.flags.cheat_flags_to_review == 1
    assert config.flags.drift_to_review == 3
    assert config.timing.candidate_timeout_minutes == 10
    assert config.timing.tick_seconds == 15
    assert config.state_schema_version == 1


def test_the_committed_config_lives_at_the_canonical_path() -> None:
    assert ORCHESTRATOR_YAML_PATH.is_file()
    assert ORCHESTRATOR_YAML_PATH.parts[-2:] == ("configs", "orchestrator.yaml")


def test_the_config_is_frozen() -> None:
    """Thresholds change by config PR (§16), never by a runtime assignment."""
    config = load_orchestrator_config()

    with pytest.raises(ValidationError, match="frozen"):
        config.adjudication.confidence_min = 0.1


def test_an_unknown_threshold_key_is_rejected(tmp_path: Path) -> None:
    """A typo must fail the load, not silently fall back to a default."""
    path = _write(tmp_path, _VALID_YAML.replace("min_probe_seconds", "min_prob_seconds"))

    with pytest.raises(OrchestratorConfigError, match="invalid orchestrator.yaml"):
        OrchestratorConfig.from_yaml(path)


def test_a_missing_section_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, _VALID_YAML.split("flags:")[0] + "state_schema_version: 1\n")

    with pytest.raises(OrchestratorConfigError):
        OrchestratorConfig.from_yaml(path)


def test_a_non_mapping_document_is_rejected(tmp_path: Path) -> None:
    path = _write(tmp_path, "- not\n- a\n- mapping\n")

    with pytest.raises(OrchestratorConfigError, match="expected a mapping"):
        OrchestratorConfig.from_yaml(path)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("confidence_min: 0.6", "confidence_min: 1.0"),
        ("confidence_min: 0.6", "confidence_min: -0.1"),
        ("max_probes_per_competency: 2", "max_probes_per_competency: -1"),
        ("cheat_flags_to_review: 1", "cheat_flags_to_review: 0"),
        ("drift_to_review: 3", "drift_to_review: 0"),
        ("candidate_timeout_minutes: 10", "candidate_timeout_minutes: 0"),
        ("tick_seconds: 15", "tick_seconds: 5"),
        ("state_schema_version: 1", "state_schema_version: 0"),
    ],
)
def test_out_of_range_thresholds_are_rejected(tmp_path: Path, old: str, new: str) -> None:
    path = _write(tmp_path, _VALID_YAML.replace(old, new))

    with pytest.raises(OrchestratorConfigError):
        OrchestratorConfig.from_yaml(path)
