"""Vertex AI price table loader and per-call cost arithmetic.

Loads ``app/backend/llm/pricing.yaml`` (committed in Git per constitution §16)
into a frozen :class:`PricingTable`. The table is the canonical model
registry — an unknown model identifier is a configuration error rather
than a zero-cost silent default (spec FR-010).

All arithmetic uses :class:`decimal.Decimal` per research §6 — LLM token
prices are tiny (Gemini 2.5 Flash is $0.000075 per 1k input tokens), and
floating-point drift exactly where the per-session ceiling check happens
would silently violate constitution §12.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, field_validator

from app.backend.llm.errors import ModelCallConfigError

_THOUSAND: Decimal = Decimal(1000)


class ModelPricing(BaseModel):
    """Per-1k-tokens input / output prices for a single model."""

    model_config = ConfigDict(frozen=True)

    input_per_1k_tokens: Decimal
    output_per_1k_tokens: Decimal

    @field_validator("input_per_1k_tokens", "output_per_1k_tokens")
    @classmethod
    def _positive_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("price must be positive")
        return v


class PricingTable(BaseModel):
    """Frozen model-keyed price table loaded from ``pricing.yaml``."""

    model_config = ConfigDict(frozen=True)

    models: dict[str, ModelPricing]

    @classmethod
    def from_yaml(cls, path: Path) -> PricingTable:
        """Load a pricing table from a YAML file.

        The YAML shape is ``{<model_id>: {input_per_1k_tokens, output_per_1k_tokens}}``
        with prices stored as strings to round-trip cleanly through Decimal.
        """
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ModelCallConfigError(
                f"{path}: expected a mapping at the top level, got {type(raw).__name__}"
            )
        models: dict[str, ModelPricing] = {}
        for model_id, entry in raw.items():
            if not isinstance(model_id, str):
                raise ModelCallConfigError(
                    f"{path}: model id must be string, got {type(model_id).__name__}"
                )
            if not isinstance(entry, dict):
                raise ModelCallConfigError(f"{path}: entry for {model_id!r} must be a mapping")
            try:
                models[model_id] = ModelPricing.model_validate(entry)
            except Exception as exc:  # pragma: no cover - re-raised as config error
                raise ModelCallConfigError(
                    f"{path}: invalid pricing entry for {model_id!r}: {exc}"
                ) from exc
        return cls(models=models)

    def cost_for(self, model: str, input_tokens: int, output_tokens: int) -> Decimal:
        """Compute the USD cost of a call with the given token counts.

        Raises :class:`ModelCallConfigError` for an unknown model identifier
        (FR-010) — never silently defaults to zero. Token counts must be
        non-negative.
        """
        if input_tokens < 0 or output_tokens < 0:
            raise ModelCallConfigError(
                f"token counts must be non-negative (input={input_tokens}, output={output_tokens})"
            )
        if model not in self.models:
            raise ModelCallConfigError(f"unknown model {model!r} — add it to pricing.yaml")
        p = self.models[model]
        return (
            p.input_per_1k_tokens * Decimal(input_tokens) / _THOUSAND
            + p.output_per_1k_tokens * Decimal(output_tokens) / _THOUSAND
        )


PRICING_YAML_PATH: Path = Path(__file__).resolve().parent / "pricing.yaml"
"""Canonical path to the committed pricing table."""
