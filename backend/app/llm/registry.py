from __future__ import annotations

from .exceptions import ProviderNotFoundError
from .providers.base import LLMProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[str, LLMProvider] = {}

    def register(self, provider: LLMProvider, *, replace: bool = False) -> None:
        key = provider.name.lower().strip()
        if not key:
            raise ValueError("Provider name cannot be empty")
        if key in self._providers and not replace:
            raise ValueError(f"Provider already registered: {key}")
        self._providers[key] = provider

    def unregister(self, name: str) -> None:
        self._providers.pop(name.lower(), None)

    def get(self, name: str) -> LLMProvider:
        try:
            return self._providers[name.lower()]
        except KeyError as exc:
            raise ProviderNotFoundError(f"Unknown LLM provider: {name}") from exc

    def all(self) -> list[LLMProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers)
