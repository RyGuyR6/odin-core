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
echo " Sprint 09.02 - IR Builder"
echo "=========================================="

mkdir -p backend/app/repository/ir

###############################################################################
# ir/builder.py
###############################################################################

cat > backend/app/repository/ir/builder.py <<'PY'
from __future__ import annotations

import ast
from pathlib import Path

from .models import (
    IRClass,
    IRFunction,
    IRModule,
)


class IRBuilder:
    """
    Builds Odin IR from parsed Python ASTs.
    """

    def build_module(
        self,
        path: Path,
        tree: ast.AST,
    ) -> IRModule:

        module = IRModule(
            name=path.stem,
            path=path,
        )

        for node in tree.body:

            if isinstance(node, ast.FunctionDef):
                module.functions.append(
                    IRFunction(
                        name=node.name,
                        qualified_name=node.name,
                        line=node.lineno,
                    )
                )

            elif isinstance(node, ast.ClassDef):

                ir_class = IRClass(
                    name=node.name,
                    qualified_name=node.name,
                    line=node.lineno,
                )

                for child in node.body:
                    if isinstance(child, ast.FunctionDef):
                        ir_class.methods.append(
                            IRFunction(
                                name=child.name,
                                qualified_name=f"{node.name}.{child.name}",
                                line=child.lineno,
                            )
                        )

                module.classes.append(ir_class)

        return module
PY

###############################################################################
# ir/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/ir/__init__.py")
text = path.read_text()

if "IRBuilder" not in text:
    text = "from .builder import IRBuilder\n" + text

    text = text.replace(
        "__all__ = [",
        '__all__ = [\n    "IRBuilder",'
    )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 09.02 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_09_03_repository_ir_integration.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"