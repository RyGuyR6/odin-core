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
echo " Sprint 07.03 - Symbol Resolver"
echo "=========================================="

mkdir -p backend/app/repository/resolution

###############################################################################
# symbol_resolver.py
###############################################################################

cat > backend/app/repository/resolution/symbol_resolver.py <<'PY'
from __future__ import annotations

from app.repository.index import SymbolIndex
from app.repository.models import RepositorySymbol

from .models import (
    ResolutionContext,
    ResolutionResult,
    ResolvedSymbol,
)


class SymbolResolver:
    """
    Resolves symbol references against the repository symbol index.
    """

    def __init__(self, index: SymbolIndex):
        self.index = index

    def resolve(
        self,
        name: str,
        context: ResolutionContext,
    ) -> ResolutionResult:
        """
        Resolve a symbol using progressively broader lookups.
        """

        #
        # Fully-qualified lookup
        #

        symbol = self.index.find(name)

        if symbol is None and context.module:
            qualified = f"{context.module}.{name}"
            symbol = self.index.find(qualified)

        if symbol is None:
            for candidate in self.index.all():
                if candidate.name == name:
                    symbol = candidate
                    break

        if symbol is None:
            return ResolutionResult(
                resolved=False,
                reason=f"Unable to resolve '{name}'.",
            )

        return ResolutionResult(
            resolved=True,
            symbol=ResolvedSymbol(
                name=symbol.name,
                qualified_name=f"{symbol.module}.{symbol.name}",
                module=symbol.module,
                file=symbol.file,
                line=symbol.line,
                kind=symbol.kind,
            ),
        )
PY

###############################################################################
# __init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/resolution/__init__.py")
text = path.read_text()

if "SymbolResolver" not in text:
    text = "from .symbol_resolver import SymbolResolver\n" + text

    text = text.replace(
        '__all__ = [',
        '__all__ = [\n    "SymbolResolver",'
    )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 07.03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_07_04_repository_resolution.sh"

echo
echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"