from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class FunctionInfo:
    """Represents a standalone function."""

    name: str


@dataclass(slots=True)
class ClassInfo:
    """Represents a class and its methods."""

    name: str
    methods: list[FunctionInfo] = field(default_factory=list)


@dataclass(slots=True)
class ModuleInfo:
    """Represents a Python module."""

    name: str
    path: str

    classes: list[ClassInfo] = field(default_factory=list)
    functions: list[FunctionInfo] = field(default_factory=list)


@dataclass(slots=True)
class PackageInfo:
    """Represents a Python package."""

    name: str
    modules: list[ModuleInfo] = field(default_factory=list)


@dataclass(slots=True)
class ProjectInventory:
    """Root intelligence inventory."""

    packages: list[PackageInfo] = field(default_factory=list)

    @property
    def module_count(self) -> int:
        """Return the total number of modules."""
        return sum(len(package.modules) for package in self.packages)
