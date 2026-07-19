from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SymbolReference:
    name: str
    module: str
    line: int
    qualified_name: str = ""


@dataclass(slots=True)
class CrossReferenceIndex:
    definitions: dict[str, SymbolReference] = field(default_factory=dict)
    references: dict[str, list[SymbolReference]] = field(default_factory=dict)

    def add_definition(self, symbol: SymbolReference) -> None:
        self.definitions[symbol.name] = symbol

    def add_reference(self, symbol: SymbolReference) -> None:
        self.references.setdefault(symbol.name, []).append(symbol)

    def find_definition(self, name: str) -> SymbolReference | None:
        return self.definitions.get(name)

    def find_references(self, name: str) -> list[SymbolReference]:
        return list(self.references.get(name, []))
