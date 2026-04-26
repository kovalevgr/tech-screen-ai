"""Tests for the price-table loader and per-call cost arithmetic (T046).

Maps to FR-010 (per-model price table; unknown model is a config error).

Asserts:

- The committed ``app/backend/llm/pricing.yaml`` loads cleanly and
  contains both Gemini 2.5 entries (Flash + Pro) per ADR-003.
- ``cost_for("gemini-2.5-flash", 1000, 1000)`` is exactly
  ``Decimal("0.000375")`` — no floating-point drift, the arithmetic
  uses ``Decimal`` end-to-end (research §6).
- ``cost_for("unknown-model", ...)`` raises ``ModelCallConfigError``
  rather than silently defaulting to zero (FR-010 — unknown identifier
  is a configuration error).
- A YAML payload with a non-positive price fails at *load* time, not
  on first use — pydantic's ``field_validator`` rejects it before the
  table is constructed.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from app.backend.llm.errors import ModelCallConfigError
from app.backend.llm.pricing import PRICING_YAML_PATH, PricingTable


def test_committed_pricing_yaml_loads_both_models() -> None:
    """Both Gemini 2.5 entries (per ADR-003) ship in the committed YAML."""
    table = PricingTable.from_yaml(PRICING_YAML_PATH)
    assert "gemini-2.5-flash" in table.models
    assert "gemini-2.5-pro" in table.models


def test_cost_for_flash_with_1k_input_and_1k_output_is_exact() -> None:
    """1000 input + 1000 output tokens at Flash prices = $0.000375 exactly.

    Per `app/backend/llm/pricing.yaml`:
        input_per_1k_tokens  = "0.000075"
        output_per_1k_tokens = "0.000300"

    1000/1000 tokens × $0.000075 + 1000/1000 tokens × $0.000300
        = Decimal("0.000075") + Decimal("0.000300")
        = Decimal("0.000375")

    No float arithmetic — the equality is exact.
    """
    table = PricingTable.from_yaml(PRICING_YAML_PATH)
    cost = table.cost_for("gemini-2.5-flash", 1000, 1000)
    assert cost == Decimal("0.000375")


def test_cost_for_unknown_model_raises_config_error() -> None:
    """FR-010: an unknown model id is a config error, never $0."""
    table = PricingTable.from_yaml(PRICING_YAML_PATH)
    with pytest.raises(ModelCallConfigError) as excinfo:
        table.cost_for("gemini-no-such", 100, 100)
    assert "gemini-no-such" in str(excinfo.value)


def test_non_positive_price_in_yaml_fails_at_load(tmp_path: Path) -> None:
    """A YAML with a zero or negative price is rejected by the loader.

    Catches "missed a digit / set a price to 0 by accident" at the
    earliest possible moment — load-time, before any call_model invocation
    can charge against an absurd budget.
    """
    bad_yaml = tmp_path / "pricing.yaml"
    bad_yaml.write_text(
        'gemini-bad-model:\n  input_per_1k_tokens: "0"\n  output_per_1k_tokens: "0.001"\n',
        encoding="utf-8",
    )
    with pytest.raises(ModelCallConfigError):
        PricingTable.from_yaml(bad_yaml)


def test_negative_price_in_yaml_fails_at_load(tmp_path: Path) -> None:
    """Negative prices are also rejected at load time."""
    bad_yaml = tmp_path / "pricing.yaml"
    bad_yaml.write_text(
        'gemini-bad-model:\n  input_per_1k_tokens: "-0.001"\n  output_per_1k_tokens: "0.001"\n',
        encoding="utf-8",
    )
    with pytest.raises(ModelCallConfigError):
        PricingTable.from_yaml(bad_yaml)
