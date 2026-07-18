#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

echo "=========================================="
echo " Odin Semantic Intelligence"
echo " Sprint 07.05 - Resolution Engine"
echo "=========================================="

mkdir -p backend/app/repository/resolution

###############################################################################
# resolution/engine.py
###############################################################################

cat > backend/app/repository/resolution/engine.py <<'PY'
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
PY

###############################################################################
# resolution/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/resolution/__init__.py")
text = path.read_text()

if "ResolutionEngine" not in text:
    text = "from .engine import ResolutionEngine\n" + text
    text = text.replace(
        '__all__ = [',
        '__all__ = [\n    "ResolutionEngine",'
    )

path.write_text(text)
PY

###############################################################################
# repository.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/repository.py")
text = path.read_text()

if "ResolutionEngine" not in text:
    text = text.replace(
        """from app.repository.resolution import (
    ResolutionContext,
    SymbolResolver,
)""",
        """from app.repository.resolution import (
    ResolutionContext,
    ResolutionEngine,
    SymbolResolver,
)"""
    )

old = """        self.resolver = SymbolResolver(
            self._index,
        )"""

new = """        self.resolver = SymbolResolver(
            self._index,
        )

        self.resolution_engine = ResolutionEngine(
            self.resolver,
        )"""

if "self.resolution_engine" not in text:
    text = text.replace(old, new)

old = """        return self.resolver.resolve(
            name,
            context,
        )"""

new = """        return self.resolution_engine.resolve(
            name,
            context,
        )"""

text = text.replace(old, new)

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 07.05 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_07_06_resolution_tests.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"