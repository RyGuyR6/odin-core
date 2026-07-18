from __future__ import annotations

from .models import ResolutionContext, ResolutionResult
from .symbol_resolver import SymbolResolver


class ResolutionEngine:
    """
    Coordinates symbol resolution strategies.

    Additional strategies (scope, imports, inheritance, aliases, etc.)
    can be added here without changing the Repository API.
    """

    def __init__(self, resolver: SymbolResolver):
        self.resolver = resolver

    def resolve(
        self,
        name: str,
        context: ResolutionContext,
    ) -> ResolutionResult:
        #
        # Future pipeline:
        #
        # 1. ScopeResolver
        # 2. ImportResolver
        # 3. SymbolResolver
        # 4. TypeResolver
        #
        return self.resolver.resolve(name, context)
