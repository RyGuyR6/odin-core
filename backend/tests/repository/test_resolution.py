from pathlib import Path

from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol
from app.repository.resolution import (
    ResolutionContext,
    ResolutionEngine,
    SymbolResolver,
)


def make_symbol(name: str, module: str = "app.example") -> RepositorySymbol:
    return RepositorySymbol(
        name=name,
        module=module,
        file=Path("example.py"),
        line=1,
        kind="function",
    )


def test_symbol_resolver_resolves_by_name():
    index = SymbolIndex()
    index.add(make_symbol("load"))

    resolver = SymbolResolver(index)

    result = resolver.resolve(
        "load",
        ResolutionContext(
            module="app.example",
            file=Path("."),
        ),
    )

    assert result.resolved
    assert result.symbol is not None
    assert result.symbol.name == "load"


def test_symbol_resolver_returns_failure():
    index = SymbolIndex()

    resolver = SymbolResolver(index)

    result = resolver.resolve(
        "missing",
        ResolutionContext(
            module="app.example",
            file=Path("."),
        ),
    )

    assert not result.resolved
    assert result.symbol is None


def test_resolution_engine_delegates():
    index = SymbolIndex()
    index.add(make_symbol("parse"))

    engine = ResolutionEngine(SymbolResolver(index))

    result = engine.resolve(
        "parse",
        ResolutionContext(
            module="app.example",
            file=Path("."),
        ),
    )

    assert result.resolved
    assert result.symbol is not None
    assert result.symbol.name == "parse"
