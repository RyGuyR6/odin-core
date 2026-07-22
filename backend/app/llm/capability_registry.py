"""Static AI capability metadata registry.

This module provides *reference* capability data for well-known OpenAI models.
Presence in this registry does NOT imply that a model is available to the
configured API account.  Availability is determined separately by querying
the live models endpoint.

Unknown models (returned by OpenAI but not in this registry) are assigned
conservative defaults: streaming supported, all advanced capabilities off.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    """Capability flags for a single model."""

    supports_streaming: bool = True
    supports_tools: bool = False
    supports_json: bool = False
    supports_embeddings: bool = False
    supports_reasoning: bool = False
    supports_large_context: bool = False
    supports_structured_output: bool = False
    supports_vision: bool = False
    supports_image_generation: bool = False
    context_window: int | None = None
    display_name: str | None = None


# Conservative defaults applied to any model NOT found in KNOWN_CAPABILITIES.
CONSERVATIVE_DEFAULTS = ModelCapabilities(
    supports_streaming=True,
    supports_tools=False,
    supports_json=False,
    supports_embeddings=False,
    supports_reasoning=False,
    supports_large_context=False,
    supports_structured_output=False,
    supports_vision=False,
    supports_image_generation=False,
)

# ---------------------------------------------------------------------------
# Known OpenAI model capability metadata.
# These are reference entries only — not an availability claim.
# ---------------------------------------------------------------------------
KNOWN_CAPABILITIES: dict[str, ModelCapabilities] = {
    # GPT-5 family
    "gpt-5": ModelCapabilities(
        display_name="GPT-5",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_vision=True,
        supports_reasoning=True,
        supports_large_context=True,
    ),
    "gpt-5-mini": ModelCapabilities(
        display_name="GPT-5 Mini",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
    ),
    # GPT-4.1 family
    "gpt-4.1": ModelCapabilities(
        display_name="GPT-4.1",
        context_window=1_047_576,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_vision=True,
        supports_large_context=True,
    ),
    "gpt-4.1-mini": ModelCapabilities(
        display_name="GPT-4.1 Mini",
        context_window=1_047_576,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_large_context=True,
    ),
    "gpt-4.1-nano": ModelCapabilities(
        display_name="GPT-4.1 Nano",
        context_window=1_047_576,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_large_context=True,
    ),
    # GPT-4o family
    "gpt-4o": ModelCapabilities(
        display_name="GPT-4o",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_vision=True,
    ),
    "gpt-4o-mini": ModelCapabilities(
        display_name="GPT-4o Mini",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
    ),
    # o-series reasoning models
    "o3": ModelCapabilities(
        display_name="o3",
        context_window=200_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_reasoning=True,
        supports_large_context=True,
    ),
    "o3-mini": ModelCapabilities(
        display_name="o3-mini",
        context_window=200_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_reasoning=True,
        supports_large_context=True,
    ),
    "o1": ModelCapabilities(
        display_name="o1",
        context_window=200_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_structured_output=True,
        supports_reasoning=True,
        supports_large_context=True,
    ),
    "o1-mini": ModelCapabilities(
        display_name="o1-mini",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=False,
        supports_json=True,
        supports_reasoning=True,
    ),
    "o1-preview": ModelCapabilities(
        display_name="o1-preview",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=False,
        supports_json=True,
        supports_reasoning=True,
    ),
    # GPT-4 Turbo
    "gpt-4-turbo": ModelCapabilities(
        display_name="GPT-4 Turbo",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
        supports_vision=True,
    ),
    "gpt-4-turbo-preview": ModelCapabilities(
        display_name="GPT-4 Turbo Preview",
        context_window=128_000,
        supports_streaming=True,
        supports_tools=True,
        supports_json=True,
    ),
    # Embedding models
    "text-embedding-3-small": ModelCapabilities(
        display_name="text-embedding-3-small",
        context_window=8_191,
        supports_streaming=False,
        supports_embeddings=True,
    ),
    "text-embedding-3-large": ModelCapabilities(
        display_name="text-embedding-3-large",
        context_window=8_191,
        supports_streaming=False,
        supports_embeddings=True,
    ),
    "text-embedding-ada-002": ModelCapabilities(
        display_name="text-embedding-ada-002",
        context_window=8_191,
        supports_streaming=False,
        supports_embeddings=True,
    ),
}


class CapabilityRegistry:
    """Looks up static capability metadata for model IDs.

    This registry is intentionally read-only and does not perform any
    API calls.  It never asserts model availability.
    """

    def __init__(self, data: dict[str, ModelCapabilities] | None = None) -> None:
        self._data = data if data is not None else KNOWN_CAPABILITIES

    def get(self, model_id: str) -> ModelCapabilities:
        """Return capabilities for *model_id*.

        For unknown models, returns CONSERVATIVE_DEFAULTS so callers always
        get a valid capabilities object without discarding the model.
        """
        # Exact match first
        if model_id in self._data:
            return self._data[model_id]
        # Prefix match: e.g. "gpt-4o-2024-11-20" → "gpt-4o"
        for known_id, caps in self._data.items():
            if model_id.startswith(known_id):
                return caps
        return CONSERVATIVE_DEFAULTS

    def known_ids(self) -> list[str]:
        return list(self._data)

    def all_entries(self) -> dict[str, ModelCapabilities]:
        return dict(self._data)


# Module-level singleton
_registry: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry()
    return _registry
