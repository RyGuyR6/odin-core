#!/usr/bin/env bash
set -Eeuo pipefail

MILESTONE="21.5d.1"
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
printf 'ODIN MILESTONE %s — MCP LIFECYCLE VALIDATION FIX\n' "$MILESTONE"
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
BACKUP_DIR="$ROOT/.odin-backups/milestone21_5d_1/$STAMP"
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
  "$BACKEND/app/services/container.py"
  "$BACKEND/app/services/runtime.py"
  "$BACKEND/app/mcp_server.py"
  "$BACKEND/tests/test_runtime_lifecycle.py"
  "$BACKEND/tests/test_health_diagnostics.py"
  "$ROOT/.gitignore"
)
for file in "${files[@]}"; do backup "$file"; done
ok "Backup created at $BACKUP_DIR"

step "Making ServiceContainer startup restart-safe"
"$PYTHON_BIN" - "$BACKEND/app/services/container.py" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
source = path.read_text()

old = """    def startup(self) -> None:
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
"""

new = """    def startup(self) -> None:
        \"\"\"
        Start eager services and required lazy services.

        Successful startup always restores READY, which makes repeated
        FastAPI lifespan/TestClient cycles safe after a prior shutdown.
        \"\"\"
        for name, service in list(self.services.items()):
            try:
                hook = getattr(service, "startup", None)
                if callable(hook):
                    hook()
                self._errors.pop(name, None)
                self._states[name] = ServiceState.READY
                logger.info(f"Started service: {name}")
            except Exception as exc:
                self._errors[name] = f"{type(exc).__name__}: {exc}"
                self._states[name] = ServiceState.ERROR
                raise

        for name, definition in list(self._definitions.items()):
            if not definition.required or name in self.services:
                continue

            try:
                service = self.require(name)
                hook = getattr(service, "startup", None)
                if callable(hook):
                    hook()
                self._errors.pop(name, None)
                self._states[name] = ServiceState.READY
                logger.info(f"Started required service: {name}")
            except Exception as exc:
                self._errors[name] = f"{type(exc).__name__}: {exc}"
                self._states[name] = ServiceState.ERROR
                raise
"""

if old in source:
    source = source.replace(old, new, 1)
elif new in source:
    pass
else:
    raise SystemExit(
        "ServiceContainer.startup() did not match the expected 21.5b.3 "
        "implementation; refusing an unsafe patch."
    )

path.write_text(source)
PY
ok "ServiceContainer now restores READY after successful restart"

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

            if required_failures:
                service_health = self.services.health()
                details = {
                    name: service_health.get(name, {})
                    for name in required_failures
                }
                raise RuntimeError(
                    "Required services are not ready: "
                    + ", ".join(required_failures)
                    + f"; details={details!r}"
                )

            with self._lock:
                self._snapshot.ready_at = utc_now()
                self._snapshot.state = (
                    RuntimeState.DEGRADED if optional_failures else RuntimeState.READY
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
    def _state_value(value: Any) -> str:
        """Normalize string enums and plain strings returned by ServiceContainer."""
        raw = getattr(value, "value", value)
        return str(raw).strip().lower()

    @classmethod
    def _required_service_failed(cls, data: dict[str, Any]) -> bool:
        state = cls._state_value(data.get("state"))
        configured = bool(data.get("configured", True))
        initialized = bool(data.get("initialized", False))

        # A required service is ready only when the container explicitly says
        # it is configured, initialized, and in the ready state.
        return not (configured and initialized and state == "ready")

    @classmethod
    def _optional_service_failed(cls, data: dict[str, Any]) -> bool:
        state = cls._state_value(data.get("state"))

        # Optional unconfigured/lazy services are expected and do not degrade
        # startup. Only an actual runtime error degrades the application.
        return state == "error"

    def _required_service_failures(self) -> list[str]:
        return [
            name
            for name, data in self.services.health().items()
            if data.get("required") and self._required_service_failed(data)
        ]

    def _optional_service_failures(self) -> list[str]:
        return [
            name
            for name, data in self.services.health().items()
            if not data.get("required") and self._optional_service_failed(data)
        ]

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

step "Installing restart-safe MCP factory"
cat > "$BACKEND/app/mcp_server.py" <<'PY'
from functools import wraps
from inspect import signature
from typing import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.tools.loader import load_tools
from app.tools.registry import registry


def create_mcp_handler(tool) -> Callable:
    execute = tool.execute

    @wraps(execute)
    def handler(**kwargs):
        return execute(**kwargs)

    handler.__name__ = tool.name.replace("-", "_")
    handler.__doc__ = tool.description
    handler.__signature__ = signature(execute)
    return handler


def create_mcp() -> FastMCP:
    """Create a fresh MCP server with a fresh single-use session manager."""
    server = FastMCP(
        name="Odin",
        instructions=(
            "Odin is a controlled engineering execution service. "
            "Use its tools to inspect and modify repositories through "
            "Odin-managed credentials and workflows."
        ),
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "odin-core.onrender.com",
                "odin-core.onrender.com:*",
                "api.odincore.net",
                "api.odincore.net:*",
                "localhost",
                "localhost:*",
                "127.0.0.1",
                "127.0.0.1:*",
            ],
        ),
    )

    load_tools()
    for tool in registry.all():
        handler = create_mcp_handler(tool)
        server.tool(
            name=tool.name,
            description=tool.description,
        )(handler)

    return server


# Compatibility instance for callers that import app.mcp_server.mcp.
# FastAPI lifespan execution creates a new instance via create_mcp().
mcp = create_mcp()
PY
ok "Restart-safe MCP factory installed"

step "Wiring lifecycle coordination into FastAPI lifespan"
cat > "$BACKEND/app/main.py" <<'PY'
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.routing import Mount

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
from app.mcp_server import create_mcp
from app.services.runtime import runtime
from app.storage.service import storage_service


# Keep one stable route object while replacing the mounted MCP ASGI app with
# a fresh server for every lifespan. MCP session managers are single-use.
_initial_mcp = create_mcp()
mcp_mount = Mount("/mcp", app=_initial_mcp.streamable_http_app())


@asynccontextmanager
async def lifespan(app: FastAPI):
    await runtime.startup(storage_initialize=storage_service.initialize)

    active_mcp = create_mcp()
    mcp_mount.app = active_mcp.streamable_http_app()

    try:
        async with active_mcp.session_manager.run():
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

app.router.routes.append(mcp_mount)


@app.get("/")
def root():
    status_payload = odin.status()
    status_payload["runtime"] = runtime.snapshot()
    return status_payload
PY
ok "FastAPI lifespan now recreates MCP session management"

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


def test_eager_registered_health_service_is_ready():
    service = SyncService()
    services = ServiceContainer()
    services.register("health", service)
    runtime = ApplicationRuntime(services)

    asyncio.run(runtime.startup())

    snapshot = runtime.snapshot()
    health = snapshot["services"]["health"]

    assert service.started is True
    assert health["required"] is True
    assert health["configured"] is True
    assert health["initialized"] is True
    assert ApplicationRuntime._state_value(health["state"]) == "ready"
    assert snapshot["required_service_failures"] == []
    assert snapshot["ready"] is True
    assert runtime.state is RuntimeState.READY


def test_container_can_restart_after_shutdown():
    service = SyncService()
    services = ServiceContainer()
    services.register("health", service)

    runtime_one = ApplicationRuntime(services)
    asyncio.run(runtime_one.startup())
    asyncio.run(runtime_one.shutdown())

    stopped = services.health()["health"]
    assert stopped["state"] == "stopped"

    runtime_two = ApplicationRuntime(services)
    asyncio.run(runtime_two.startup())

    restarted = services.health()["health"]
    assert restarted["state"] == "ready"
    assert restarted["initialized"] is True
    assert runtime_two.state is RuntimeState.READY
    assert runtime_two.snapshot()["required_service_failures"] == []


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


def test_application_lifespan_can_restart_with_fresh_mcp_manager():
    from app.main import app

    with TestClient(app) as first:
        assert first.get("/health/ready").status_code == 200

    with TestClient(app) as second:
        assert second.get("/health/ready").status_code == 200


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


step "Running exact eager-health readiness probe"
(
  cd "$BACKEND"
  ODIN_GITHUB_TOKEN="" PYTHONPATH="$BACKEND" "$PYTHON_BIN" - <<'PY'
import asyncio

from app.services.container import ServiceContainer
from app.services.runtime import ApplicationRuntime, RuntimeState


class ProbeHealthService:
    def __init__(self):
        self.started = False
        self.stopped = False

    def startup(self):
        self.started = True

    def shutdown(self):
        self.stopped = True


services = ServiceContainer()
health_service = ProbeHealthService()
services.register("health", health_service)
runtime = ApplicationRuntime(services)

asyncio.run(runtime.startup())
first_snapshot = runtime.snapshot()
first_health = first_snapshot["services"]["health"]

assert health_service.started is True
assert first_health["required"] is True
assert first_health["configured"] is True
assert first_health["initialized"] is True
assert ApplicationRuntime._state_value(first_health["state"]) == "ready"
assert first_snapshot["required_service_failures"] == []
assert first_snapshot["ready"] is True
assert runtime.state is RuntimeState.READY

asyncio.run(runtime.shutdown())
assert health_service.stopped is True
assert runtime.state is RuntimeState.STOPPED
assert services.health()["health"]["state"] == "stopped"

second_runtime = ApplicationRuntime(services)
asyncio.run(second_runtime.startup())
second_snapshot = second_runtime.snapshot()
second_health = second_snapshot["services"]["health"]

assert ApplicationRuntime._state_value(second_health["state"]) == "ready"
assert second_health["initialized"] is True
assert second_snapshot["required_service_failures"] == []
assert second_snapshot["ready"] is True
assert second_runtime.state is RuntimeState.READY

asyncio.run(second_runtime.shutdown())

print("Exact eager-health restart readiness probe passed")
PY
)
ok "Exact eager-health restart readiness probe passed"

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
health_data = services.json()["services"]["health"]
assert health_data["required"] is True
assert health_data["configured"] is True
assert health_data["initialized"] is True
assert health_data["state"] == "ready"
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

container = Path("backend/app/services/container.py").read_text()
runtime = Path("backend/app/services/runtime.py").read_text()
main = Path("backend/app/main.py").read_text()
mcp_server = Path("backend/app/mcp_server.py").read_text()
health = Path("backend/app/api/health.py").read_text()

assert "self._states[name] = ServiceState.READY" in container
assert "self._states[name] = ServiceState.ERROR" in container
assert "class ApplicationRuntime" in runtime
assert "def _state_value" in runtime
assert "def _required_service_failed" in runtime
assert "configured and initialized and state == \"ready\"" in runtime
assert "RuntimeState.READY" in runtime
assert "await runtime.startup" in main
assert "await runtime.shutdown" in main
assert "active_mcp = create_mcp()" in main
assert "mcp_mount.app = active_mcp.streamable_http_app()" in main
assert "def create_mcp()" in mcp_server
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
printf '  • Fresh MCP server/session manager per FastAPI lifespan\n  • Restart-safe ServiceContainer state transitions\n  • Enum-safe, metadata-driven required service readiness\n'
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
