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
echo " Sprint 08.05 - Analysis Results API"
echo "=========================================="

mkdir -p backend/app/repository/analysis

###############################################################################
# analysis/results.py
###############################################################################

cat > backend/app/repository/analysis/results.py <<'PY'
from __future__ import annotations

from collections import Counter

from .models import AnalysisResult


class AnalysisResults:
    """
    Query API over a collection of AnalysisResult objects.
    """

    def __init__(self, results: list[AnalysisResult]):
        self._results = list(results)

    def all(self) -> list[AnalysisResult]:
        return list(self._results)

    def by_name(self, name: str) -> AnalysisResult | None:
        for result in self._results:
            if result.name == name:
                return result
        return None

    def passed(self) -> list[AnalysisResult]:
        return [r for r in self._results if r.passed]

    def failed(self) -> list[AnalysisResult]:
        return [r for r in self._results if not r.passed]

    def warnings(self):
        warnings = []

        for result in self._results:
            warnings.extend(
                issue
                for issue in result.issues
                if issue.severity.lower() == "warning"
            )

        return warnings

    def errors(self):
        errors = []

        for result in self._results:
            errors.extend(
                issue
                for issue in result.issues
                if issue.severity.lower() == "error"
            )

        return errors

    def summary(self) -> dict[str, int]:
        counter = Counter()

        counter["passes"] = len(self._results)
        counter["passed"] = len(self.passed())
        counter["failed"] = len(self.failed())
        counter["warnings"] = len(self.warnings())
        counter["errors"] = len(self.errors())

        return dict(counter)

    def __iter__(self):
        return iter(self._results)

    def __len__(self):
        return len(self._results)
PY

###############################################################################
# analysis/pipeline.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/analysis/pipeline.py")
text = path.read_text()

if "AnalysisResults" not in text:
    text = text.replace(
        "from .models import AnalysisPass, AnalysisResult",
        "from .models import AnalysisPass, AnalysisResult\nfrom .results import AnalysisResults"
    )

old = """        return results"""

new = """        return AnalysisResults(results)"""

if old not in text:
    raise SystemExit("Expected pipeline return statement not found.")

text = text.replace(old, new, 1)

path.write_text(text)
PY

###############################################################################
# analysis/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/analysis/__init__.py")
text = path.read_text()

if "AnalysisResults" not in text:
    text = "from .results import AnalysisResults\n" + text

    text = text.replace(
        '__all__ = [',
        '__all__ = [\n    "AnalysisResults",'
    )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 08.05 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_08_06_analysis_tests.sh"

echo
echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"