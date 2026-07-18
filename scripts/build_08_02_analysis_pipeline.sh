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
echo " Sprint 08.02 - Analysis Pipeline"
echo "=========================================="

mkdir -p backend/app/repository/analysis

###############################################################################
# analysis/pipeline.py
###############################################################################

cat > backend/app/repository/analysis/pipeline.py <<'PY'
from __future__ import annotations

from .models import AnalysisPass, AnalysisResult


class AnalysisPipeline:
    """
    Executes registered analysis passes against a repository.
    """

    def __init__(self) -> None:
        self._passes: list[AnalysisPass] = []

    def register(self, analysis_pass: AnalysisPass) -> None:
        """
        Register an analysis pass.
        """
        self._passes.append(analysis_pass)

    def unregister(self, name: str) -> bool:
        """
        Remove a registered analysis pass by name.
        """
        before = len(self._passes)
        self._passes = [
            p for p in self._passes
            if p.name != name
        ]
        return len(self._passes) != before

    def clear(self) -> None:
        """
        Remove all registered analysis passes.
        """
        self._passes.clear()

    def run(self, repository) -> list[AnalysisResult]:
        """
        Execute all registered analysis passes.
        """
        results: list[AnalysisResult] = []

        for analysis_pass in self._passes:
            results.append(
                analysis_pass.run(repository)
            )

        return results

    @property
    def passes(self) -> tuple[AnalysisPass, ...]:
        """
        Read-only view of registered passes.
        """
        return tuple(self._passes)

    def __len__(self) -> int:
        return len(self._passes)
PY

###############################################################################
# analysis/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/analysis/__init__.py")
text = path.read_text()

if "AnalysisPipeline" not in text:
    text = "from .pipeline import AnalysisPipeline\n" + text

    text = text.replace(
        '__all__ = [',
        '__all__ = [\n    "AnalysisPipeline",'
    )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 08.02 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_08_03_analysis_integration.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"