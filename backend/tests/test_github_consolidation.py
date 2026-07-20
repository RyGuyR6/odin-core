from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.errors import ServiceNotConfiguredError
from app.services.github import github, reset_github_provider
from app.services.github.client import GitHubClient
from app.services.github.provider import GitHubProvider
from app.services.github_service import GitHubService


@pytest.fixture(autouse=True)
def isolate_github_state(monkeypatch):
    # Pytest runs from backend/, where Pydantic intentionally discovers
    # backend/.env. An explicit empty variable masks that dotenv value.
    monkeypatch.setenv("ODIN_GITHUB_TOKEN", "")
    reset_github_provider()
    yield
    reset_github_provider()


def test_package_import_is_lazy_without_token():
    assert github.initialized is False
    provider = github.resolve()
    assert provider.configured is False
    assert provider.client._session is None


def test_client_raises_only_when_request_session_is_used():
    client = GitHubClient(token=None)
    assert client.configured is False
    with pytest.raises(ServiceNotConfiguredError):
        _ = client.session


def test_explicit_token_is_deterministic():
    client = GitHubClient(token="test-token")
    assert client.configured is True
    assert client.token == "test-token"
    assert client._session is None


def test_environment_changes_are_observed(monkeypatch):
    monkeypatch.setenv("ODIN_GITHUB_TOKEN", "runtime-token")
    configured = GitHubClient()
    assert configured.configured is True

    monkeypatch.setenv("ODIN_GITHUB_TOKEN", "")
    unconfigured = GitHubClient()
    assert unconfigured.configured is False


def test_legacy_facade_uses_canonical_client():
    service = GitHubService(token="test-token")
    assert isinstance(service.client, GitHubClient)
    assert service.configured is True
    assert service.client._session is None


def test_provider_builds_domain_services_without_network():
    provider = GitHubProvider(GitHubClient(token="test-token"))
    assert provider.configured is True
    assert provider.client._session is None
    assert provider.repositories.client is provider.client
    assert provider.branches.client is provider.client
    assert provider.commits.client is provider.client


def test_fastapi_openapi_without_token():
    from app.main import app
    schema = app.openapi()
    assert "/" in schema["paths"]
    assert "/github/repos" in schema["paths"]


def test_unconfigured_github_endpoint_returns_503():
    from app.main import app
    with TestClient(app) as client:
        response = client.get("/github/repos")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"].lower()
