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
echo " Sprint 09.03 - Repository IR Integration"
echo "=========================================="

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

import_line = "from app.repository.ir import IRBuilder"

if import_line not in text:
    marker = "from app.repository.analysis import AnalysisPipeline"

    if marker not in text:
        raise SystemExit("Unable to locate AnalysisPipeline import.")

    text = text.replace(
        marker,
        marker + "\n" + import_line,
    )

###############################################################################
# Constructor
###############################################################################

constructor_marker = "self.analysis = AnalysisPipeline()"

replacement = """self.analysis = AnalysisPipeline()
        self.ir_builder = IRBuilder()
        self.ir_modules = []"""

if "self.ir_builder = IRBuilder()" not in text:

    if constructor_marker not in text:
        raise SystemExit("Unable to locate AnalysisPipeline initialization.")

    text = text.replace(
        constructor_marker,
        replacement,
    )

###############################################################################
# build_ir()
###############################################################################

method = '''

    def build_ir(self):
        """
        Build IR for every parsed module.
        """
        self.ir_modules = []

        for path, tree in self._parsed.items():
            self.ir_modules.append(
                self.ir_builder.build_module(
                    path=path,
                    tree=tree,
                )
            )

        return self.ir_modules

'''

if "def build_ir(" not in text:

    marker = "    def analyze(self):"

    if marker not in text:
        raise SystemExit("Unable to locate analyze() method.")

    text = text.replace(
        marker,
        method + marker,
    )

###############################################################################
# Property
###############################################################################

property_block = '''

    @property
    def ir(self):
        return self.ir_modules

'''

if "@property\n    def ir(" not in text:

    marker = "    @property\n    def file_count"

    if marker not in text:
        raise SystemExit("Unable to locate file_count property.")

    text = text.replace(
        marker,
        property_block + marker,
    )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 09.03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_09_04_ir_query_engine.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"