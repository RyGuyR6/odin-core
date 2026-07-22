"""Tests for the AI capability registry (OIC-012)."""

from __future__ import annotations

from app.llm.capability_registry import (
    CONSERVATIVE_DEFAULTS,
    KNOWN_CAPABILITIES,
    CapabilityRegistry,
    get_capability_registry,
)


def test_known_model_returns_correct_capabilities():
    registry = CapabilityRegistry()
    caps = registry.get("gpt-4o")
    assert caps.supports_streaming is True
    assert caps.supports_tools is True
    assert caps.supports_json is True
    assert caps.supports_vision is True
    assert caps.context_window == 128_000


def test_unknown_model_returns_conservative_defaults():
    registry = CapabilityRegistry()
    caps = registry.get("some-future-unknown-model-xyz")
    assert caps is CONSERVATIVE_DEFAULTS
    assert caps.supports_streaming is True
    assert caps.supports_tools is False
    assert caps.supports_embeddings is False
    assert caps.supports_reasoning is False


def test_prefix_match_for_dated_variants():
    """e.g. 'gpt-4o-2024-11-20' should match 'gpt-4o' capabilities."""
    registry = CapabilityRegistry()
    caps = registry.get("gpt-4o-2024-11-20")
    assert caps.supports_tools is True
    assert caps.supports_vision is True


def test_embedding_model_has_correct_flags():
    registry = CapabilityRegistry()
    caps = registry.get("text-embedding-3-small")
    assert caps.supports_embeddings is True
    assert caps.supports_streaming is False
    assert caps.supports_tools is False


def test_reasoning_model_capabilities():
    registry = CapabilityRegistry()
    for model in ("o3", "o1", "o3-mini"):
        caps = registry.get(model)
        assert caps.supports_reasoning is True, f"{model} should support reasoning"
        assert caps.supports_tools is True, f"{model} should support tools"


def test_all_entries_returns_known_capabilities():
    registry = CapabilityRegistry()
    entries = registry.all_entries()
    assert "gpt-5" in entries
    assert "gpt-4o" in entries
    assert "text-embedding-3-small" in entries


def test_module_singleton():
    r1 = get_capability_registry()
    r2 = get_capability_registry()
    assert r1 is r2


def test_custom_registry_data():
    from app.llm.capability_registry import ModelCapabilities

    custom = {
        "my-model": ModelCapabilities(
            supports_tools=True,
            supports_reasoning=True,
            context_window=999,
        )
    }
    registry = CapabilityRegistry(data=custom)
    caps = registry.get("my-model")
    assert caps.supports_tools is True
    assert caps.context_window == 999

    # Unknown falls back to conservative defaults
    unknown = registry.get("not-in-custom")
    assert unknown is CONSERVATIVE_DEFAULTS
