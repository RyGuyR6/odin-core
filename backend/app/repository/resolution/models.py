from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    """
    Fully qualified symbol resolved within the repository.
    """

    name: str
    qualified_name: str
    module: str
    file: Path
    line: int
    kind: str


@dataclass(slots=True)
class ResolutionContext:
    """
    Context used while resolving symbols.
    """

    module: str
    file: Path
    imports: dict[str, str] = field(default_factory=dict)
    locals: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ResolutionResult:
    """
    Result of a symbol resolution attempt.
    """

    symbol: ResolvedSymbol | None = None
    resolved: bool = False
    reason: str | None = None
