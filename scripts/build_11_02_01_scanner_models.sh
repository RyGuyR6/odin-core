#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

APP_DIR="backend/app/intelligence"

mkdir -p "$APP_DIR"

# --------------------------------------------------------------------
# __init__.py
# --------------------------------------------------------------------

touch "$APP_DIR/__init__.py"

# --------------------------------------------------------------------
# scanner.py
# --------------------------------------------------------------------

cat > "$APP_DIR/scanner.py" <<'PY'
"""
Repository Intelligence Scanner.

The scanner converts a loaded Repository into a ProjectInventory.
It consumes repository abstractions rather than reparsing source files.
"""

from __future__ import annotations

from typing import Optional

from .models import ProjectInventory


class IntelligenceScanner:
    """
    Primary entry point for repository intelligence.

    Later sprints will implement repository traversal,
    inventory population, and semantic analysis.
    """

    def __init__(self) -> None:
        pass

    def scan(self, repository: object) -> ProjectInventory:
        """
        Scan a loaded repository.

        Parameters
        ----------
        repository:
            Repository abstraction.

        Returns
        -------
        ProjectInventory
        """
        return ProjectInventory()
PY

# --------------------------------------------------------------------
# engine.py
# --------------------------------------------------------------------

cat > "$APP_DIR/engine.py" <<'PY'
"""
Repository Intelligence Engine.

Coordinates scanning and future enrichment.
"""

from __future__ import annotations

from .scanner import IntelligenceScanner
from .models import ProjectInventory


class IntelligenceEngine:

    def __init__(self) -> None:
        self._scanner = IntelligenceScanner()

    def build_inventory(self, repository: object) -> ProjectInventory:
        return self._scanner.scan(repository)
PY

# --------------------------------------------------------------------
# inventory.py
# --------------------------------------------------------------------

cat > "$APP_DIR/inventory.py" <<'PY'
"""
Inventory helpers.

Future sprints populate lookup tables,
indexes and semantic relationships.
"""

from __future__ import annotations

from .models import ProjectInventory


def create_inventory() -> ProjectInventory:
    return ProjectInventory()
PY

echo
echo "Sprint 11.02.01 complete."
echo
echo "Created:"
echo "  backend/app/intelligence/scanner.py"
echo "  backend/app/intelligence/engine.py"
echo "  backend/app/intelligence/inventory.py"