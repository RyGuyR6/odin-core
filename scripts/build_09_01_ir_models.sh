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
echo " Odin IR Framework"
echo " Sprint 09.01 - IR Models"
echo "=========================================="

mkdir -p backend/app/repository/ir

###############################################################################
# ir/models.py
###############################################################################

cat > backend/app/repository/ir/models.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class IRCall:
    caller: str
    callee: str


@dataclass(slots=True)
class IRFunction:
    name: str
    qualified_name: str
    line: int
    calls: list[IRCall] = field(default_factory=list)


@dataclass(slots=True)
class IRClass:
    name: str
    qualified_name: str
    line: int
    methods: list[IRFunction] = field(default_factory=list)


@dataclass(slots=True)
class IRModule:
    name: str
    path: Path
    classes: list[IRClass] = field(default_factory=list)
    functions: list[IRFunction] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
PY

###############################################################################
# ir/__init__.py
###############################################################################

cat > backend/app/repository/ir/__init__.py <<'PY'
from .models import (
    IRCall,
    IRClass,
    IRFunction,
    IRModule,
)

__all__ = [
    "IRCall",
    "IRClass",
    "IRFunction",
    "IRModule",
]
PY

echo
echo "=========================================="
echo " Sprint 09.01 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_09_02_ir_builder.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"