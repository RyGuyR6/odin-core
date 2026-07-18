from __future__ import annotations

from app.repository.models import RepositorySymbol


class SymbolIndex:
    """
    Stores RepositorySymbol objects by name.
    """

    def __init__(self) -> None:
        self._symbols: dict[str, RepositorySymbol] = {}

    def add(self, symbol: RepositorySymbol) -> None:
        self._symbols[symbol.name] = symbol

    def find(self, name: str) -> RepositorySymbol | None:
        return self._symbols.get(name)

    def all(self) -> list[RepositorySymbol]:
        return list(self._symbols.values())

    def clear(self) -> None:
        self._symbols.clear()

    def __len__(self) -> int:
        return len(self._symbols)

    def __contains__(self, name: str) -> bool:
        return name in self._symbols
