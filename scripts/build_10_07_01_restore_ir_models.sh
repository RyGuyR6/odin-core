#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

if [[ ! -d backend ]]; then
    echo "ERROR: backend directory not found."
    exit 1
fi

IR_DIR="backend/app/repository/ir"

mkdir -p "$IR_DIR"

cat > "$IR_DIR/models.py" <<'PY'
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
PY

echo
echo "✔ Restored backend/app/repository/ir/models.py"