"""
Canonical GitHub integration.

Importing this package never creates a client or requires credentials.
"""

from __future__ import annotations

import threading
from typing import Any

from app.services.github.client import github_is_configured
from app.services.github.provider import GitHubProvider

_provider: GitHubProvider | None = None
_lock = threading.RLock()


def get_github_provider() -> GitHubProvider:
    global _provider
    with _lock:
        if _provider is None:
            _provider = GitHubProvider()
        return _provider


def reset_github_provider() -> None:
    global _provider
    with _lock:
        _provider = None


class LazyGitHubProvider:
    @property
    def configured(self) -> bool:
        return github_is_configured()

    @property
    def initialized(self) -> bool:
        return _provider is not None

    def resolve(self) -> GitHubProvider:
        return get_github_provider()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.resolve(), name)

    def __repr__(self) -> str:
        state = "initialized" if self.initialized else "lazy"
        configured = "configured" if self.configured else "unconfigured"
        return f"<LazyGitHubProvider {state} {configured}>"


github = LazyGitHubProvider()

__all__ = [
    "GitHubProvider",
    "LazyGitHubProvider",
    "get_github_provider",
    "reset_github_provider",
    "github",
]
