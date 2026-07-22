from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


class PricingRegistry:
    def __init__(self, prices: dict[str, ModelPrice] | None = None):
        self._prices = prices or {}

    @classmethod
    def from_mapping(cls, mapping: dict[str, dict[str, float]]) -> "PricingRegistry":
        prices: dict[str, ModelPrice] = {}
        for model, values in mapping.items():
            if not isinstance(values, dict):
                continue
            prices[model] = ModelPrice(
                input_per_million=float(values.get("input_per_million", 0.0)),
                output_per_million=float(values.get("output_per_million", 0.0)),
            )
        return cls(prices=prices)

    def register(self, model: str, *, input_per_million: float, output_per_million: float) -> None:
        self._prices[model] = ModelPrice(
            input_per_million=input_per_million,
            output_per_million=output_per_million,
        )

    def get(self, model: str) -> ModelPrice | None:
        return self._prices.get(model)

    def estimate_cost(self, model: str, *, input_tokens: int, output_tokens: int) -> float:
        price = self.get(model)
        if price is None:
            return 0.0
        return (
            (max(0, input_tokens) / 1_000_000.0) * price.input_per_million
            + (max(0, output_tokens) / 1_000_000.0) * price.output_per_million
        )
