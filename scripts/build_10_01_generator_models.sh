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
echo " Odin Developer Infrastructure"
echo " Sprint 10.01 - Generator Models"
echo "=========================================="

mkdir -p backend/app/devtools/generators

###############################################################################
# models.py
###############################################################################

cat > backend/app/devtools/generators/models.py <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class GeneratedFile:
    """
    Represents a generated source file.
    """
    path: Path
    content: str


@dataclass(slots=True)
class GenerationResult:
    """
    Result of a generation operation.
    """
    files: list[GeneratedFile] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
PY

###############################################################################
# __init__.py
###############################################################################

cat > backend/app/devtools/generators/__init__.py <<'PY'
from .models import (
    GeneratedFile,
    GenerationResult,
)

__all__ = [
    "GeneratedFile",
    "GenerationResult",
]
PY

echo
echo "=========================================="
echo " Sprint 10.01 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_10_02_template_engine.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app"