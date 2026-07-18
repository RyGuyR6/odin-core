from __future__ import annotations

from app.repository.graph import (
    CallGraph,
    ImportGraph,
)
from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol


class RepositoryQuery:

    def __init__(
        self,
        symbols: SymbolIndex,
        imports: ImportGraph,
        calls: CallGraph,
    ):
        self.symbols = symbols
        self.imports = imports
        self.calls = calls

    #
    # Symbols
    #

    def find_symbol(
        self,
        name: str,
    ) -> RepositorySymbol | None:
        return self.symbols.find(name)

    def all_symbols(self) -> list[RepositorySymbol]:
        return self.symbols.all()

    def search(
        self,
        text: str,
    ) -> list[RepositorySymbol]:

        text = text.lower()

        return [
            symbol
            for symbol in self.symbols.all()
            if text in symbol.name.lower()
        ]

    #
    # Imports
    #

    def dependencies(
        self,
        module: str,
    ) -> list[str]:
        return self.imports.dependencies(module)

    def dependents(
        self,
        module: str,
    ) -> list[str]:
        return self.imports.dependents(module)

    def modules(self) -> list[str]:
        modules: set[str] = set()

        for edge in self.imports.edges:
            modules.add(edge.source)
            modules.add(edge.target)

        return sorted(modules)

    #
    # Calls
    #

    def callers(
        self,
        callee: str,
    ) -> list[str]:
        return self.calls.callers(callee)

    def callees(
        self,
        caller: str,
    ) -> list[str]:
        return self.calls.callees(caller)
