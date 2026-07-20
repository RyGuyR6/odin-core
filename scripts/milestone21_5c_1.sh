#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.5c.1"
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
    return "$code"
  fi
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
printf 'ODIN MILESTONE %s — READINESS STATE CORRECTION\n' "$MILESTONE"
printf '============================================================\n'
printf 'Repository: %s\nBackend:    %s\nPython:     %s\n' "$ROOT" "$BACKEND" "$PYTHON_BIN"

step "Checking Milestone 21.5b.3 foundation"
required=(
  "$BACKEND/app/main.py"
  "$BACKEND/app/api/health.py"
  "$BACKEND/app/core/odin.py"
  "$BACKEND/app/services/container.py"
  "$BACKEND/app/services/lifecycle.py"
  "$BACKEND/app/services/github/__init__.py"
  "$BACKEND/tests/test_service_lifecycle.py"
  "$BACKEND/tests/test_github_consolidation.py"
)
for file in "${required[@]}"; do
  [[ -f "$file" ]] || fail "Required file missing: $file"
done

grep -q "register_factory" "$BACKEND/app/services/container.py" ||
  fail "Lazy service container from Milestone 21.5b.3 not detected"
grep -q "reset_github_provider" "$BACKEND/app/services/github/__init__.py" ||
  fail "GitHub lifecycle foundation from Milestone 21.5b.3 not detected"
ok "Milestone 21.5b.3 foundation detected"

STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="$ROOT/.odin-backups/milestone21_5c_1/$STAMP"
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
  "$BACKEND/app/main.py"
  "$BACKEND/app/api/health.py"
  "$BACKEND/app/services/runtime.py"
  "$BACKEND/tests/test_runtime_lifecycle.py"
  "$BACKEND/tests/test_health_diagnostics.py"
  "$ROOT/.gitignore"
)
for file in "${files[@]}"; do backup "$file"; done
ok "Backup created at $BACKUP_DIR"

step "Installing application runtime lifecycle coordinator"
cat > "$BACKEND/app/services/runtime.py" <<'PY'
from __future__ import annotations

import inspect
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from time import perf_counter
from typing import Any, Awaitable, Callable

from app.core.logger import logger
from app.services.container import ServiceContainer, container


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class RuntimeState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    DEGRADED = "degraded"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(slots=True)
class LifecycleEvent:
    phase: str
    component: str
    status: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "component": self.component,
            "status": self.status,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "duration_ms": round(self.duration_ms, 3),
            "detail": self.detail,
        }


@dataclass(slots=True)
class RuntimeSnapshot:
    state: RuntimeState = RuntimeState.CREATED
    started_at: datetime | None = None
    ready_at: datetime | None = None
    stopping_at: datetime | None = None
    stopped_at: datetime | None = None
    startup_error: str | None = None
    shutdown_error: str | None = None
    events: list[LifecycleEvent] = field(default_factory=list)


class ApplicationRuntime:
    """Coordinates Odin startup, shutdown, readiness, and diagnostics."""

    def __init__(self, services: ServiceContainer | None = None):
        self.services = services or container
        self._snapshot = RuntimeSnapshot()
        self._lock = threading.RLock()

    @property
    def state(self) -> RuntimeState:
        return self._snapshot.state

    @property
    def is_live(self) -> bool:
        return self.state not in {RuntimeState.STOPPED, RuntimeState.FAILED}

    @property
    def is_ready(self) -> bool:
        if self.state not in {RuntimeState.READY, RuntimeState.DEGRADED}:
            return False
        return not self._required_service_failures()

    async def _invoke(
        self,
        phase: str,
        component: str,
        callback: Callable[[], Any] | None,
        *,
        required: bool,
    ) -> LifecycleEvent:
        started_at = utc_now()
        started_clock = perf_counter()
        status = "skipped"
        detail = None

        try:
            if callback is not None:
                result = callback()
                if inspect.isawaitable(result):
                    await result
                status = "ok"
        except Exception as exc:
            status = "error"
            detail = f"{type(exc).__name__}: {exc}"
            logger.exception(
                "Lifecycle %s failed for %s (required=%s)",
                phase,
                component,
                required,
            )
            if required:
                raise
        finally:
            completed_at = utc_now()
            event = LifecycleEvent(
                phase=phase,
                component=component,
                status=status,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=(perf_counter() - started_clock) * 1000,
                detail=detail,
            )
            with self._lock:
                self._snapshot.events.append(event)

        return event

    async def startup(
        self,
        *,
        storage_initialize: Callable[[], Any] | None = None,
    ) -> None:
        with self._lock:
            if self.state in {RuntimeState.STARTING, RuntimeState.READY, RuntimeState.DEGRADED}:
                return
            self._snapshot = RuntimeSnapshot(
                state=RuntimeState.STARTING,
                started_at=utc_now(),
            )

        logger.info("Odin application runtime starting")

        try:
            await self._invoke(
                "startup",
                "storage",
                storage_initialize,
                required=True,
            )
            await self._invoke(
                "startup",
                "service-container",
                self.services.startup,
                required=True,
            )

            required_failures = self._required_service_failures()
            optional_failures = self._optional_service_failures()

            with self._lock:
                self._snapshot.ready_at = utc_now()
                self._snapshot.state = (
                    RuntimeState.DEGRADED if optional_failures else RuntimeState.READY
                )

            if required_failures:
                raise RuntimeError(
                    "Required services are not ready: "
                    + ", ".join(required_failures)
                )

            logger.info(
                "Odin application runtime ready (state=%s, optional_failures=%s)",
                self.state.value,
                len(optional_failures),
            )
        except Exception as exc:
            with self._lock:
                self._snapshot.state = RuntimeState.FAILED
                self._snapshot.startup_error = f"{type(exc).__name__}: {exc}"
            raise

    async def shutdown(self) -> None:
        with self._lock:
            if self.state in {RuntimeState.STOPPING, RuntimeState.STOPPED}:
                return
            self._snapshot.state = RuntimeState.STOPPING
            self._snapshot.stopping_at = utc_now()

        logger.info("Odin application runtime stopping")

        try:
            await self._invoke(
                "shutdown",
                "service-container",
                self.services.shutdown,
                required=False,
            )
        except Exception as exc:
            with self._lock:
                self._snapshot.shutdown_error = f"{type(exc).__name__}: {exc}"
        finally:
            with self._lock:
                self._snapshot.state = RuntimeState.STOPPED
                self._snapshot.stopped_at = utc_now()
            logger.info("Odin application runtime stopped")

    @staticmethod
    def _service_failed(data: dict[str, Any]) -> bool:
        """
        Evaluate actual service failure, not registration style.

        Eager services registered with container.register() are initialized
        immediately and may be reported as required for compatibility. They
        are healthy whenever their state is ready and initialized is true.
        """
        state = data.get("state")
        initialized = bool(data.get("initialized"))
        configured = bool(data.get("configured"))

        if state in {"error", "stopped"}:
            return True
        if state == "unconfigured":
            return bool(data.get("required"))
        if state == "ready":
            return not initialized
        if state == "registered":
            return bool(data.get("required")) and not initialized
        return False

    def _required_service_failures(self) -> list[str]:
        failures: list[str] = []
        for name, data in self.services.health().items():
            if data.get("required") and self._service_failed(data):
                failures.append(name)
        return failures

    def _optional_service_failures(self) -> list[str]:
        failures: list[str] = []
        for name, data in self.services.health().items():
            if not data.get("required") and self._service_failed(data):
                failures.append(name)
        return failures

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
            started_at = snapshot.started_at
            ready_at = snapshot.ready_at
            now = utc_now()

            uptime_seconds = None
            if started_at is not None and snapshot.state not in {
                RuntimeState.CREATED,
                RuntimeState.STOPPED,
            }:
                uptime_seconds = max(0.0, (now - started_at).total_seconds())

            return {
                "state": snapshot.state.value,
                "live": self.is_live,
                "ready": self.is_ready,
                "started_at": iso_or_none(started_at),
                "ready_at": iso_or_none(ready_at),
                "stopping_at": iso_or_none(snapshot.stopping_at),
                "stopped_at": iso_or_none(snapshot.stopped_at),
                "uptime_seconds": (
                    round(uptime_seconds, 3)
                    if uptime_seconds is not None
                    else None
                ),
                "startup_error": snapshot.startup_error,
                "shutdown_error": snapshot.shutdown_error,
                "required_service_failures": self._required_service_failures(),
                "optional_service_failures": self._optional_service_failures(),
                "services": self.services.health(),
                "events": [event.as_dict() for event in snapshot.events],
            }


runtime = ApplicationRuntime()
PY
ok "Application runtime coordinator installed"

step "Installing health, liveness, readiness, and service diagnostics"
cat > "$BACKEND/app/api/health.py" <<'PY'
from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.core.settings import settings
from app.services.runtime import runtime

router = APIRouter(tags=["Health"])


def health_payload() -> dict:
    snapshot = runtime.snapshot()
    return {
        "status": (
            "healthy"
            if snapshot["ready"] and snapshot["state"] == "ready"
            else "degraded"
            if snapshot["live"]
            else "unhealthy"
        ),
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "runtime": snapshot,
    }


@router.get("/health")
def health(response: Response):
    payload = health_payload()
    if not payload["runtime"]["live"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("/health/live")
def liveness(response: Response):
    snapshot = runtime.snapshot()
    if not snapshot["live"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "alive" if snapshot["live"] else "stopped",
        "state": snapshot["state"],
        "uptime_seconds": snapshot["uptime_seconds"],
    }


@router.get("/health/ready")
def readiness(response: Response):
    snapshot = runtime.snapshot()
    if not snapshot["ready"]:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if snapshot["ready"] else "not_ready",
        "state": snapshot["state"],
        "required_service_failures": snapshot["required_service_failures"],
        "optional_service_failures": snapshot["optional_service_failures"],
    }


@router.get("/health/services")
def service_diagnostics():
    snapshot = runtime.snapshot()
    return {
        "state": snapshot["state"],
        "services": snapshot["services"],
        "events": snapshot["events"],
    }
PY
ok "Diagnostic health endpoints installed"

step "Wiring lifecycle coordination into FastAPI lifespan"
cat > "$BACKEND/app/main.py" <<'PY'
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.memory import router as memory_router
from app.api.auth import router as auth_router
from app.api.storage import router as storage_router
from app.api.events import router as events_router
from app.api.version import router as version_router
from app.api.github import router as github_router
from app.api.tools import router as tools_router
from app.api.jobs import router as jobs_router
from app.api.planner import router as planner_router
from app.api.llm import router as llm_router
from app.api.prompts import router as prompts_router
from app.api.conversations import router as conversations_router
from app.api.conversations import sessions_router
from app.api.agents import router as agents_router
from app.api.agents import workflows_router
from app.core.odin import Odin
from app.core.settings import settings
from app.mcp_server import mcp
from app.services.runtime import runtime
from app.storage.service import storage_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.startup(storage_initialize=storage_service.initialize)
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        await runtime.shutdown()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    lifespan=lifespan,
)

odin = Odin()

app.include_router(health_router)
app.include_router(version_router)
app.include_router(github_router)
app.include_router(tools_router)
app.include_router(jobs_router)
app.include_router(events_router)
app.include_router(storage_router)
app.include_router(memory_router)
app.include_router(auth_router)
app.include_router(llm_router)
app.include_router(prompts_router)
app.include_router(sessions_router)
app.include_router(workflows_router)
app.include_router(agents_router)
app.include_router(conversations_router)
app.include_router(planner_router)

app.mount("/mcp", mcp.streamable_http_app())


@app.get("/")
def root():
    status_payload = odin.status()
    status_payload["runtime"] = runtime.snapshot()
    return status_payload
PY
ok "FastAPI lifespan now coordinates application runtime"

step "Adding runtime lifecycle tests"
cat > "$BACKEND/tests/test_runtime_lifecycle.py" <<'PY'
from __future__ import annotations

import asyncio

from app.services.container import ServiceContainer
from app.services.runtime import ApplicationRuntime, RuntimeState


class SyncService:
    def __init__(self):
        self.started = False
        self.stopped = False

    def startup(self):
        self.started = True

    def shutdown(self):
        self.stopped = True


def test_runtime_starts_required_services_and_records_events():
    service = SyncService()
    services = ServiceContainer()
    services.register_factory("required", lambda: service, required=True)
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup(storage_initialize=lambda: None))

    snapshot = runtime.snapshot()
    assert runtime.state is RuntimeState.READY
    assert snapshot["ready"] is True
    assert service.started is True
    assert [event["component"] for event in snapshot["events"]] == [
        "storage",
        "service-container",
    ]

    asyncio.run(runtime.shutdown())
    assert runtime.state is RuntimeState.STOPPED
    assert service.stopped is True


def test_eager_registered_service_is_ready():
    service = SyncService()
    services = ServiceContainer()
    services.register("health", service)
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup())

    snapshot = runtime.snapshot()
    assert snapshot["ready"] is True
    assert snapshot["required_service_failures"] == []
    assert snapshot["services"]["health"]["initialized"] is True
    assert snapshot["services"]["health"]["state"] == "ready"


def test_unconfigured_optional_service_does_not_block_readiness():
    services = ServiceContainer()
    services.register_factory(
        "optional",
        object,
        required=False,
        configured=lambda: False,
    )
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup())

    snapshot = runtime.snapshot()
    assert snapshot["ready"] is True
    assert snapshot["services"]["optional"]["state"] == "unconfigured"


def test_required_startup_failure_marks_runtime_failed():
    services = ServiceContainer()

    def fail():
        raise RuntimeError("boom")

    services.register_factory("required", fail, required=True)
    runtime = ApplicationRuntime(services)

    try:
        asyncio.run(runtime.startup())
    except Exception:
        pass

    snapshot = runtime.snapshot()
    assert runtime.state is RuntimeState.FAILED
    assert snapshot["ready"] is False
    assert "boom" in snapshot["startup_error"]
PY

cat > "$BACKEND/tests/test_health_diagnostics.py" <<'PY'
from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_routes_are_present_in_openapi():
    from app.main import app

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "/health/live" in paths
    assert "/health/ready" in paths
    assert "/health/services" in paths


def test_health_endpoints_during_application_lifespan():
    from app.main import app

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")
        services = client.get("/health/services")
        root = client.get("/")

        assert live.status_code == 200
        assert live.json()["status"] == "alive"

        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        assert services.status_code == 200
        assert "health" in services.json()["services"]
        assert "github" in services.json()["services"]

        assert root.status_code == 200
        assert root.json()["runtime"]["ready"] is True
PY
ok "Runtime and health diagnostics tests installed"

step "Updating ignore rules"
touch "$ROOT/.gitignore"
grep -qxF '.odin-backups/' "$ROOT/.gitignore" || printf '\n.odin-backups/\n' >> "$ROOT/.gitignore"
grep -qxF '.odin-diagnostics/' "$ROOT/.gitignore" || printf '.odin-diagnostics/\n' >> "$ROOT/.gitignore"
ok "Generated lifecycle artifacts ignored"

step "Running compile checks"
PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m compileall -q \
  "$BACKEND/app/main.py" \
  "$BACKEND/app/api/health.py" \
  "$BACKEND/app/services/runtime.py" \
  "$BACKEND/tests/test_runtime_lifecycle.py" \
  "$BACKEND/tests/test_health_diagnostics.py"
ok "Python compile checks passed"

step "Verifying credential-free OpenAPI"
(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from app.main import app

schema = app.openapi()
paths = schema["paths"]
for required in (
    "/health",
    "/health/live",
    "/health/ready",
    "/health/services",
    "/github/repos",
):
    assert required in paths, required

print(f"OpenAPI generated with {len(paths)} paths")
PY
)
ok "OpenAPI verification passed"

step "Verifying lifecycle and health endpoints"
(
  cd "$ROOT"
  ODIN_GITHUB_TOKEN="" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from fastapi.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    live = client.get("/health/live")
    ready = client.get("/health/ready")
    services = client.get("/health/services")
    github = client.get("/github/repos")

assert live.status_code == 200, live.text
assert live.json()["status"] == "alive"
assert ready.status_code == 200, ready.text
assert ready.json()["status"] == "ready"
assert services.status_code == 200, services.text
assert services.json()["services"]["health"]["initialized"] is True
assert services.json()["services"]["github"]["state"] == "unconfigured"
assert github.status_code == 503, github.text

print("Lifecycle endpoints and optional GitHub degradation verified")
PY
)
ok "Runtime endpoint behavior passed"

step "Running Milestone 21.5 regression suite"
(
  cd "$BACKEND"
  ODIN_GITHUB_TOKEN="" PYTHONPATH="$BACKEND" "$PYTHON_BIN" -m pytest -q \
    tests/test_service_lifecycle.py \
    tests/test_github_consolidation.py \
    tests/test_runtime_lifecycle.py \
    tests/test_health_diagnostics.py
)
ok "Milestone 21.5 regression suite passed"

step "Checking lifecycle invariants"
(
  cd "$ROOT"
  PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
from pathlib import Path

runtime = Path("backend/app/services/runtime.py").read_text()
main = Path("backend/app/main.py").read_text()
health = Path("backend/app/api/health.py").read_text()

assert "class ApplicationRuntime" in runtime
assert "RuntimeState.READY" in runtime
assert "def _service_failed" in runtime
assert "await runtime.startup" in main
assert "await runtime.shutdown" in main
assert '@router.get("/health/live")' in health
assert '@router.get("/health/ready")' in health
assert '@router.get("/health/services")' in health

print("Lifecycle invariants verified")
PY
)
ok "Lifecycle invariants passed"

printf '\n============================================================\n'
printf '✅ ODIN MILESTONE %s COMPLETE\n' "$MILESTONE"
printf '============================================================\n'
printf 'Checks passed: %s\n' "$CHECKS"
printf 'Backup:       %s\n' "$BACKUP_DIR"
printf '\nInstalled:\n'
printf '  • Central application runtime lifecycle coordinator\n'
printf '  • Correct eager and lazy service readiness evaluation\n'
printf '  • Startup and shutdown event timing diagnostics\n'
printf '  • /health compatibility endpoint\n'
printf '  • /health/live liveness endpoint\n'
printf '  • /health/ready readiness endpoint\n'
printf '  • /health/services service diagnostics endpoint\n'
printf '  • FastAPI lifespan startup and shutdown orchestration\n'
printf '  • Root status runtime diagnostics\n'
printf '  • Compile, OpenAPI, endpoint, and regression validation\n'
printf '  • Automatic backup, rollback, and rerun safety\n'
printf '\nNext chunk: Milestone 21.6 — GitHub capability expansion and write safety.\n'
