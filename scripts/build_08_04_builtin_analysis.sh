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
echo " Sprint 08.04 - Repository Health Analysis"
echo "=========================================="

mkdir -p backend/app/repository/analysis

###############################################################################
# analysis/health.py
###############################################################################

cat > backend/app/repository/analysis/health.py <<'PY'
from __future__ import annotations

from .models import (
    AnalysisIssue,
    AnalysisPass,
    AnalysisResult,
)


class RepositoryHealthAnalysis(AnalysisPass):
    """
    Performs basic repository consistency checks.
    """

    @property
    def name(self) -> str:
        return "repository_health"

    def run(self, repository) -> AnalysisResult:
        result = AnalysisResult(name=self.name)

        if repository.file_count == 0:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message="Repository contains no loaded files.",
                )
            )

        if repository.parsed_count != repository.file_count:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message="Parsed file count does not match loaded file count.",
                )
            )

        if repository.symbol_count == 0:
            result.issues.append(
                AnalysisIssue(
                    severity="warning",
                    message="No symbols have been indexed.",
                )
            )

        result.metadata.update(
            {
                "files": repository.file_count,
                "parsed": repository.parsed_count,
                "symbols": repository.symbol_count,
                "imports": len(repository.import_graph),
                "calls": len(repository.call_graph),
            }
        )

        return result
PY

###############################################################################
# analysis/__init__.py
###############################################################################

python - <<'PY'
from pathlib import Path

path = Path("backend/app/repository/analysis/__init__.py")
text = path.read_text()

if "RepositoryHealthAnalysis" not in text:
    text = "from .health import RepositoryHealthAnalysis\n" + text

    text = text.replace(
        '__all__ = [',
        '__all__ = [\n    "RepositoryHealthAnalysis",'
    )

path.write_text(text)
PY

echo
echo "=========================================="
echo " Sprint 08.04 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_08_05_analysis_query_api.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"