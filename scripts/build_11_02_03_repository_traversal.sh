#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

INTELLIGENCE_DIR="backend/app/intelligence"

mkdir -p "$INTELLIGENCE_DIR"

###############################################################################
# scanner.py
###############################################################################

cat > "$INTELLIGENCE_DIR/scanner.py" <<'PY'
"""
Repository Intelligence Scanner.

Traverses the Repository abstraction and builds a ProjectInventory.
"""

from __future__ import annotations

from pathlib import Path

from .models import ModuleInfo, PackageInfo, ProjectInventory


class RepositoryScanner:
    """Builds a ProjectInventory from an existing Repository."""

    def scan(self, repository: object) -> ProjectInventory:
        inventory = ProjectInventory()

        package_lookup: dict[str, PackageInfo] = {}

        for module in self._iter_modules(repository):

            module_path = Path(str(getattr(module, "path", "")))

            package_name = self._package_name(module_path)

            package = package_lookup.get(package_name)

            if package is None:
                package = PackageInfo(name=package_name)
                package_lookup[package_name] = package
                inventory.packages.append(package)

            package.modules.append(
                ModuleInfo(
                    name=getattr(module, "name", module_path.stem),
                    path=str(module_path),
                )
            )

        return inventory

    def _iter_modules(self, repository: object):
        """
        Repository adapter.

        Supports multiple repository implementations without
        coupling the scanner to one concrete class.
        """

        modules = getattr(repository, "modules", None)

        if modules is None:
            return []

        if isinstance(modules, dict):
            return modules.values()

        return modules

    @staticmethod
    def _package_name(path: Path) -> str:
        if not path.parts:
            return "root"

        if len(path.parts) == 1:
            return "root"

        return ".".join(path.parts[:-1])
PY

###############################################################################
# Validate
###############################################################################

python3 -m py_compile "$INTELLIGENCE_DIR/scanner.py"

echo
echo "========================================="
echo "Repository traversal installed."
echo "========================================="