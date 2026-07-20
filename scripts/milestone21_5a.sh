#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.5a"
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
  if [[ "$ROLLED_BACK" == "1" ]]; then
    exit "$code"
  fi
  ROLLED_BACK=1

  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone %s changes...\n' "$MILESTONE"
    while IFS= read -r -d '' saved; do
      rel="${saved#"$BACKUP_DIR/files/"}"
      if [[ "$saved" == *.missing ]]; then
        target="$ROOT/${rel%.missing}"
        rm -rf "$target"
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

[[ -n "$ROOT" ]] || fail "Could not locate the odin-core repository"

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
printf 'ODIN MILESTONE %s — SERVICE LIFECYCLE FOUNDATION\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\n' "$ROOT"
printf 'Backend:    %s\n' "$BACKEND"
printf 'Python:     %s\n' "$PYTHON_BIN"

step "Checking expected Odin architecture"
required=(
  "$BACKEND/app/core/odin.py"
  "$BACKEND/app/core/settings.py"
  "$BACKEND/app/services/container.py"
  "$BACKEND/app/services/base.py"
  "$BACKEND/app/services/health_service.py"
  "$BACKEND/app/services/github_service.py"
  "$BACKEND/app/main.py"
)

for file in "${required[@]}"; do
  [[ -f "$file" ]] || fail "Required file missing: $file"
done
ok "Expected Odin architecture detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_5a/$STAMP"
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

files_to_backup=(
  "$BACKEND/app/core/settings.py"
  "$BACKEND/app/core/odin.py"
  "$BACKEND/app/services/container.py"
  "$BACKEND/app/services/github_service.py"
  "$BACKEND/app/services/lifecycle.py"
  "$BACKEND/app/services/errors.py"
  "$BACKEND/tests/test_service_lifecycle.py"
  "$ROOT/.gitignore"
)

for file in "${files_to_backup[@]}"; do
  backup "$file"
done
ok "Backup created at $BACKUP_DIR"

step "Hardening application settings"
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
ok "Settings accept unrelated Odin environment variables"

step "Adding service lifecycle types"
cat > "$BACKEND/app/services/errors.py" <<'PY'
from __future__ import annotations


class ServiceError(RuntimeError):
    """Base exception for Odin service lifecycle errors."""


class ServiceNotRegisteredError(ServiceError, KeyError):
    """Raised when a service name is not registered."""


class ServiceNotConfiguredError(ServiceError):
    """Raised when an optional service is requested without configuration."""


class ServiceInitializationError(ServiceError):
    """Raised when a service factory fails."""
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
ok "Lifecycle definitions installed"

step "Replacing eager service container with lazy-compatible registry"
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
    """
    Backward-compatible service container with lazy factories.

    Existing code may continue calling ``register(name, instance)`` and
    ``get(name)``. New code should prefer ``register_factory`` for optional or
    expensive integrations so importing and booting Odin does not initialize
    them eagerly.
    """

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
            self._definitions[name] = ServiceDefinition(
                name=name,
                factory=factory,
                required=required,
                configured=configured,
            )
            self._errors.pop(name, None)
            self._states[name] = (
                ServiceState.REGISTERED
                if self._definitions[name].is_configured()
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
                raise ServiceNotConfiguredError(
                    f"Service '{name}' is not configured."
                )

            try:
                service = definition.factory()
            except Exception as exc:
                message = f"{type(exc).__name__}: {exc}"
                self._errors[name] = message
                self._states[name] = ServiceState.ERROR
                raise ServiceInitializationError(
                    f"Service '{name}' failed to initialize: {message}"
                ) from exc

            self.services[name] = service
            self._errors.pop(name, None)
            self._states[name] = ServiceState.READY
            logger.info(f"Initialized lazy service: {name}")
            return service

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
                lazy_names = set(self._definitions)
                self.services.clear()
                self._errors.clear()
                for service_name in lazy_names:
                    definition = self._definitions[service_name]
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
                required=bool(definition.required) if definition else True,
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
            startup = getattr(service, "startup", None)
            if callable(startup):
                startup()
                logger.info(f"Started service: {name}")

        for name, definition in list(self._definitions.items()):
            if not definition.required:
                continue
            service = self.require(name)
            startup = getattr(service, "startup", None)
            if callable(startup):
                startup()
                logger.info(f"Started required service: {name}")

    def shutdown(self) -> None:
        for name, service in reversed(list(self.services.items())):
            shutdown = getattr(service, "shutdown", None)
            if callable(shutdown):
                shutdown()
                logger.info(f"Stopped service: {name}")
            self._states[name] = ServiceState.STOPPED


container = ServiceContainer()
PY
ok "Lazy-compatible service container installed"

step "Making legacy GitHubService construction import-safe"
cat > "$BACKEND/app/services/github_service.py" <<'PY'
"""
Legacy GitHub Service.

This compatibility service no longer requires credentials during object
construction. Authentication is enforced when a GitHub operation is called.
A later stabilization chunk will consolidate it with app.services.github.
"""

from __future__ import annotations

from typing import Any

import requests

from app.core.settings import settings
from app.services.errors import ServiceNotConfiguredError


class GitHubService:
    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        token: str | None = None,
        *,
        timeout_seconds: float = 30.0,
        session: requests.Session | None = None,
    ):
        self.token = token or settings.ODIN_GITHUB_TOKEN
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

    def _request(self, method: str, endpoint: str, **kwargs: Any):
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

    def _get(self, endpoint: str):
        return self._request("GET", endpoint)

    def _post(self, endpoint: str, payload: dict):
        return self._request("POST", endpoint, json=payload)

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
            {
                "ref": f"refs/heads/{new_branch}",
                "sha": source_sha,
            },
        )
PY
ok "Legacy GitHub service now authenticates only at operation time"

step "Refactoring Odin service registration"
cat > "$BACKEND/app/core/odin.py" <<'PY'
from __future__ import annotations

from app.core.logger import logger
from app.core.settings import settings
from app.services.container import container
from app.services.github_service import GitHubService
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
                GitHubService,
                required=False,
                configured=lambda: bool(settings.ODIN_GITHUB_TOKEN),
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
ok "Odin now registers GitHub lazily"

step "Adding lifecycle regression tests"
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

    service = container.require("example")

    assert isinstance(service, ExampleService)
    assert calls == [1]
    assert container.is_initialized("example") is True


def test_unconfigured_optional_service_is_not_initialized():
    container = ServiceContainer()
    container.register_factory(
        "optional",
        ExampleService,
        required=False,
        configured=lambda: False,
    )

    status = container.status("optional")
    assert status.configured is False
    assert status.initialized is False
    assert status.state.value == "unconfigured"

    with pytest.raises(ServiceNotConfiguredError):
        container.require("optional")


def test_required_services_start_but_optional_services_remain_lazy():
    required = ExampleService()
    optional = ExampleService()
    container = ServiceContainer()
    container.register_factory("required", lambda: required, required=True)
    container.register_factory("optional", lambda: optional, required=False)

    container.startup()

    assert required.started is True
    assert container.is_initialized("required") is True
    assert optional.started is False
    assert container.is_initialized("optional") is False
PY
ok "Lifecycle regression tests added"

step "Updating backup ignore rule"
touch "$ROOT/.gitignore"
grep -qxF '.odin-backups/' "$ROOT/.gitignore" || printf '\n.odin-backups/\n' >> "$ROOT/.gitignore"
ok "Backup directory ignored by Git"

step "Running shell and Python syntax checks"
bash -n "$0"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m compileall -q \
  "$BACKEND/app/core" \
  "$BACKEND/app/services" \
  "$BACKEND/tests/test_service_lifecycle.py"
ok "Syntax and compile checks passed"

step "Verifying credential-free Odin construction"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.odin import Odin
from app.services.container import container

odin = Odin()
status = odin.status()

assert status["status"] == "online"
assert status["services"]["health"]["initialized"] is True
assert status["services"]["github"]["configured"] is False
assert status["services"]["github"]["initialized"] is False
assert container.is_initialized("github") is False

print("Credential-free Odin construction passed")
PY
)
ok "Odin constructs without GitHub credentials"

step "Verifying GitHub failure occurs only at use boundary"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.odin import Odin
from app.services.container import container
from app.services.errors import ServiceNotConfiguredError

Odin()

try:
    container.require("github")
except ServiceNotConfiguredError as exc:
    assert "not configured" in str(exc)
else:
    raise AssertionError("Expected unconfigured GitHub service to fail lazily")

assert container.is_initialized("github") is False
print("Lazy GitHub configuration boundary passed")
PY
)
ok "GitHub remains lazy when unconfigured"

step "Verifying configured service construction without network access"
(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="milestone-validation-token" \
  PYTHONPATH="$BACKEND" \
  "$PYTHON_BIN" - <<'PY'
from app.core.odin import Odin
from app.services.container import container

Odin()
service = container.require("github")

assert service.configured is True
assert service._session is None
assert container.is_initialized("github") is True

print("Configured GitHub service constructed without network access")
PY
)
ok "Configured GitHub construction remains network-lazy"

step "Verifying FastAPI and OpenAPI without GitHub credentials"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.main import app
from app.services.container import container

schema = app.openapi()
assert schema["info"]["title"]
assert "/" in schema["paths"]
assert container.is_initialized("github") is False

print(f"OpenAPI generated with {len(schema['paths'])} paths")
PY
)
ok "FastAPI and OpenAPI import passed without GitHub credentials"

step "Running lifecycle tests"
(
  cd "$BACKEND"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m pytest -q tests/test_service_lifecycle.py
)
ok "Lifecycle tests passed"

step "Verifying installer idempotency markers"
(
  cd "$ROOT"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from pathlib import Path

odin = Path("backend/app/core/odin.py").read_text()
container = Path("backend/app/services/container.py").read_text()
settings = Path("backend/app/core/settings.py").read_text()

assert odin.count('container.register_factory(') == 1
assert "class ServiceContainer" in container
assert "def register_factory(" in container
assert 'extra="ignore"' in settings

print("Idempotency markers verified")
PY
)
ok "Idempotency markers verified"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\n' "$CHECKS"
printf 'Backup:       %s\n' "$BACKUP_DIR"
printf '\nInstalled:\n'
printf '  • Backward-compatible lazy service container\n'
printf '  • Service lifecycle states and errors\n'
printf '  • Import-safe legacy GitHub service\n'
printf '  • Lazy GitHub registration in Odin\n'
printf '  • Credential-free FastAPI/OpenAPI startup validation\n'
printf '  • Lifecycle regression tests\n'
printf '  • Backup, rollback, and rerun safety\n'
printf '\nNext chunk: Milestone 21.5b — GitHub service consolidation.\n'
