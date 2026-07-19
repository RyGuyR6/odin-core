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
echo " Sprint 09.04 - IR Query Engine"
echo "=========================================="

mkdir -p backend/app/repository/ir

###############################################################################
# ir/query.py
###############################################################################

cat > backend/app/repository/ir/query.py <<'PY'
from __future__ import annotations


class IRQuery:
    """
    High-level query interface for the Odin Intermediate Representation.
    """

    def __init__(self, modules):
        self._modules = modules

    def modules(self):
        return list(self._modules)

    def classes(self):
        return [
            cls
            for module in self._modules
            for cls in module.classes
        ]

    def functions(self):
        functions = []

        for module in self._modules:
            functions.extend(module.functions)

            for cls in module.classes:
                functions.extend(cls.methods)

        return functions

    def find_class(self, qualified_name: str):
        for cls in self.classes():
            if cls.qualified_name == qualified_name:
                return cls
        return None

    def find_function(self, qualified_name: str):
        for fn in self.functions():
            if fn.qualified_name == qualified_name:
                return fn
        return None
PY

###############################################################################
# ir/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/ir/__init__.py")
text = path.read_text()

if "IRQuery" not in text:
    text = "from .query import IRQuery\n" + text

    text = text.replace(
        "__all__ = [",
        '__all__ = [\n    "IRQuery",'
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

###############################################################################
# Import
###############################################################################

import_line = "from app.repository.ir import IRQuery"

if import_line not in text:
    marker = "from app.repository.ir import IRBuilder"

    if marker not in text:
        raise SystemExit("Unable to locate IRBuilder import.")

    text = text.replace(
        marker,
        marker + "\n" + import_line,
    )

###############################################################################
# Constructor
###############################################################################

old = """self.ir_builder = IRBuilder()
        self.ir_modules = []"""

new = """self.ir_builder = IRBuilder()
        self.ir_modules = []
        self.ir_query = IRQuery(self.ir_modules)"""

if "self.ir_query = IRQuery" not in text:
    if old not in text:
        raise SystemExit("Unable to locate IR initialization.")
    text = text.replace(old, new)

###############################################################################
# build_ir refresh
###############################################################################

old = """        return self.ir_modules"""

new = """        self.ir_query = IRQuery(self.ir_modules)
        return self.ir_modules"""

if old in text:
    text = text.replace(old, new, 1)

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 09.04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_09_05_ir_analysis_adapter.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"