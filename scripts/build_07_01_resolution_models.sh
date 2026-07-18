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
echo " Sprint 07.01 - Resolution Models"
echo "=========================================="

mkdir -p backend/app/repository/resolution

###############################################################################
# resolution/models.py
###############################################################################

cat > backend/app/repository/resolution/models.py <<'PY'
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
PY

###############################################################################
# resolution/__init__.py
###############################################################################

cat > backend/app/repository/resolution/__init__.py <<'PY'
from .models import (
    ResolutionContext,
    ResolutionResult,
    ResolvedSymbol,
)

__all__ = [
    "ResolvedSymbol",
    "ResolutionContext",
    "ResolutionResult",
]
PY

echo
echo "=========================================="
echo " Sprint 07.01 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_07_02_scope_tracker.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"