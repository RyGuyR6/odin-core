#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$PROJECT_ROOT"

[[ -d backend ]] || { echo "backend directory missing"; exit 1; }

INTEL="backend/app/intelligence"
TESTS="backend/tests/intelligence"

mkdir -pv "$INTEL"
mkdir -pv "$TESTS"

###############################################################################
# cross_reference.py
###############################################################################

cat > "$INTEL/cross_reference.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class SymbolReference:
    name: str
    module: str
    line: int
    qualified_name: str = ""


@dataclass(slots=True)
class CrossReferenceIndex:
    definitions: dict[str, SymbolReference] = field(default_factory=dict)
    references: dict[str, list[SymbolReference]] = field(default_factory=dict)

    def add_definition(self, symbol: SymbolReference) -> None:
        self.definitions[symbol.name] = symbol

    def add_reference(self, symbol: SymbolReference) -> None:
        self.references.setdefault(symbol.name, []).append(symbol)

    def find_definition(self, name: str) -> SymbolReference | None:
        return self.definitions.get(name)

    def find_references(self, name: str) -> list[SymbolReference]:
        return list(self.references.get(name, []))
PY

###############################################################################
# Update __init__.py
###############################################################################

python3 <<'PY'
from pathlib import Path

p = Path("backend/app/intelligence/__init__.py")

text = p.read_text()

if "CrossReferenceIndex" not in text:
    text += """

from .cross_reference import CrossReferenceIndex, SymbolReference
"""

if '"CrossReferenceIndex"' not in text:
    text = text.replace(
        "]",
        '    "CrossReferenceIndex",\n'
        '    "SymbolReference",\n]'
    )

p.write_text(text)
PY

###############################################################################
# Tests
###############################################################################

cat > "$TESTS/test_cross_reference.py" <<'PY'
from app.intelligence.cross_reference import (
    CrossReferenceIndex,
    SymbolReference,
)


def test_add_definition():
    index = CrossReferenceIndex()

    symbol = SymbolReference(
        name="Repository",
        qualified_name="repository.Repository",
        module="repository.py",
        line=10,
    )

    index.add_definition(symbol)

    assert index.find_definition("Repository") == symbol


def test_add_reference():
    index = CrossReferenceIndex()

    symbol = SymbolReference(
        name="Repository",
        qualified_name="repository.Repository",
        module="repository.py",
        line=20,
    )

    index.add_reference(symbol)

    refs = index.find_references("Repository")

    assert len(refs) == 1
    assert refs[0] == symbol
PY

###############################################################################
# HARD VALIDATION
###############################################################################

echo
echo "========== VALIDATION =========="

[[ -f "$INTEL/cross_reference.py" ]] || { echo "cross_reference.py missing"; exit 1; }
[[ -f "$TESTS/test_cross_reference.py" ]] || { echo "test_cross_reference.py missing"; exit 1; }

python3 -m py_compile "$INTEL/cross_reference.py"

echo
echo "Created Intelligence files:"
find "$INTEL" -maxdepth 1 -type f | sort

echo
echo "Created Intelligence tests:"
find "$TESTS" -maxdepth 1 -type f | sort

echo
echo "SUCCESS"