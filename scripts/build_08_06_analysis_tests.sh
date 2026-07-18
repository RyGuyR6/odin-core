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
echo " Sprint 08.06 - Analysis Tests"
echo "=========================================="

mkdir -p backend/tests/repository

###############################################################################
# test_analysis.py
###############################################################################

cat > backend/tests/repository/test_analysis.py <<'PY'
from app.repository.analysis import (
    AnalysisIssue,
    AnalysisPass,
    AnalysisPipeline,
    AnalysisResult,
    RepositoryHealthAnalysis,
)


class DummyAnalysis(AnalysisPass):

    @property
    def name(self) -> str:
        return "dummy"

    def run(self, repository):
        return AnalysisResult(name=self.name)


def test_pipeline_register():
    pipeline = AnalysisPipeline()

    pipeline.register(DummyAnalysis())

    assert len(pipeline) == 1


def test_pipeline_run():
    pipeline = AnalysisPipeline()

    pipeline.register(DummyAnalysis())

    results = pipeline.run(None)

    assert len(results) == 1
    assert results.by_name("dummy") is not None


def test_analysis_results_summary():
    pipeline = AnalysisPipeline()

    pipeline.register(DummyAnalysis())

    results = pipeline.run(None)

    summary = results.summary()

    assert summary["passes"] == 1
    assert summary["passed"] == 1
    assert summary["failed"] == 0


def test_analysis_results_warnings():
    result = AnalysisResult(
        name="warnings",
        issues=[
            AnalysisIssue(
                severity="warning",
                message="warning",
            )
        ],
    )

    pipeline = AnalysisPipeline()
    wrapped = pipeline.run(None)

    wrapped._results.append(result)

    assert len(wrapped.warnings()) == 1


def test_repository_health_analysis():
    class RepositoryStub:
        file_count = 1
        parsed_count = 1
        symbol_count = 1

        class import_graph:
            def __len__(self):
                return 0

        class call_graph:
            def __len__(self):
                return 0

    analysis = RepositoryHealthAnalysis()

    result = analysis.run(RepositoryStub())

    assert result.passed
PY

echo
echo "=========================================="
echo " Sprint 08.06 Complete"
echo "=========================================="

echo
echo "Next:"
echo "./scripts/verify_repository.sh"

echo
echo "Verify:"
echo "cd backend"
echo "pytest tests/repository -v"