from __future__ import annotations

from .models import (
    ModuleInfo,
    PackageInfo,
    ProjectInventory,
)


class IntelligenceQueryEngine:
    """Simple query helper for ProjectInventory."""

    def __init__(self, inventory: ProjectInventory):
        self.inventory = inventory

    def packages(self) -> list[PackageInfo]:
        return self.inventory.packages

    def modules(self) -> list[ModuleInfo]:
        return [
            module
            for package in self.inventory.packages
            for module in package.modules
        ]

    def statistics(self) -> dict[str, int]:
        return {
            "packages": len(self.inventory.packages),
            "modules": len(self.modules()),
        }

    def find_module(self, name: str) -> ModuleInfo | None:
        return next(
            (m for m in self.modules() if m.name == name),
            None,
        )
