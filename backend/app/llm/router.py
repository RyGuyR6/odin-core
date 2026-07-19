from __future__ import annotations

from .config import LLMSettings
from .registry import ProviderRegistry


class LLMRouter:
    def __init__(self, registry: ProviderRegistry, settings: LLMSettings):
        self.registry = registry
        self.settings = settings

    def candidates(self, requested: str | None, allow_failover: bool) -> list[str]:
        first = requested or self.settings.default_provider
        names = [first]
        if allow_failover:
            names.extend(self.settings.provider_priority)
        seen: set[str] = set()
        result: list[str] = []
        available = set(self.registry.names())
        for name in names:
            normalized = name.lower()
            if normalized not in seen and normalized in available:
                result.append(normalized)
                seen.add(normalized)
        return result
