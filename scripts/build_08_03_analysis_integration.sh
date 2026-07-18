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
echo " Odin Analysis Framework"
echo " Sprint 08.03 - Repository Analysis Integration"
echo "=========================================="

###############################################################################
# repository.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/repository.py")
text = path.read_text()

#
# Add AnalysisPipeline import
#

analysis_import = "from app.repository.analysis import AnalysisPipeline"

if analysis_import not in text:
    marker = "from app.repository.query import RepositoryQuery"
    if marker in text:
        text = text.replace(
            marker,
            marker + "\n" + analysis_import,
        )
    else:
        raise SystemExit("Could not locate RepositoryQuery import.")

#
# Create pipeline during initialization
#

constructor_marker = """        self.query = RepositoryQuery(
            self._index,
            self.import_graph,
            self.call_graph,
        )
"""

pipeline_block = constructor_marker + """
        self.analysis = AnalysisPipeline()
"""

if "self.analysis = AnalysisPipeline()" not in text:
    if constructor_marker in text:
        text = text.replace(constructor_marker, pipeline_block)
    else:
        raise SystemExit("Could not locate RepositoryQuery initialization.")

#
# Add Repository.analyze()
#

marker = """    @property
    def file_count(self) -> int:
"""

method = """
    def analyze(self):
        \"\"\"
        Execute all registered analysis passes.
        \"\"\"
        return self.analysis.run(self)

"""

if "def analyze(" not in text:
    if marker in text:
        text = text.replace(marker, method + marker)
    else:
        raise SystemExit("Could not locate insertion point for analyze().")

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 08.03 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_08_04_builtin_analysis.sh"

echo
echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"