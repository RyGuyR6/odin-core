#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=""
BACKEND=""
PYTHON_BIN=""
BACKUP_DIR=""
ROLLED_BACK=0
CHECKS=0

step(){ printf '\n▶ %s\n' "$1"; }
ok(){ CHECKS=$((CHECKS+1)); printf '✅ %s\n' "$1"; }
die(){ printf '❌ %s\n' "$1" >&2; exit 1; }

rollback(){
  code="$1"
  trap - ERR
  [[ "$ROLLED_BACK" == "1" ]] && exit "$code"
  ROLLED_BACK=1
  if [[ -n "${BACKUP_DIR:-}" && -d "$BACKUP_DIR/files" ]]; then
    printf '\n↩ Rolling back Milestone 21.5 changes...\n'
    while IFS= read -r -d '' item; do
      rel="${item#"$BACKUP_DIR/files/"}"
      target="$ROOT/${rel%.missing}"
      if [[ "$item" == *.missing ]]; then
        rm -rf "$target"
      else
        mkdir -p "$(dirname "$target")"
        cp -a "$item" "$target"
      fi
    done < <(find "$BACKUP_DIR/files" -type f -print0)
    printf '✅ Rollback completed\n'
  fi
  printf '\n============================================================\n'
  printf '❌ MILESTONE 21.5 FAILED\nLine: %s\nExit: %s\n' "${BASH_LINENO[0]:-unknown}" "$code"
  [[ -n "${BACKUP_DIR:-}" ]] && printf 'Backup: %s\n' "$BACKUP_DIR"
  exit "$code"
}
trap 'rollback $?' ERR

for candidate in "${ODIN_ROOT:-}" "$(pwd)" /workspaces/odin-core "$(git rev-parse --show-toplevel 2>/dev/null || true)"; do
  [[ -n "$candidate" ]] || continue
  if [[ -d "$candidate/backend/app" ]]; then
    ROOT="$(cd "$candidate" && pwd)"
    BACKEND="$ROOT/backend"
    break
  fi
done
[[ -n "$ROOT" ]] || die "Could not locate odin-core repository"

for candidate in "$BACKEND/.venv/bin/python" "$ROOT/.venv/bin/python" "$(command -v python || true)" "$(command -v python3 || true)"; do
  [[ -n "$candidate" && -x "$candidate" ]] && PYTHON_BIN="$candidate" && break
done
[[ -n "$PYTHON_BIN" ]] || die "Python not found"

printf '\n============================================================\n'
printf 'ODIN MILESTONE 21.5 — CORE STARTUP STABILIZATION\n'
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"

step "Checking required application foundation"
for file in \
  "$BACKEND/app/main.py" \
  "$BACKEND/app/core/settings.py" \
  "$BACKEND/app/services/github/client.py" \
  "$BACKEND/app/services/github/provider.py" \
  "$BACKEND/app/services/github/__init__.py"; do
  [[ -f "$file" ]] || die "Missing required file: $file"
done
ok "Application foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_5/$STAMP"
mkdir -p "$BACKUP_DIR/files"

backup(){
  target="$1"
  destination="$BACKUP_DIR/files/${target#"$ROOT/"}"
  mkdir -p "$(dirname "$destination")"
  if [[ -e "$target" ]]; then
    cp -a "$target" "$destination"
  else
    : > "${destination}.missing"
  fi
}

for path in \
  "$BACKEND/app/core/settings.py" \
  "$BACKEND/app/core/service_registry.py" \
  "$BACKEND/app/core/startup.py" \
  "$BACKEND/app/api/system.py" \
  "$BACKEND/app/main.py" \
  "$BACKEND/app/services/github/client.py" \
  "$BACKEND/app/services/github/provider.py" \
  "$BACKEND/app/services/github/__init__.py" \
  "$ROOT/.env.example" \
  "$ROOT/.gitignore"; do
  backup "$path"
done
ok "Backup created at $BACKUP_DIR"

step "Hardening settings loading"
cat > "$BACKEND/app/core/settings.py" <<'PY'
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "Odin Core"
    VERSION: str = "0.21.5"
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
ok "Settings now tolerate unrelated environment variables"

step "Installing service lifecycle registry"
cat > "$BACKEND/app/core/service_registry.py" <<'PY'
from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class ServiceDescriptor:
    name: str
    factory: Callable[[], Any]
    required: bool = False
    configured: Callable[[], bool] | None = None


class ServiceRegistry:
    """
    Thread-safe lazy dependency registry.

    Factories are not called during module import. Optional integrations can be
    present in the application without requiring credentials merely to boot,
    generate OpenAPI, or serve unrelated endpoints.
    """

    def __init__(self) -> None:
        self._descriptors: dict[str, ServiceDescriptor] = {}
        self._instances: dict[str, Any] = {}
        self._errors: dict[str, str] = {}
        self._lock = threading.RLock()

    def register(
        self,
        name: str,
        factory: Callable[[], Any],
        *,
        required: bool = False,
        configured: Callable[[], bool] | None = None,
        replace: bool = False,
    ) -> None:
        with self._lock:
            if name in self._descriptors and not replace:
                return
            self._descriptors[name] = ServiceDescriptor(
                name=name,
                factory=factory,
                required=required,
                configured=configured,
            )
            self._instances.pop(name, None)
            self._errors.pop(name, None)

    def configured(self, name: str) -> bool:
        descriptor = self._descriptors[name]
        return True if descriptor.configured is None else bool(descriptor.configured())

    def get(self, name: str) -> Any:
        with self._lock:
            if name in self._instances:
                return self._instances[name]
            descriptor = self._descriptors.get(name)
            if descriptor is None:
                raise KeyError(f"Unknown service: {name}")
            if not self.configured(name):
                raise RuntimeError(f"Service '{name}' is not configured")
            try:
                instance = descriptor.factory()
            except Exception as exc:
                self._errors[name] = f"{type(exc).__name__}: {exc}"
                raise
            self._instances[name] = instance
            self._errors.pop(name, None)
            return instance

    def reset(self, name: str | None = None) -> None:
        with self._lock:
            if name is None:
                self._instances.clear()
                self._errors.clear()
            else:
                self._instances.pop(name, None)
                self._errors.pop(name, None)

    def health(self, initialize: bool = False) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for name, descriptor in sorted(self._descriptors.items()):
            configured = self.configured(name)
            status = "ready" if name in self._instances else ("available" if configured else "unconfigured")
            error = self._errors.get(name)
            if initialize and configured and name not in self._instances:
                try:
                    self.get(name)
                    status = "ready"
                except Exception as exc:
                    status = "error"
                    error = f"{type(exc).__name__}: {exc}"
            result[name] = {
                "required": descriptor.required,
                "configured": configured,
                "initialized": name in self._instances,
                "status": status,
                "error": error,
            }
        return result


service_registry = ServiceRegistry()
PY

cat > "$BACKEND/app/core/startup.py" <<'PY'
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.core.service_registry import service_registry


@dataclass(slots=True)
class StartupReport:
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    checks: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return all(
            item.get("status") not in {"error", "missing"}
            or not item.get("required", False)
            for item in self.checks.values()
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "healthy": self.healthy,
            "started_at": self.started_at,
            "checks": self.checks,
        }


_last_report: StartupReport | None = None


def run_startup_checks(*, initialize_optional: bool = False) -> StartupReport:
    global _last_report
    report = StartupReport()
    report.checks["services"] = {
        "required": True,
        "status": "ready",
        "details": service_registry.health(initialize=initialize_optional),
    }
    _last_report = report
    return report


def get_startup_report() -> StartupReport:
    return _last_report or run_startup_checks(initialize_optional=False)
PY
ok "Lazy service lifecycle registry installed"

step "Making GitHub client lazy and import-safe"
cat > "$BACKEND/app/services/github/client.py" <<'PY'
from __future__ import annotations

from typing import Any

import requests

from app.core.settings import settings


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None, timeout_seconds: float = 30):
        self.token = token or settings.ODIN_GITHUB_TOKEN
        self.timeout_seconds = timeout_seconds
        self._session: requests.Session | None = None

    @property
    def configured(self) -> bool:
        return bool(self.token)

    @property
    def session(self) -> requests.Session:
        if not self.configured:
            raise RuntimeError(
                "GitHub integration is not configured. Set ODIN_GITHUB_TOKEN "
                "before calling GitHub operations."
            )
        if self._session is None:
            session = requests.Session()
            session.headers.update({
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Odin-Core",
            })
            self._session = session
        return self._session

    def request(self, method: str, endpoint: str, **kwargs: Any) -> Any:
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

cat > "$BACKEND/app/services/github/provider.py" <<'PY'
from __future__ import annotations

from app.services.github.client import GitHubClient
from app.services.github.repositories import RepositoryService
from app.services.github.branches import BranchService
from app.services.github.commits import CommitService
from app.services.github.contents import ContentService
from app.services.github.pull_requests import PullRequestService


class GitHubProvider:
    """Central access point for GitHub services without eager network setup."""

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
GitHub service package.

The exported ``github`` object is a lazy proxy. Importing FastAPI routes,
building OpenAPI, and starting Odin no longer require a GitHub token.
"""
from __future__ import annotations

from typing import Any

from app.core.service_registry import service_registry
from app.core.settings import settings
from .provider import GitHubProvider


def _build_github() -> GitHubProvider:
    return GitHubProvider()


service_registry.register(
    "github",
    _build_github,
    required=False,
    configured=lambda: bool(settings.ODIN_GITHUB_TOKEN),
)


def get_github() -> GitHubProvider:
    return service_registry.get("github")


class _LazyGitHub:
    def __getattr__(self, name: str) -> Any:
        return getattr(get_github(), name)

    @property
    def configured(self) -> bool:
        return bool(settings.ODIN_GITHUB_TOKEN)

    def __repr__(self) -> str:
        state = "configured" if self.configured else "unconfigured"
        return f"<LazyGitHubProvider {state}>"


github = _LazyGitHub()

__all__ = ["GitHubProvider", "get_github", "github"]
PY
ok "GitHub integration now initializes only when used"

step "Adding startup diagnostics API"
mkdir -p "$BACKEND/app/api"
cat > "$BACKEND/app/api/system.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter

from app.core.service_registry import service_registry
from app.core.startup import get_startup_report, run_startup_checks

router = APIRouter(prefix="/system", tags=["System"])


@router.get("/startup")
def startup_report():
    return get_startup_report().as_dict()


@router.get("/services")
def service_health(initialize: bool = False):
    return {
        "services": service_registry.health(initialize=initialize),
    }


@router.post("/checks")
def refresh_startup_checks(initialize_optional: bool = False):
    return run_startup_checks(initialize_optional=initialize_optional).as_dict()
PY

"$PYTHON_BIN" - "$BACKEND/app/main.py" <<'PY'
from pathlib import Path
import ast
import sys

path = Path(sys.argv[1])
text = path.read_text()

import_line = "from app.api.system import router as system_router\n"
startup_import = "from app.core.startup import run_startup_checks\n"

if import_line not in text:
    anchor = "from app.api.health import router as health_router\n"
    if anchor not in text:
        raise SystemExit("Could not locate health router import")
    text = text.replace(anchor, anchor + import_line, 1)

if startup_import not in text:
    anchor = "from app.core.settings import settings\n"
    if anchor not in text:
        raise SystemExit("Could not locate settings import")
    text = text.replace(anchor, anchor + startup_import, 1)

if "run_startup_checks(initialize_optional=False)" not in text:
    anchor = "async def lifespan(app: FastAPI):\n"
    if anchor not in text:
        raise SystemExit("Could not locate lifespan")
    text = text.replace(
        anchor,
        anchor + "    run_startup_checks(initialize_optional=False)\n",
        1,
    )

if "app.include_router(system_router)" not in text:
    anchor = "app.include_router(health_router)\n"
    if anchor not in text:
        raise SystemExit("Could not locate health router registration")
    text = text.replace(anchor, anchor + "app.include_router(system_router)\n", 1)

path.write_text(text)
PY
ok "Startup diagnostics endpoints registered"

step "Updating environment documentation"
touch "$ROOT/.env.example" "$ROOT/.gitignore"
grep -qxF 'ODIN_GITHUB_TOKEN=' "$ROOT/.env.example" || printf '\nODIN_GITHUB_TOKEN=\n' >> "$ROOT/.env.example"
grep -qxF '.odin-backups/' "$ROOT/.gitignore" || printf '\n.odin-backups/\n' >> "$ROOT/.gitignore"
ok "Environment documentation updated"

step "Compiling stabilized application"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m compileall -q \
  "$BACKEND/app/core" \
  "$BACKEND/app/services/github" \
  "$BACKEND/app/api/system.py" \
  "$BACKEND/app/main.py"
ok "Compile checks passed"

step "Validating startup without GitHub credentials"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.service_registry import service_registry
from app.services.github import github

assert github.configured is False
health = service_registry.health()
assert health["github"]["configured"] is False
assert health["github"]["initialized"] is False

from app.main import app
paths = app.openapi()["paths"]
assert "/system/startup" in paths
assert "/system/services" in paths
assert "/github/repositories" in paths or any(path.startswith("/github") for path in paths)
assert service_registry.health()["github"]["initialized"] is False
print("Credential-free application import passed")
PY
)
ok "Application starts and generates OpenAPI without GitHub token"

step "Validating lazy GitHub initialization"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.services.github import github
try:
    _ = github.repositories
except RuntimeError as exc:
    assert "not configured" in str(exc)
else:
    raise AssertionError("GitHub service should reject use when unconfigured")
print("Unconfigured GitHub use fails only at call boundary")
PY
)
ok "Optional GitHub service fails lazily at use boundary"

step "Validating configured GitHub construction without network access"
(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="validation-token" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.services.github import github, get_github
from app.core.service_registry import service_registry

assert github.configured is True
provider = get_github()
assert provider.configured is True
assert provider.client._session is None
assert service_registry.health()["github"]["initialized"] is True
print("Configured GitHub provider constructed without network request")
PY
)
ok "Configured provider remains network-lazy"

step "Validating settings compatibility"
(
  cd "$ROOT"
  ODIN_AUTH_SECRET="secret" \
  ODIN_API_KEY_PEPPER="pepper" \
  ODIN_BOOTSTRAP_USERNAME="admin" \
  ODIN_BOOTSTRAP_PASSWORD="password" \
  ODIN_DEFAULT_PROVIDER="mock" \
  ODIN_DEFAULT_MODEL="mock-echo" \
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.core.settings import settings
assert settings.APP_NAME == "Odin Core"
print("Unrelated Odin environment variables accepted")
PY
)
ok "Settings compatibility passed"

step "Validating HTTP diagnostics"
(
  cd "$ROOT"
  env -u ODIN_GITHUB_TOKEN PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    response = client.get("/system/services")
    assert response.status_code == 200, response.text
    github = response.json()["services"]["github"]
    assert github["configured"] is False
    assert github["initialized"] is False

    response = client.get("/system/startup")
    assert response.status_code == 200, response.text
    assert "healthy" in response.json()

print("System diagnostics HTTP checks passed")
PY
)
ok "HTTP diagnostics passed"

step "Verifying idempotent source state"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from pathlib import Path

main = Path("backend/app/main.py").read_text()
assert main.count("from app.api.system import router as system_router") == 1
assert main.count("app.include_router(system_router)") == 1
assert main.count("run_startup_checks(initialize_optional=False)") == 1

settings = Path("backend/app/core/settings.py").read_text()
assert 'extra="ignore"' in settings
print("Idempotency markers verified")
PY
ok "Idempotency verification passed"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE 21.5 COMPLETE\n'
printf '============================================================\n'
printf 'Checks passed: %s\n' "$CHECKS"
printf 'Backup:       %s\n' "$BACKUP_DIR"
printf '\nInstalled:\n'
printf '  • Import-safe configuration loading\n'
printf '  • Lazy optional-service registry\n'
printf '  • Lazy GitHub client and provider initialization\n'
printf '  • Credential-free FastAPI/OpenAPI startup\n'
printf '  • Startup and service diagnostics endpoints\n'
printf '  • Optional-service health reporting\n'
printf '  • Validation, backup, rollback, and idempotency checks\n'
printf '\nNext: rerun scripts/milestone21_v2.sh.\n'
