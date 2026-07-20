import pytest

from app.services.github.workflows import WorkflowService, GitHubWriteSafetyError


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint):
        self.calls.append(("GET", endpoint, None))
        if endpoint.endswith("/actions/runs/44"):
            return {"id": 44, "status": "completed", "conclusion": "success"}
        if endpoint.endswith("/actions/runs/44/jobs"):
            return {
                "jobs": [
                    {"id": 1, "name": "test", "status": "completed", "conclusion": "success"},
                    {"id": 2, "name": "lint", "status": "completed", "conclusion": "success"},
                ]
            }
        if endpoint.endswith("/actions/runs/44/artifacts"):
            return {"artifacts": [{"id": 9, "name": "coverage"}]}
        return {"ok": True}

    def post(self, endpoint, payload):
        self.calls.append(("POST", endpoint, payload))
        return None


def test_dispatch_defaults_to_dry_run():
    client = FakeClient()
    result = WorkflowService(client).dispatch(
        "owner", "repo", "ci.yml", ref="main"
    )
    assert result["executed"] is False
    assert result["plan"]["workflow_id"] == "ci.yml"
    assert client.calls == []


def test_live_dispatch_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        WorkflowService(FakeClient()).dispatch(
            "owner", "repo", "ci.yml", ref="main", dry_run=False
        )


def test_confirmed_dispatch_calls_github():
    client = FakeClient()
    result = WorkflowService(client).dispatch(
        "owner",
        "repo",
        "ci.yml",
        ref="main",
        inputs={"suite": "all"},
        confirmed=True,
        dry_run=False,
    )
    assert result["executed"] is True
    method, endpoint, payload = client.calls[-1]
    assert method == "POST"
    assert endpoint.endswith("/workflows/ci.yml/dispatches")
    assert payload["inputs"]["suite"] == "all"


def test_rerun_failed_jobs_plan():
    result = WorkflowService(FakeClient()).rerun(
        "owner", "repo", 44, failed_jobs_only=True
    )
    assert result["plan"]["operation"] == "rerun-failed-jobs"
    assert result["executed"] is False


def test_overview_aggregates_jobs_and_artifacts():
    result = WorkflowService(FakeClient()).overview("owner", "repo", 44)
    assert result.passed is True
    assert result.jobs_total == 2
    assert result.jobs_completed == 2
    assert result.jobs_failed == 0
    assert result.artifacts_total == 1


def test_logs_endpoint_is_descriptive_and_non_mutating():
    result = WorkflowService(FakeClient()).get_job_logs_url(
        "owner", "repo", 77
    )
    assert result["job_id"] == 77
    assert result["download_endpoint"].endswith("/actions/jobs/77/logs")
