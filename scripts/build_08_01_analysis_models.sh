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
echo " Sprint 08.01 - Analysis Models"
echo "=========================================="

mkdir -p backend/app/repository/analysis

###############################################################################
# analysis/models.py
###############################################################################

cat > backend/app/repository/analysis/models.py <<'PY'
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnalysisIssue:
    """
    A single issue, finding, or observation produced by an analysis pass.
    """

    severity: str
    message: str
    symbol: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AnalysisResult:
    """
    Result produced by a single analysis pass.
    """

    name: str
    issues: list[AnalysisIssue] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return len(self.issues) == 0


class AnalysisPass(ABC):
    """
    Base class for all repository analysis passes.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def run(self, repository: Any) -> AnalysisResult:
        """
        Execute the analysis pass against a repository.
        """
        raise NotImplementedError
PY

###############################################################################
# analysis/__init__.py
###############################################################################

cat > backend/app/repository/analysis/__init__.py <<'PY'
from .models import (
    AnalysisIssue,
    AnalysisPass,
    AnalysisResult,
)

__all__ = [
    "AnalysisIssue",
    "AnalysisPass",
    "AnalysisResult",
]
PY

echo
echo "=========================================="
echo " Sprint 08.01 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/build_08_02_analysis_pipeline.sh"

echo
echo "Verify:"
echo "cd backend"
echo "python -m compileall app/repository"