from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class IRFunction:
    name: str
    qualified_name: str
    line: int


@dataclass(slots=True)
class IRClass:
    name: str
    qualified_name: str
    line: int
    methods: list[IRFunction] = field(default_factory=list)


@dataclass(slots=True)
class IRCall:
    caller: str
    callee: str
    line: int


@dataclass(slots=True)
class IRModule:
    name: str
    path: Path

    classes: list[IRClass] = field(default_factory=list)
    functions: list[IRFunction] = field(default_factory=list)
    calls: list[IRCall] = field(default_factory=list)