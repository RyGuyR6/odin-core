import pytest

from app.services.github.pull_requests import PullRequestService
from app.services.github.safety import GitHubWriteSafetyError


class FakeClient:
    def __init__(self, *, draft=False, mergeable=True, status="success", reviews=None):
        self.calls = []
        self.draft = draft
        self.mergeable = mergeable
        self.status = status
        self.reviews = reviews or []

    def get(self, endpoint):
        self.calls.append(("GET", endpoint, None))
        if endpoint.endswith("/reviews"):
            return self.reviews
        if endpoint.endswith("/status"):
            return {"state": self.status}
        if "/pulls/" in endpoint and not endpoint.endswith("/files"):
            return {
                "draft": self.draft,
                "mergeable": self.mergeable,
                "head": {"sha": "abc1234"},
            }
        if endpoint.endswith("/files"):
            return [{"filename": "README.md"}]
        raise AssertionError(endpoint)

    def post(self, endpoint, payload):
        self.calls.append(("POST", endpoint, payload))
        return {"number": 12}

    def put(self, endpoint, payload):
        self.calls.append(("PUT", endpoint, payload))
        return {"merged": True}


def approved_review():
    return {"user": {"login": "reviewer"}, "state": "APPROVED"}


def test_pr_create_defaults_to_dry_run():
    client = FakeClient()
    result = PullRequestService(client).create_pull_request(
        "owner", "repo", "Title", "feature/test", "main"
    )
    assert result["executed"] is False
    assert result["plan"]["draft"] is False
    assert client.calls == []


def test_pr_create_live_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        PullRequestService(FakeClient()).create_pull_request(
            "owner", "repo", "Title", "feature/test", "main", dry_run=False
        )


def test_review_gates_pass_with_approval_and_successful_checks():
    service = PullRequestService(FakeClient(reviews=[approved_review()]))
    result = service.evaluate_review_gates("owner", "repo", 12)
    assert result.passed is True
    assert result.approvals == 1
    assert result.required_checks_passed is True


def test_review_gates_fail_for_draft():
    service = PullRequestService(
        FakeClient(draft=True, reviews=[approved_review()])
    )
    result = service.evaluate_review_gates("owner", "repo", 12)
    assert result.passed is False
    assert "pull request is still a draft" in result.reasons


def test_merge_dry_run_returns_gate_preview():
    service = PullRequestService(FakeClient(reviews=[approved_review()]))
    result = service.merge_pull_request("owner", "repo", 12)
    assert result["executed"] is False
    assert result["plan"]["gates"]["passed"] is True


def test_live_merge_fails_when_checks_fail():
    service = PullRequestService(
        FakeClient(status="failure", reviews=[approved_review()])
    )
    with pytest.raises(GitHubWriteSafetyError):
        service.merge_pull_request(
            "owner", "repo", 12, confirmed=True, dry_run=False
        )


def test_confirmed_merge_uses_selected_method():
    client = FakeClient(reviews=[approved_review()])
    result = PullRequestService(client).merge_pull_request(
        "owner",
        "repo",
        12,
        method="rebase",
        confirmed=True,
        dry_run=False,
    )
    assert result["executed"] is True
    method, endpoint, payload = client.calls[-1]
    assert method == "PUT"
    assert endpoint.endswith("/pulls/12/merge")
    assert payload["merge_method"] == "rebase"
