import base64

import pytest

from app.services.github.branches import BranchService
from app.services.github.contents import ContentService
from app.services.github.safety import GitHubWriteSafetyError, normalize_repo_path


class FakeClient:
    def __init__(self):
        self.calls = []

    def get(self, endpoint):
        self.calls.append(("GET", endpoint, None))
        return {"endpoint": endpoint}

    def post(self, endpoint, payload):
        self.calls.append(("POST", endpoint, payload))
        return {"ok": True}

    def put(self, endpoint, payload):
        self.calls.append(("PUT", endpoint, payload))
        return {"ok": True}

    def delete(self, endpoint, payload=None):
        self.calls.append(("DELETE", endpoint, payload))
        return {"ok": True}


def test_path_traversal_is_rejected():
    with pytest.raises(GitHubWriteSafetyError):
        normalize_repo_path("../secrets.txt")


def test_write_defaults_to_dry_run():
    client = FakeClient()
    result = ContentService(client).write_file(
        "owner", "repo", "README.md", "hello",
        branch="feature/safe", message="Update README",
    )
    assert result["executed"] is False
    assert result["plan"]["operation"] == "create"
    assert client.calls == []


def test_live_write_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        ContentService(FakeClient()).write_file(
            "owner", "repo", "README.md", "hello",
            branch="feature/safe", message="Update README", dry_run=False,
        )


def test_confirmed_write_encodes_content():
    client = FakeClient()
    result = ContentService(client).write_file(
        "owner", "repo", "README.md", "hello",
        branch="feature/safe", message="Update README",
        confirmed=True, dry_run=False,
    )
    assert result["executed"] is True
    method, endpoint, payload = client.calls[0]
    assert method == "PUT"
    assert endpoint.endswith("/contents/README.md")
    assert base64.b64decode(payload["content"]).decode() == "hello"


def test_delete_requires_confirmation():
    with pytest.raises(GitHubWriteSafetyError):
        ContentService(FakeClient()).delete_file(
            "owner", "repo", "README.md",
            branch="feature/safe", message="Delete README",
            sha="abcdef1", dry_run=False,
        )


def test_protected_branch_deletion_is_blocked():
    with pytest.raises(GitHubWriteSafetyError):
        BranchService(FakeClient()).delete_branch(
            "owner", "repo", "main", confirmed=True
        )
