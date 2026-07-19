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
echo " Sprint 09.05 - IR Analysis Adapter"
echo "=========================================="

mkdir -p backend/app/repository/ir

###############################################################################
# ir/analysis.py
###############################################################################

cat > backend/app/repository/ir/analysis.py <<'PY'
from __future__ import annotations


class IRAnalysisAdapter:
    """
    Executes analysis passes using the repository's IR.

    This adapter provides a stable integration point between the
    Repository IR and the Analysis Framework.
    """

    def __init__(self, repository):
        self._repository = repository

    @property
    def modules(self):
        return self._repository.ir

    def run(self):
        """
        Ensure the IR is available, then execute the analysis pipeline.
        """
        if not self._repository.ir:
            self._repository.build_ir()

        return self._repository.analysis.run(self._repository)
PY

###############################################################################
# ir/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/ir/__init__.py")

if path.exists():
    text = path.read_text()

    if "IRAnalysisAdapter" not in text:
        text = "from .analysis import IRAnalysisAdapter\n" + text

        if "__all__" in text:
            text = text.replace(
                "__all__ = [",
                '__all__ = [\n    "IRAnalysisAdapter",'
            )

        path.write_text(text)
else:
    raise SystemExit("backend/app/repository/ir/__init__.py not found.")
PY

###############################################################################
# repository.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/repository.py")
text = path.read_text()

import_line = "from app.repository.ir import IRAnalysisAdapter"

if import_line not in text:
    marker = "from app.repository.ir import IRQuery"

    if marker not in text:
        raise SystemExit("Unable to locate IRQuery import.")

    text = text.replace(marker, marker + "\n" + import_line)

old = """self.ir_query = IRQuery(self.ir_modules)"""

new = """self.ir_query = IRQuery(self.ir_modules)
        self.ir_analysis = IRAnalysisAdapter(self)"""

if "self.ir_analysis = IRAnalysisAdapter(self)" not in text:
    if old not in text:
        raise SystemExit("Unable to locate IRQuery initialization.")
    text = text.replace(old, new)

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 09.05 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_09_06_ir_tests.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"