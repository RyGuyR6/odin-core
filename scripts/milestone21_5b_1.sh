#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.5b.1"
ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
ROLLED_BACK=0
CHECKS=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ CHECKS=$((CHECKS+1)); printf '✅ %s\n' "$1"; }
fail(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  local code="${1:-1}"
  trap - ERR
  [[ "$ROLLED_BACK" == "1" ]] && exit "$code"
  ROLLED_BACK=1

  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone %s changes...\n' "$MILESTONE"
    while IFS= read -r -d '' saved; do
      rel="${saved#"$BACKUP_DIR/files/"}"
      if [[ "$saved" == *.missing ]]; then
        rm -rf "$ROOT/${rel%.missing}"
      else
        target="$ROOT/$rel"
        mkdir -p "$(dirname "$target")"
        cp -a "$saved" "$target"
      fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi

  printf '\n============================================================\n'
  printf '❌ MILESTONE %s FAILED\n' "$MILESTONE"
  printf 'Line: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for candidate in \
  "${ODIN_ROOT:-}" \
  "$(pwd)" \
  "/workspaces/odin-core" \
  "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$candidate" ]] || continue
  if [[ -d "$candidate/backend/app" ]]; then
    ROOT="$(cd "$candidate" && pwd)"
    BACKEND="$ROOT/backend"
    break
  fi
done
[[ -n "$ROOT" ]] || fail "Could not locate odin-core repository"

for candidate in \
  "$BACKEND/.venv/bin/python" \
  "$ROOT/.venv/bin/python" \
  "$(command -v python3 || true)" \
  "$(command -v python || true)"; do
  if [[ -n "$candidate" && -x "$candidate" ]]; then
    PYTHON_BIN="$candidate"
    break
  fi
done
[[ -n "$PYTHON_BIN" ]] || fail "Python interpreter not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE %s — DETERMINISTIC GITHUB CONFIGURATION\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"
printf 'Mode: cumulative replacement for failed 21.5b\n'

step "Checking expected source files"
required=(
  "$BACKEND/app/core/odin.py"
  "$BACKEND/app/core/settings.py"
  "$BACKEND/app/main.py"
  "$BACKEND/app/services/container.py"
  "$BACKEND/app/services/github_service.py"
  "$BACKEND/app/services/github/__init__.py"
  "$BACKEND/app/services/github/client.py"
  "$BACKEND/app/services/github/provider.py"
  "$BACKEND/app/services/github/repositories.py"
  "$BACKEND/app/api/github/repositories.py"
  "$BACKEND/app/api/github/branches.py"
  "$BACKEND/app/api/github/pull_requests.py"
)
for file in "${required[@]}"; do
  [[ -f "$file" ]] || fail "Required file missing: $file"
done
ok "Expected GitHub architecture detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_5b_1/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup(){
  local target="$1"
  local destination="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$destination")"
  if [[ -e "$target" ]]; then
    cp -a "$target" "$destination"
  else
    : > "${destination}.missing"
  fi
}

files=(
  "$BACKEND/app/core/settings.py"
  "$BACKEND/app/core/odin.py"
  "$BACKEND/app/core/dependencies.py"
  "$BACKEND/app/services/container.py"
  "$BACKEND/app/services/errors.py"
  "$BACKEND/app/services/lifecycle.py"
  "$BACKEND/app/services/github_service.py"
  "$BACKEND/app/services/github/__init__.py"
  "$BACKEND/app/services/github/client.py"
  "$BACKEND/app/services/github/provider.py"
  "$BACKEND/app/services/engineering/service.py"
  "$BACKEND/app/api/github/dependencies.py"
  "$BACKEND/app/api/github/errors.py"
  "$BACKEND/app/api/github/repositories.py"
  "$BACKEND/app/api/github/branches.py"
  "$BACKEND/app/api/github/pull_requests.py"
  "$BACKEND/tests/test_service_lifecycle.py"
  "$BACKEND/tests/test_github_consolidation.py"
  "$ROOT/.gitignore"
)
for file in "${files[@]}"; do backup "$file"; done
ok "Backup created at $BACKUP_DIR"

step "Installing lifecycle foundation"
cat > "$BACKEND/app/core/settings.py" <<'PY'
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Odin Core"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"

    ODIN_GITHUB_TOKEN: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
PY

cat > "$BACKEND/app/services/errors.py" <<'PY'
from __future__ import annotations


class ServiceError(RuntimeError):
    """Base exception for Odin service lifecycle failures."""


class ServiceNotRegisteredError(ServiceError, KeyError):
    """Raised when a requested service has not been registered."""


class ServiceNotConfiguredError(ServiceError):
    """Raised when an optional service is used without configuration."""


class ServiceInitializationError(ServiceError):
    """Raised when a lazy service factory fails."""
PY

cat > "$BACKEND/app/services/lifecycle.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable


class ServiceState(str, Enum):
    REGISTERED = "registered"
    UNCONFIGURED = "unconfigured"
    READY = "ready"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass(slots=True)
class ServiceDefinition:
    name: str
    factory: Callable[[], Any]
    required: bool = False
    configured: Callable[[], bool] | None = None

    def is_configured(self) -> bool:
        return True if self.configured is None else bool(self.configured())


@dataclass(slots=True)
class ServiceStatus:
    name: str
    required: bool
    configured: bool
    initialized: bool
    state: ServiceState
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "configured": self.configured,
            "initialized": self.initialized,
            "state": self.state.value,
            "error": self.error,
        }
PY

cat > "$BACKEND/app/services/container.py" <<'PY'
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from app.core.logger import logger
from app.services.errors import (
    ServiceInitializationError,
    ServiceNotConfiguredError,
    ServiceNotRegisteredError,
)
from app.services.lifecycle import ServiceDefinition, ServiceState, ServiceStatus


class ServiceContainer:
    """Backward-compatible container supporting lazy optional services."""

    def __init__(self):
        self.services: dict[str, Any] = {}
        self._definitions: dict[str, ServiceDefinition] = {}
        self._errors: dict[str, str] = {}
        self._states: dict[str, ServiceState] = {}
        self._lock = threading.RLock()

    def register(self, name: str, service: Any, *, replace: bool = True) -> Any:
        with self._lock:
            if not replace and (name in self.services or name in self._definitions):
                return self.services.get(name)
            self.services[name] = service
            self._definitions.pop(name, None)
            self._errors.pop(name, None)
            self._states[name] = ServiceState.READY
            logger.info(f"Registered service: {name}")
            return service

    def register_factory(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        required: bool = False,
        configured: Callable[[], bool] | None = None,
        replace: bool = False,
    ) -> None:
        with self._lock:
            if not replace and (name in self.services or name in self._definitions):
                return
            self.services.pop(name, None)
            definition = ServiceDefinition(name, factory, required, configured)
            self._definitions[name] = definition
            self._errors.pop(name, None)
            self._states[name] = (
                ServiceState.REGISTERED
                if definition.is_configured()
                else ServiceState.UNCONFIGURED
            )
            logger.info(f"Registered lazy service: {name}")

    def is_registered(self, name: str) -> bool:
        return name in self.services or name in self._definitions

    def is_initialized(self, name: str) -> bool:
        return name in self.services

    def get(self, name: str, default: Any = None) -> Any:
        with self._lock:
            if name in self.services:
                return self.services[name]

            definition = self._definitions.get(name)
            if definition is None:
                return default

            if not definition.is_configured():
                self._states[name] = ServiceState.UNCONFIGURED
                raise ServiceNotConfiguredError(f"Service '{name}' is not configured.")

            try:
                instance = definition.factory()
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self._errors[name] = message
                self._states[name] = ServiceState.ERROR
                raise ServiceInitializationError(
                    f"Service '{name}' failed to initialize: {message}"
                ) from exc

            self.services[name] = instance
            self._errors.pop(name, None)
            self._states[name] = ServiceState.READY
            logger.info(f"Initialized lazy service: {name}")
            return instance

    def require(self, name: str) -> Any:
        if not self.is_registered(name):
            raise ServiceNotRegisteredError(f"Service '{name}' is not registered.")
        service = self.get(name)
        if service is None:
            raise ServiceNotRegisteredError(f"Service '{name}' is not registered.")
        return service

    def reset(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self.services.clear()
                self._errors.clear()
                for service_name, definition in self._definitions.items():
                    self._states[service_name] = (
                        ServiceState.REGISTERED
                        if definition.is_configured()
                        else ServiceState.UNCONFIGURED
                    )
                return

            self.services.pop(name, None)
            self._errors.pop(name, None)
            if name in self._definitions:
                definition = self._definitions[name]
                self._states[name] = (
                    ServiceState.REGISTERED
                    if definition.is_configured()
                    else ServiceState.UNCONFIGURED
                )
            else:
                self._states.pop(name, None)

    def status(self, name: str) -> ServiceStatus:
        if name in self.services:
            definition = self._definitions.get(name)
            return ServiceStatus(
                name=name,
                required=definition.required if definition else True,
                configured=True,
                initialized=True,
                state=self._states.get(name, ServiceState.READY),
                error=self._errors.get(name),
            )

        definition = self._definitions.get(name)
        if definition is None:
            raise ServiceNotRegisteredError(f"Service '{name}' is not registered.")

        configured = definition.is_configured()
        state = self._states.get(
            name,
            ServiceState.REGISTERED if configured else ServiceState.UNCONFIGURED,
        )
        if not configured and state is not ServiceState.ERROR:
            state = ServiceState.UNCONFIGURED

        return ServiceStatus(
            name=name,
            required=definition.required,
            configured=configured,
            initialized=False,
            state=state,
            error=self._errors.get(name),
        )

    def health(self) -> dict[str, dict[str, Any]]:
        names = sorted(set(self.services) | set(self._definitions))
        return {name: self.status(name).as_dict() for name in names}

    def startup(self) -> None:
        for name, service in list(self.services.items()):
            hook = getattr(service, "startup", None)
            if callable(hook):
                hook()
                logger.info(f"Started service: {name}")

        for name, definition in list(self._definitions.items()):
            if not definition.required:
                continue
            service = self.require(name)
            hook = getattr(service, "startup", None)
            if callable(hook):
                hook()
                logger.info(f"Started required service: {name}")

    def shutdown(self) -> None:
        for name, service in reversed(list(self.services.items())):
            hook = getattr(service, "shutdown", None)
            if callable(hook):
                hook()
            self._states[name] = ServiceState.STOPPED


container = ServiceContainer()
PY
ok "Lifecycle foundation installed"

step "Adding dynamic GitHub configuration resolution"
cat > "$BACKEND/app/services/github/client.py" <<'PY'
from __future__ import annotations

import os
from typing import Any

import requests

from app.core.settings import settings
from app.services.errors import ServiceNotConfiguredError


def resolve_github_token(explicit_token: str | None = None) -> str | None:
    """
    Resolve credentials at object-construction time.

    Environment variables intentionally take precedence over the module-level
    Settings singleton. This keeps runtime behavior and tests deterministic
    when ODIN_GITHUB_TOKEN is changed after app.core.settings was imported.
    """
    if explicit_token is not None:
        token = explicit_token.strip()
        return token or None

    if "ODIN_GITHUB_TOKEN" in os.environ:
        token = os.environ.get("ODIN_GITHUB_TOKEN", "").strip()
        return token or None

    token = settings.ODIN_GITHUB_TOKEN
    return token.strip() if isinstance(token, str) and token.strip() else None


def github_is_configured() -> bool:
    return resolve_github_token() is not None


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
    ):
        self.token = resolve_github_token(token)
        self.timeout_seconds = timeout_seconds
        self._session = session

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def session(self) -> requests.Session:
        if not self.configured:
            raise ServiceNotConfiguredError(
                "GitHub is not configured. Set ODIN_GITHUB_TOKEN before "
                "calling GitHub operations."
            )

        if self._session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "Odin-Core",
                }
            )
            self._session = session
        return self._session

    def request(self, method: str, endpoint: str, **kwargs: Any):
        response = self.session.request(
            method,
            f"{self.BASE_URL}{endpoint}",
            timeout=kwargs.pop("timeout", self.timeout_seconds),
            **kwargs,
        )
        response.raise_for_status()
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get(self, endpoint: str):
        return self.request("GET", endpoint)

    def post(self, endpoint: str, payload):
        return self.request("POST", endpoint, json=payload)

    def patch(self, endpoint: str, payload):
        return self.request("PATCH", endpoint, json=payload)
PY
ok "GitHub token resolution is deterministic"

step "Installing lazy canonical GitHub provider"
cat > "$BACKEND/app/services/github/provider.py" <<'PY'
from __future__ import annotations

from app.services.github.branches import BranchService
from app.services.github.client import GitHubClient
from app.services.github.commits import CommitService
from app.services.github.contents import ContentService
from app.services.github.pull_requests import PullRequestService
from app.services.github.repositories import RepositoryService


class GitHubProvider:
    """Central access point for GitHub domain services."""

    def __init__(self, client: GitHubClient | None = None):
        self.client = client or GitHubClient()
        self.repositories = RepositoryService(self.client)
        self.branches = BranchService(self.client)
        self.commits = CommitService(self.client)
        self.contents = ContentService(self.client)
        self.pull_requests = PullRequestService(self.client)

    @property
    def configured(self) -> bool:
        return self.client.configured
PY

cat > "$BACKEND/app/services/github/__init__.py" <<'PY'
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
PY
ok "Lazy GitHub provider installed"

step "Installing compatibility facade"
cat > "$BACKEND/app/services/github_service.py" <<'PY'
"""Backward-compatible facade over the canonical GitHub client."""

from __future__ import annotations

from app.services.github.client import GitHubClient


class GitHubService:
    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        session=None,
    ):
        self.client = GitHubClient(
            token=token,
            timeout_seconds=timeout_seconds,
            session=session,
        )

    @property
    def token(self):
        return self.client.token

    @property
    def configured(self) -> bool:
        return self.client.configured

    @property
    def session(self):
        return self.client.session

    def _get(self, endpoint: str):
        return self.client.get(endpoint)

    def _post(self, endpoint: str, payload: dict):
        return self.client.post(endpoint, payload)

    def get_current_user(self):
        return self._get("/user")

    def list_repositories(self):
        return self._get("/user/repos")

    def get_repository(self, owner: str, repo: str):
        return self._get(f"/repos/{owner}/{repo}")

    def list_branches(self, owner: str, repo: str):
        return self._get(f"/repos/{owner}/{repo}/branches")

    def get_file(self, owner: str, repo: str, path: str):
        return self._get(f"/repos/{owner}/{repo}/contents/{path}")

    def get_branch(self, owner: str, repo: str, branch: str):
        return self._get(f"/repos/{owner}/{repo}/git/ref/heads/{branch}")

    def create_branch(
        self,
        owner: str,
        repo: str,
        new_branch: str,
        source_sha: str,
    ):
        return self._post(
            f"/repos/{owner}/{repo}/git/refs",
            {"ref": f"refs/heads/{new_branch}", "sha": source_sha},
        )
PY
ok "Legacy facade consolidated"

step "Registering GitHub with dynamic configuration checks"
cat > "$BACKEND/app/core/odin.py" <<'PY'
from __future__ import annotations

from app.core.logger import logger
from app.core.settings import settings
from app.services.container import container
from app.services.github import get_github_provider
from app.services.github.client import github_is_configured
from app.services.health_service import HealthService
from app.tools.loader import load_tools
from app.tools.registry import registry


class Odin:
    def __init__(self):
        self.name = settings.APP_NAME
        self.version = settings.VERSION
        self.environment = settings.ENVIRONMENT

        if not container.is_registered("health"):
            container.register("health", HealthService())

        if not container.is_registered("github"):
            container.register_factory(
                "github",
                get_github_provider,
                required=False,
                configured=github_is_configured,
            )

        load_tools()
        logger.info("Odin initialized.")

    def status(self):
        return {
            "name": self.name,
            "version": self.version,
            "environment": self.environment,
            "status": "online",
            "services": container.health(),
            "tools": registry.metadata(),
        }
PY
ok "Odin uses dynamic GitHub configuration"

step "Installing request-time FastAPI dependencies"
cat > "$BACKEND/app/api/github/dependencies.py" <<'PY'
from __future__ import annotations

from app.services.github import get_github_provider
from app.services.github.branches import BranchService
from app.services.github.pull_requests import PullRequestService
from app.services.github.repositories import RepositoryService


def get_repository_service() -> RepositoryService:
    return get_github_provider().repositories


def get_branch_service() -> BranchService:
    return get_github_provider().branches


def get_pull_request_service() -> PullRequestService:
    return get_github_provider().pull_requests
PY

cat > "$BACKEND/app/api/github/errors.py" <<'PY'
from __future__ import annotations

import requests
from fastapi import HTTPException

from app.services.errors import ServiceNotConfiguredError


def github_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ServiceNotConfiguredError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, requests.HTTPError):
        status = exc.response.status_code if exc.response is not None else 502
        return HTTPException(status_code=status, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))
PY

cat > "$BACKEND/app/api/github/repositories.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.github.dependencies import get_repository_service
from app.api.github.errors import github_http_error
from app.services.github.repositories import RepositoryService

router = APIRouter(prefix="/github", tags=["GitHub"])


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.get("/me")
def current_user(repos: RepositoryService = Depends(get_repository_service)):
    return run(repos.current_user)


@router.get("/repos")
def repositories(repos: RepositoryService = Depends(get_repository_service)):
    return run(repos.repositories)


@router.get("/repo/{owner}/{repo}")
def repository(
    owner: str,
    repo: str,
    repos: RepositoryService = Depends(get_repository_service),
):
    return run(lambda: repos.repository(owner, repo))


@router.get("/repo/{owner}/{repo}/branches")
def list_branches(
    owner: str,
    repo: str,
    repos: RepositoryService = Depends(get_repository_service),
):
    return run(lambda: repos.branches(owner, repo))


@router.get("/repo/{owner}/{repo}/file")
def get_file(
    owner: str,
    repo: str,
    path: str = Query(...),
    repos: RepositoryService = Depends(get_repository_service),
):
    return run(lambda: repos.client.get(f"/repos/{owner}/{repo}/contents/{path}"))
PY

cat > "$BACKEND/app/api/github/branches.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.github.dependencies import get_branch_service
from app.api.github.errors import github_http_error
from app.services.github.branches import BranchService

router = APIRouter(prefix="/github", tags=["GitHub"])


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.post("/repo/{owner}/{repo}/branch")
def create_branch(
    owner: str,
    repo: str,
    new_branch: str,
    source_sha: str,
    branches: BranchService = Depends(get_branch_service),
):
    return run(lambda: branches.create_branch(owner, repo, new_branch, source_sha))
PY

cat > "$BACKEND/app/api/github/pull_requests.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.github.dependencies import get_pull_request_service
from app.api.github.errors import github_http_error
from app.services.github.pull_requests import PullRequestService

router = APIRouter(prefix="/github", tags=["GitHub"])


def run(fn):
    try:
        return fn()
    except Exception as exc:
        raise github_http_error(exc) from exc


@router.post("/repo/{owner}/{repo}/pull-request")
def create_pull_request(
    owner: str,
    repo: str,
    title: str,
    head: str,
    base: str,
    body: str = "",
    prs: PullRequestService = Depends(get_pull_request_service),
):
    return run(lambda: prs.create_pull_request(owner, repo, title, head, base, body))
PY
ok "GitHub API dependencies installed"

step "Consolidating shared application dependencies"
cat > "$BACKEND/app/core/dependencies.py" <<'PY'
"""Application dependency providers."""

from __future__ import annotations

from app.services.github import get_github_provider
from app.services.github.branches import BranchService
from app.services.github.commits import CommitService
from app.services.github.pull_requests import PullRequestService
from app.services.github.repositories import RepositoryService


def get_repository_service() -> RepositoryService:
    return get_github_provider().repositories


def get_branch_service() -> BranchService:
    return get_github_provider().branches


def get_commit_service() -> CommitService:
    return get_github_provider().commits


def get_pull_request_service() -> PullRequestService:
    return get_github_provider().pull_requests
PY

cat > "$BACKEND/app/services/engineering/service.py" <<'PY'
from __future__ import annotations

from app.services.github import get_github_provider
from app.services.github.provider import GitHubProvider


class EngineeringService:
    def __init__(self, github: GitHubProvider | None = None):
        provider = github or get_github_provider()
        self.github = provider
        self.repositories = provider.repositories
        self.branches = provider.branches
        self.commits = provider.commits
        self.pull_requests = provider.pull_requests

    def repository_summary(self, owner: str, repo: str):
        repository = self.repositories.repository(owner, repo)
        branches = self.repositories.branches(owner, repo)
        return {"repository": repository, "branches": branches}

    def health(self):
        return {
            "service": "engineering",
            "status": "ready" if self.github.configured else "unconfigured",
        }
PY
ok "Shared dependencies consolidated"

step "Adding deterministic regression tests"
mkdir -p "$BACKEND/tests"

cat > "$BACKEND/tests/test_service_lifecycle.py" <<'PY'
from __future__ import annotations

import pytest

from app.services.container import ServiceContainer
from app.services.errors import ServiceNotConfiguredError


class ExampleService:
    def __init__(self):
        self.started = False

    def startup(self):
        self.started = True


def test_factory_is_lazy():
    calls = []
    container = ServiceContainer()
    container.register_factory("example", lambda: calls.append(1) or ExampleService())
    assert calls == []
    assert container.is_initialized("example") is False
    assert isinstance(container.require("example"), ExampleService)
    assert calls == [1]


def test_unconfigured_optional_service_is_not_initialized():
    container = ServiceContainer()
    container.register_factory(
        "optional",
        ExampleService,
        required=False,
        configured=lambda: False,
    )
    assert container.status("optional").state.value == "unconfigured"
    with pytest.raises(ServiceNotConfiguredError):
        container.require("optional")


def test_required_services_start_but_optional_remains_lazy():
    required = ExampleService()
    optional = ExampleService()
    container = ServiceContainer()
    container.register_factory("required", lambda: required, required=True)
    container.register_factory("optional", lambda: optional)
    container.startup()
    assert required.started is True
    assert container.is_initialized("required") is True
    assert optional.started is False
PY

cat > "$BACKEND/tests/test_github_consolidation.py" <<'PY'
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
    monkeypatch.delenv("ODIN_GITHUB_TOKEN", raising=False)
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

    monkeypatch.delenv("ODIN_GITHUB_TOKEN", raising=False)
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
PY
ok "Deterministic tests installed"

step "Updating ignore rule"
touch "$ROOT/.gitignore"
grep -qxF '.odin-backups/' "$ROOT/.gitignore" || printf '\n.odin-backups/\n' >> "$ROOT/.gitignore"
ok "Backup directory ignored"

step "Running compile checks"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m compileall -q \
  "$BACKEND/app/core" \
  "$BACKEND/app/services" \
  "$BACKEND/app/api/github" \
  "$BACKEND/tests/test_service_lifecycle.py" \
  "$BACKEND/tests/test_github_consolidation.py"
ok "Python compile checks passed"

step "Verifying environment changes are observed in one process"
(
  cd "$ROOT"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
import os
from app.services.github.client import GitHubClient

os.environ["ODIN_GITHUB_TOKEN"] = "validation-token"
assert GitHubClient().configured is True

os.environ.pop("ODIN_GITHUB_TOKEN", None)
assert GitHubClient().configured is False

print("Dynamic environment resolution passed")
PY
)
ok "Dynamic configuration resolution passed"

step "Verifying credential-free FastAPI and OpenAPI"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.main import app
from app.services.github import github

schema = app.openapi()
assert "/" in schema["paths"]
assert "/github/repos" in schema["paths"]
assert github.initialized is False
print(f"OpenAPI generated with {len(schema['paths'])} paths")
PY
)
ok "FastAPI and OpenAPI are credential-free"

step "Verifying unconfigured endpoint returns 503"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.get("/github/repos")

assert response.status_code == 503, response.text
assert "not configured" in response.json()["detail"].lower()
print("Unconfigured GitHub endpoint returned HTTP 503")
PY
)
ok "GitHub HTTP 503 mapping passed"

step "Verifying configured construction is network-lazy"
(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="validation-token" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.odin import Odin
from app.services.container import container
from app.services.github import reset_github_provider

reset_github_provider()
container.reset()
odin = Odin()
provider = container.require("github")

assert provider.configured is True
assert provider.client._session is None
assert odin.status()["services"]["github"]["initialized"] is True
print("Configured provider constructed without network access")
PY
)
ok "Configured provider remains network-lazy"

step "Running focused regression tests"
(
  cd "$BACKEND"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m pytest -q \
    tests/test_service_lifecycle.py \
    tests/test_github_consolidation.py
)
ok "Focused regression tests passed"

step "Checking deterministic configuration invariants"
(
  cd "$ROOT"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from pathlib import Path

client = Path("backend/app/services/github/client.py").read_text()
package = Path("backend/app/services/github/__init__.py").read_text()
odin = Path("backend/app/core/odin.py").read_text()
tests = Path("backend/tests/test_github_consolidation.py").read_text()

assert "def resolve_github_token(" in client
assert '"ODIN_GITHUB_TOKEN" in os.environ' in client
assert "github = GitHubProvider()" not in package
assert "configured=github_is_configured" in odin
assert "isolate_github_state" in tests
print("Deterministic configuration invariants verified")
PY
)
ok "Configuration invariants passed"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\n' "$CHECKS"
printf 'Backup:       %s\n' "$BACKUP_DIR"
printf '\nInstalled:\n'
printf '  • Cumulative lazy service lifecycle foundation\n'
printf '  • Canonical GitHub client and provider\n'
printf '  • Dynamic ODIN_GITHUB_TOKEN resolution\n'
printf '  • Deterministic provider reset behavior\n'
printf '  • Request-time GitHub API dependencies\n'
printf '  • HTTP 503 mapping for missing credentials\n'
printf '  • Isolated regression tests with no state leakage\n'
printf '  • Backup, rollback, compile, and rerun safety\n'
printf '\nNext chunk: Milestone 21.5c — application startup lifecycle and diagnostics.\n'
