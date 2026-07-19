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
    class EmptyGraph:
        def __len__(self):
            return 0


    class RepositoryStub:
        file_count = 1
        parsed_count = 1
        symbol_count = 1

        import_graph = EmptyGraph()
        call_graph = EmptyGraph()

    analysis = RepositoryHealthAnalysis()

    result = analysis.run(RepositoryStub())

    assert result.passed
