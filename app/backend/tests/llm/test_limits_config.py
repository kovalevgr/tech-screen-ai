"""``configs/llm-limits.yaml`` loader (T21, §12 + §16)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.backend.llm.limits_config import (
    LLM_LIMITS_YAML_PATH,
    LlmLimitsConfig,
    LlmLimitsConfigError,
    load_llm_limits,
)


def test_the_committed_ceiling_is_the_constitutional_five_dollars() -> None:
    limits = load_llm_limits()

    assert limits.session_cost_ceiling_usd == Decimal("5.00")


def test_the_ceiling_is_a_decimal_not_a_float() -> None:
    """Money never round-trips through binary floating point (§12)."""
    limits = load_llm_limits()

    assert isinstance(limits.session_cost_ceiling_usd, Decimal)
    assert str(limits.session_cost_ceiling_usd) == "5.00"


def test_an_unknown_key_fails_the_load(tmp_path: Path) -> None:
    path = tmp_path / "llm-limits.yaml"
    path.write_text('session_cost_ceiling_usd: "5.00"\nmystery: 1\n', encoding="utf-8")

    with pytest.raises(LlmLimitsConfigError):
        LlmLimitsConfig.from_yaml(path)


def test_a_non_positive_ceiling_fails_the_load(tmp_path: Path) -> None:
    path = tmp_path / "llm-limits.yaml"
    path.write_text('session_cost_ceiling_usd: "0"\n', encoding="utf-8")

    with pytest.raises(LlmLimitsConfigError):
        LlmLimitsConfig.from_yaml(path)


def test_a_missing_file_fails_the_load(tmp_path: Path) -> None:
    with pytest.raises(LlmLimitsConfigError):
        LlmLimitsConfig.from_yaml(tmp_path / "absent.yaml")


def test_a_scalar_document_fails_the_load(tmp_path: Path) -> None:
    path = tmp_path / "llm-limits.yaml"
    path.write_text("5.00\n", encoding="utf-8")

    with pytest.raises(LlmLimitsConfigError):
        LlmLimitsConfig.from_yaml(path)


def test_the_canonical_path_points_at_the_committed_file() -> None:
    assert LLM_LIMITS_YAML_PATH.is_file()
    assert LLM_LIMITS_YAML_PATH.parts[-2:] == ("configs", "llm-limits.yaml")
