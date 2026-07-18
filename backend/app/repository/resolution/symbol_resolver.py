from __future__ import annotations

from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol

from .models import (
    ResolutionContext,
    ResolutionResult,
    ResolvedSymbol,
)


class SymbolResolver:
    """
    Resolves symbol references against the repository symbol index.
    """

    def __init__(self, index: SymbolIndex):
        self.index = index

    def resolve(
        self,
        name: str,
        context: ResolutionContext,
    ) -> ResolutionResult:
        """
        Resolve a symbol using progressively broader lookups.
        """

        #
        # Fully-qualified lookup
        #

        symbol = self.index.find(name)

        if symbol is None and context.module:
            qualified = f"{context.module}.{name}"
            symbol = self.index.find(qualified)

        if symbol is None:
            for candidate in self.index.all():
                if candidate.name == name:
                    symbol = candidate
                    break

        if symbol is None:
            return ResolutionResult(
                resolved=False,
                reason=f"Unable to resolve '{name}'.",
            )

        return ResolutionResult(
            resolved=True,
            symbol=ResolvedSymbol(
                name=symbol.name,
                qualified_name=f"{symbol.module}.{symbol.name}",
                module=symbol.module,
                file=symbol.file,
                line=symbol.line,
                kind=symbol.kind,
            ),
        )
