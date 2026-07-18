from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RepositoryFile:
    path: Path
    module: str

    @property
    def extension(self) -> str:
        return self.path.suffix


@dataclass(slots=True)
class RepositoryModule:
    name: str
    file: RepositoryFile


@dataclass(slots=True)
class RepositorySymbol:
    name: str
    kind: str
    module: str
    file: Path | str
    line: int

    decorators: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ImportSymbol:
    module: str
    name: str | None = None
    alias: str | None = None
    line: int = 0


@dataclass(slots=True)
class RepositorySnapshot:
    files: list[RepositoryFile] = field(default_factory=list)
    modules: list[RepositoryModule] = field(default_factory=list)
    symbols: list[RepositorySymbol] = field(default_factory=list)
    imports: list[ImportSymbol] = field(default_factory=list)
